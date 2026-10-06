"""Invite links (shared bot and own bot) and the forced channel join."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app import bale, gate, referral  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.engine import MemoryStore, handle, new_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Bot, BotVersion, CustomerSeen, ReferralJoin, User, VersionTests  # noqa: E402
from app.spec import BotSpec  # noqa: E402

BASE = {"name": "کافه", "welcome": "سلام", "menu": [{"label": "دعوت دوستان", "block": "ref"}, {"label": "درباره", "block": "about"}],
        "blocks": [{"type": "referral", "id": "ref", "title": "دعوت", "goal": 2, "reward_text": "یک قهوه رایگان 🎁"},
                   {"type": "message", "id": "about", "text": "ما کافه‌ایم"}]}


def test_spec_rules_for_gate_and_referral():
    BotSpec.model_validate({**BASE, "gate": {"channel": "@mycafe_channel"}})
    BotSpec.model_validate({**BASE, "gate": {"channel": "-1001234567890"}})
    for bad in ("mycafe", "@ab", "@has space", "https://ble.ir/x", ""):
        with pytest.raises(ValidationError):
            BotSpec.model_validate({**BASE, "gate": {"channel": bad}})
    with pytest.raises(ValidationError):
        BotSpec.model_validate({**BASE, "gate": {"channel": "@mycafe_channel", "join_url": "http://x"}})
    with pytest.raises(ValidationError):
        BotSpec.model_validate({**BASE, "blocks": [{**BASE["blocks"][0], "goal": 0}, BASE["blocks"][1]]})


def test_engine_referral_block_shows_link_progress_and_reward():
    sp, s, st = BotSpec.model_validate(BASE), new_session(), MemoryStore()
    handle(sp, s, "/start", st)
    out = handle(sp, s, "m:0", st)
    assert "فقط در بله و تلگرام" in out[0]["text"] and "0 از 2" in out[0]["text"] and "رایگان" not in out[0]["text"]
    s["ref"] = {"link": "https://ble.ir/bot?start=rabc12345", "count": 1}
    out = handle(sp, s, "m:0", st)
    assert "https://ble.ir/bot?start=rabc12345" in out[0]["text"] and "1 از 2" in out[0]["text"] and "رایگان" not in out[0]["text"]
    s["ref"]["count"] = 2
    assert "رایگان" in handle(sp, s, "m:0", st)[0]["text"]


# ---- Bale integration ----
@pytest.fixture()
def world(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    bale._seen.clear(); bale._gate_notice.clear(); bale._cap_notice.clear()
    monkeypatch.setattr(settings, "public_base_url", "https://example.test")
    monkeypatch.setattr(settings, "bale_shared_bot_token", "SHAREDTOKEN")
    sent, members = [], {"@mycafe_channel": {601: "member", 602: "left", 9999: "administrator"}}
    state = {"fail": False}

    def fake(token, method, payload=None, timeout=15):
        if method == "sendMessage":
            sent.append((str(payload["chat_id"]), payload["text"], payload.get("reply_markup")))
        if method == "getMe":
            return {"username": "botyar_test_bot", "id": 9999}
        if method == "getChatMember":
            if state["fail"]:
                raise bale.BaleError("Bad Request: chat not found")
            return {"status": members[payload["chat_id"]].get(payload["user_id"], "left")}
        return True

    monkeypatch.setattr(bale, "api_call", fake)
    with TestClient(app) as c:
        tok = c.post("/api/auth/register", json={"username": "r_x.com", "password": "123456"}).json()["token"]
        H = {"Authorization": f"Bearer {tok}"}

        def make(spec):
            with SessionLocal() as db:
                uid = db.query(User).filter(User.username == "r_x.com").one().id
                bot = Bot(user_id=uid, name="کافه")
                db.add(bot); db.flush()
                db.add(BotVersion(bot_id=bot.id, version=1, spec=spec, note=""))
                db.add(VersionTests(bot_id=bot.id, version=1, scenarios=[], results=[{"name": "t", "passed": True, "failures": [], "transcript": []}]))
                db.commit()
                return bot.id

        yield c, H, make, sent, state


def driver(c):
    n = [70000]

    def msg(chat, text, name="مشتری"):
        n[0] += 1
        return c.post(f"/api/hook/shared/{bale.shared_hook_secret()}", json={"update_id": n[0], "message": {
            "message_id": 1, "from": {"id": chat, "first_name": name}, "chat": {"id": chat, "type": "private"}, "text": text}})

    def tap(chat, data):
        n[0] += 1
        return c.post(f"/api/hook/shared/{bale.shared_hook_secret()}", json={"update_id": n[0], "callback_query": {
            "id": "q", "from": {"id": chat}, "data": data, "message": {"message_id": 7, "chat": {"id": chat, "type": "private"}}}})

    return msg, tap


def test_invite_link_flow_counts_new_customers_once_and_never_self_or_existing_customers(world):
    c, H, make, sent, _ = world
    bid = make(BASE)
    pub = c.post(f"/api/bots/{bid}/publish", json={"mode": "shared"}, headers=H).json()
    msg, tap = driver(c)
    msg(701, f"/start {pub['code']}", "سارا")                                   # the inviter arrives through the business link
    sent.clear()
    tap(701, "m:0")
    link = [t for ch, t, _ in sent if ch == "701"][0]
    code = link.split("start=")[1].split()[0].strip()
    assert code.startswith("r") and len(code) == 8 and "botyar_test_bot?start=" in link
    sent.clear()
    msg(702, f"/start {code}", "علی")                                           # brand new customer through the invite link
    assert any(ch == "701" and "یک نفر با لینک اختصاصی شما وارد شد" in t and "1 از 2" in t.replace("۱", "1").replace("۲", "2") for ch, t, _ in sent)
    assert any(ch == "702" and "سلام" in t for ch, t, _ in sent)                 # and they land in the business's bot
    msg(702, f"/start {code}", "علی")                                           # again: no second count
    msg(701, f"/start {code}", "سارا")                                          # self-invite: no count
    msg(703, f"/start {pub['code']}", "رضا")
    msg(703, f"/start {code}", "رضا")                                           # existing customer: no count
    with SessionLocal() as db:
        assert db.query(ReferralJoin).count() == 1
    data = c.get(f"/api/bots/{bid}/referrals", headers=H).json()
    assert data == {"total": 1, "top": [{"name": "سارا", "invited": 1}]}
    sent.clear()
    msg(704, f"/start {code}", "مینا")                                           # the second invite reaches the goal (2)
    assert any(ch == "701" and "به هدف رسیدید" in t for ch, t, _ in sent)
    tap(701, "m:0")
    assert any(ch == "701" and "رایگان" in t for ch, t, _ in sent)
    assert "701" not in str(data) and "bale:" not in str(data)


def test_unknown_or_foreign_invite_codes_do_nothing_harmful(world):
    c, H, make, sent, _ = world
    make(BASE)
    msg, _ = driver(c)
    sent.clear()
    msg(710, "/start rzzzzzzz")                                                  # well-formed but unknown code
    assert not any("وارد شد" in t for _, t, _ in sent)
    other = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"username": "o_x.com", "password": "123456"}).json()["token"]}
    assert c.get("/api/bots/1/referrals", headers=other).status_code == 404


GATED = {**BASE, "gate": {"channel": "@mycafe_channel", "text": "اول عضو کانال شو"}}


def test_forced_join_blocks_non_members_lets_members_in_and_remembers(world):
    c, H, make, sent, state = world
    bid = make(GATED)
    pub = c.post(f"/api/bots/{bid}/publish", json={"mode": "shared"}, headers=H).json()
    msg, tap = driver(c)
    sent.clear()
    msg(602, f"/start {pub['code']}")                                            # not a member
    out = [x for x in sent if x[0] == "602"]
    assert len(out) == 1 and "اول عضو کانال شو" in out[0][1]
    buttons = out[0][2]["inline_keyboard"]
    assert buttons[0][0]["url"] == "https://ble.ir/mycafe_channel" and buttons[1][0]["callback_data"] == "gate:check"
    with SessionLocal() as db:
        assert db.query(CustomerSeen).count() == 0                               # non-members are not customers (and cost no cap)
    sent.clear()
    msg(601, f"/start {pub['code']}")                                            # a member goes straight in
    assert any(ch == "601" and "سلام" in t for ch, t, _ in sent)
    state["fail"] = True
    sent.clear()
    msg(601, "/start")                                                            # remembered: no new membership call needed
    assert any(ch == "601" and "سلام" in t for ch, t, _ in sent)


def test_gate_check_button_after_joining_and_fail_open_when_the_check_cannot_be_made(world):
    c, H, make, sent, state = world
    bid = make(GATED)
    pub = c.post(f"/api/bots/{bid}/publish", json={"mode": "shared"}, headers=H).json()
    msg, tap = driver(c)
    msg(900, f"/admin {pub['admin_code']}")
    msg(602, f"/start {pub['code']}")
    sent.clear()
    tap(602, "gate:check")                                                        # still not a member: blocked again
    assert any("اول عضو کانال شو" in t for ch, t, _ in sent if ch == "602")
    state["fail"] = True                                                          # the bot is not admin / channel name wrong
    sent.clear()
    tap(602, "gate:check")
    assert any("سلام" in t for ch, t, _ in sent if ch == "602")                  # fail open: the customer is let in
    assert sum("بررسی عضویت" in t for ch, t, _ in sent if ch == "900") == 1      # the owner is warned
    tap(602, "m:1")
    assert sum("بررسی عضویت" in t for ch, t, _ in sent if ch == "900") == 1      # once a day


def test_gate_setup_status_for_the_owner(world):
    c, H, make, sent, state = world
    bid = make(GATED)
    c.post(f"/api/bots/{bid}/publish", json={"mode": "shared"}, headers=H)
    st = c.get(f"/api/bots/{bid}/gate", headers=H).json()
    assert st["configured"] is True and st["messengers"][0]["ok"] is True and st["messengers"][0]["status"] == "administrator"
    state["fail"] = True
    st = c.get(f"/api/bots/{bid}/gate", headers=H).json()
    assert st["messengers"][0]["ok"] is False and "chat not found" in st["messengers"][0]["error"]
    plain = make(BASE)
    assert c.get(f"/api/bots/{plain}/gate", headers=H).json() == {"configured": False, "messengers": []}
    other = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"username": "z_x.com", "password": "123456"}).json()["token"]}
    assert c.get(f"/api/bots/{bid}/gate", headers=other).status_code == 404
