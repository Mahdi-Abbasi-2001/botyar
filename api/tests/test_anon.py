"""Anonymous chat: pairing, relaying, safety filters, ending, reporting, banning, expiry (Bale and Telegram customers mixed)."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from datetime import datetime, timedelta, timezone  # noqa: E402

import pytest  # noqa: E402

from app import anon, outreach  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.engine import MemoryStore, handle, new_session  # noqa: E402
from app.models import AnonPair, AnonQueue, BannedCustomer, CustomerSeen, Record  # noqa: E402
from app.spec import BotSpec  # noqa: E402

from tests.test_referral_gate import driver, world  # noqa: E402,F401

@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    anon._hits.clear()
    yield


SPEC = {"name": "باشگاه", "welcome": "سلام", "menu": [{"label": "چت ناشناس", "block": "anon"}, {"label": "درباره", "block": "about"}],
        "blocks": [{"type": "anon_chat", "id": "anon", "title": "چت ناشناس"}, {"type": "message", "id": "about", "text": "ما باشگاهیم"}]}


def test_engine_emits_actions_and_walks_the_states():
    sp, s, st = BotSpec.model_validate(SPEC), new_session(), MemoryStore()
    handle(sp, s, "/start", st)
    out = handle(sp, s, "m:0", st)
    assert [b["data"] for a in out for b in a.get("buttons", [])] == ["ac:find", "/menu"] and s["step"] == "idle"
    out = handle(sp, s, "ac:find", st)
    assert out[1] == {"type": "anon_find", "block": "anon"} and s["step"] == "waiting"
    out = handle(sp, s, "سلام؟", st)
    assert not [a for a in out if a["type"].startswith("anon_")] and s["step"] == "waiting"      # typing while waiting does nothing
    out = handle(sp, s, "/menu", st)                                                               # leaving while waiting releases the queue
    assert out[0] == {"type": "anon_end", "block": "anon"} and s["block"] is None
    s["block"], s["step"] = "anon", "chat"
    assert handle(sp, s, "سلام", st) == [{"type": "anon_relay", "block": "anon", "text": "سلام"}]
    assert handle(sp, s, "ac:report", st)[0]["type"] == "anon_report" and s["step"] == "idle"


def chat(world):
    c, H, make, sent, state = world
    bid = make(SPEC)
    pub = c.post(f"/api/bots/{bid}/publish", json={"mode": "shared"}, headers=H).json()
    msg, tap = driver(c)
    for chat_id, name in ((801, "سارا"), (802, "علی"), (803, "رضا")):
        msg(chat_id, f"/start {pub['code']}", name)
    return c, H, bid, sent, msg, tap


def texts(sent, chat_id):
    return [t for ch, t, _ in sent if ch == str(chat_id)]


def test_two_customers_are_paired_and_messages_are_relayed_without_identity(world):
    c, H, bid, sent, msg, tap = chat(world)
    tap(801, "m:0"); tap(801, "ac:find")
    assert any("در حال جستجو" in t for t in texts(sent, 801))
    sent.clear()
    tap(802, "m:0"); tap(802, "ac:find")
    assert any("شریک گفتگو پیدا شد" in t for t in texts(sent, 801)) and any("شریک گفتگو پیدا شد" in t for t in texts(sent, 802))
    sent.clear()
    msg(801, "سلام، خوبی؟", "سارا")
    got = texts(sent, 802)
    assert got == ["👤 سلام، خوبی؟"] and "سارا" not in str(sent) and "801" not in str(got)
    sent.clear()
    msg(802, "مرسی، تو چطوری؟", "علی")
    assert texts(sent, 801) == ["👤 مرسی، تو چطوری؟"]
    assert texts(sent, 803) == []                                                                   # nobody else hears it


def test_links_ids_and_phone_numbers_are_not_relayed_and_long_text_is_cut(world):
    c, H, bid, sent, msg, tap = chat(world)
    for a in (801, 802):
        tap(a, "m:0"); tap(a, "ac:find")
    for bad in ("برو به https://example.com", "کانال ما @mychannel", "شماره‌ام ۰۹۱۲۱۲۳۴۵۶۷ است", "09121234567", "site.ir رو ببین", "t.me/abc"):
        sent.clear()
        msg(801, bad)
        assert texts(sent, 802) == [] and any("مجاز نیست" in t for t in texts(sent, 801)), bad
    sent.clear()
    msg(801, "ا" * 900)
    assert len(texts(sent, 802)[0]) <= 500 + 3
    sent.clear()
    anon._hits.clear()
    for i in range(anon.RATE + 3):
        msg(801, f"پیام {i}")
    assert any("خیلی سریع" in t for t in texts(sent, 801)) and len(texts(sent, 802)) == anon.RATE


def test_ending_next_and_leaving_by_menu_release_both_sides(world):
    c, H, bid, sent, msg, tap = chat(world)
    for a in (801, 802):
        tap(a, "m:0"); tap(a, "ac:find")
    sent.clear()
    tap(801, "ac:end")
    assert any("گفتگو را پایان داد" in t for t in texts(sent, 802))
    sent.clear()
    msg(802, "هنوز اینجایی؟")                                                                      # no active chat any more
    assert texts(sent, 801) == [] and any("با یک نفر ناشناس" in t for t in texts(sent, 802))          # back at the start, nothing relayed
    with SessionLocal() as db:
        assert db.query(AnonPair).filter(AnonPair.active.is_(True)).count() == 0 and all(p.log == [] for p in db.query(AnonPair))
    # leaving through the menu while paired also ends it
    for a in (801, 802):
        tap(a, "m:0"); tap(a, "ac:find")
    sent.clear()
    msg(801, "/menu")
    assert any("گفتگو را پایان داد" in t for t in texts(sent, 802))
    # "next partner" re-queues the caller; a third customer gets paired with them
    tap(802, "m:0"); tap(802, "ac:find"); tap(801, "m:0"); tap(801, "ac:find")
    sent.clear()
    tap(802, "ac:next"); tap(803, "m:0"); tap(803, "ac:find")
    assert any("شریک گفتگو پیدا شد" in t for t in texts(sent, 803)) and any("شریک گفتگو پیدا شد" in t for t in texts(sent, 802))


def test_report_gives_the_owner_evidence_and_the_owner_can_ban(world):
    c, H, bid, sent, msg, tap = chat(world)
    for a in (801, 802):
        tap(a, "m:0"); tap(a, "ac:find")
    msg(802, "پیام بد")
    msg(801, "سلام")
    sent.clear()
    tap(801, "ac:report")
    assert any("گزارش شما" in t for t in texts(sent, 801)) and any("پایان داد" in t for t in texts(sent, 802))
    recs = c.get(f"/api/bots/{bid}/records?sandbox=false", headers=H).json()
    rep = [r for r in recs if r["data"].get("status") == "reported"][0]["data"]
    assert [l["text"] for l in rep["log"]] == ["پیام بد", "سلام"] and {l["from"] for l in rep["log"]} == {"گزارش‌دهنده", "طرف مقابل"}
    assert "802" not in str(rep) and "bale:" not in str(rep)
    assert c.post(f"/api/bots/{bid}/customers/{rep['reported_id']}/ban", headers=H).status_code == 200
    sent.clear()
    msg(802, "/start", "علی")
    assert any("مسدود" in t for t in texts(sent, 802))
    cust = c.get(f"/api/bots/{bid}/customers", headers=H).json()["items"]
    assert [x["banned"] for x in cust if x["id"] == rep["reported_id"]] == [True]
    assert c.post(f"/api/bots/{bid}/customers/{rep['reported_id']}/unban", headers=H).status_code == 200
    sent.clear()
    msg(802, "/start", "علی")
    assert not any("مسدود" in t for t in texts(sent, 802))
    other = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"username": "q_x.com", "password": "123456"}).json()["token"]}
    assert c.post(f"/api/bots/{bid}/customers/{rep['reported_id']}/ban", headers=other).status_code == 404


def test_waiting_too_long_expires_and_a_ban_ends_a_running_chat(world):
    c, H, bid, sent, msg, tap = chat(world)
    tap(801, "m:0"); tap(801, "ac:find")
    sent.clear()
    with SessionLocal() as db:
        assert outreach.expire_anon_waiting(db, datetime.now(timezone.utc)) == 0
        assert outreach.expire_anon_waiting(db, datetime.now(timezone.utc) + timedelta(minutes=anon.WAIT_MINUTES + 1)) == 1
        assert db.query(AnonQueue).count() == 0
    assert any("کسی برای گفتگو پیدا نشد" in t for t in texts(sent, 801))
    for a in (801, 802):
        tap(a, "m:0"); tap(a, "ac:find")
    with SessionLocal() as db:
        cid = db.query(CustomerSeen).filter(CustomerSeen.key == "bale:801").one().id
    sent.clear()
    assert c.post(f"/api/bots/{bid}/customers/{cid}/ban", headers=H).status_code == 200
    assert any("گفتگو را پایان داد" in t for t in texts(sent, 802))
