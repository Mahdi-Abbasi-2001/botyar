"""The newer features on the Telegram channel: customer tracking and caps, map pin, file note, announcements, join gate, invite links,
forwarding between channels, and an anonymous chat that pairs a Bale customer with a Telegram customer."""
import itertools
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import bale, billing, telegram  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Bot, BotVersion, ChatBinding, CustomerSeen, User, VersionTests  # noqa: E402

ids = itertools.count(1)
SPEC = {"name": "کافه", "welcome": "سلام", "menu": [{"label": "آدرس", "block": "addr"}, {"label": "کاتالوگ", "block": "cat"}, {"label": "دعوت", "block": "ref"}, {"label": "چت", "block": "anon"}],
        "blocks": [{"type": "message", "id": "addr", "text": "آدرس ما", "location": {"latitude": 35.7, "longitude": 51.4}},
                   {"type": "message", "id": "cat", "text": "کاتالوگ", "media": "document"},
                   {"type": "referral", "id": "ref", "title": "دعوت", "goal": 2},
                   {"type": "anon_chat", "id": "anon", "title": "چت"}]}


@pytest.fixture()
def tw(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "public_base_url", "https://example.test")
    monkeypatch.setattr(settings, "bale_shared_bot_token", "BALESHARED")
    monkeypatch.setattr(settings, "telegram_relay_url", "https://relay.example")
    monkeypatch.setattr(settings, "telegram_relay_key", "k")
    monkeypatch.setattr(settings, "telegram_shared_bot_token", "123456:TGSHARED")
    calls = {"bale": [], "tg": []}
    members = {"status": "left"}

    def faker(name):
        def fake(token, method, payload=None, timeout=15):
            calls[name].append((method, dict(payload or {})))
            if method == "getMe":
                return {"username": f"{name}_shared_bot", "id": 5}
            if method == "getChatMember":
                return {"status": members["status"]}
            return True
        return fake

    monkeypatch.setattr(bale, "api_call", faker("bale"))
    monkeypatch.setattr(telegram, "api_call", faker("tg"))
    bale._username_cache.clear(); telegram._username_cache.clear()
    with TestClient(app) as c:
        tok = c.post("/api/auth/register", json={"email": "t@x.com", "password": "123456"}).json()["token"]
        H = {"Authorization": f"Bearer {tok}"}

        def make(spec):
            with SessionLocal() as db:
                uid = db.query(User).filter(User.email == "t@x.com").one().id
                bot = Bot(user_id=uid, name="کافه")
                db.add(bot); db.flush()
                db.add(BotVersion(bot_id=bot.id, version=1, spec=spec, note=""))
                db.add(VersionTests(bot_id=bot.id, version=1, scenarios=[], results=[{"name": "t", "passed": True, "failures": [], "transcript": []}]))
                db.commit()
                return bot.id

        yield c, H, make, calls, members


def tg(c, update):
    update["update_id"] = next(ids) + 500_000
    return c.post(f"/api/tghook/shared/{telegram.shared_hook_secret()}", json=update)


def tg_msg(c, chat, text, name="مشتری"):
    return tg(c, {"message": {"message_id": 1, "from": {"id": chat, "first_name": name}, "chat": {"id": chat, "type": "private"}, "text": text}})


def tg_tap(c, chat, data):
    return tg(c, {"callback_query": {"id": "q", "from": {"id": chat}, "data": data, "message": {"message_id": 7, "chat": {"id": chat, "type": "private"}}}})


def bale_msg(c, chat, text, name="مشتری"):
    return c.post(f"/api/hook/shared/{bale.shared_hook_secret()}", json={"update_id": next(ids) + 600_000, "message": {
        "message_id": 1, "from": {"id": chat, "first_name": name}, "chat": {"id": chat, "type": "private"}, "text": text}})


def bale_tap(c, chat, data):
    return c.post(f"/api/hook/shared/{bale.shared_hook_secret()}", json={"update_id": next(ids) + 600_000, "callback_query": {
        "id": "q", "from": {"id": chat}, "data": data, "message": {"message_id": 7, "chat": {"id": chat, "type": "private"}}}})


def sent(calls, name, chat):
    return [p["text"] for m, p in calls[name] if m == "sendMessage" and str(p["chat_id"]) == str(chat)]


def publish_both(c, H, bid):
    pb = c.post(f"/api/bots/{bid}/publish", json={"mode": "shared"}, headers=H).json()
    pt = c.post(f"/api/bots/{bid}/telegram/publish", json={"mode": "shared"}, headers=H).json()
    return pb, pt


def test_map_pin_and_file_note_on_telegram_and_customer_is_tracked_with_its_channel(tw):
    c, H, make, calls, _ = tw
    bid = make(SPEC)
    pb, pt = publish_both(c, H, bid)
    tg_msg(c, 91, f"/start {pt['code']}", "سارا")
    calls["tg"].clear()
    tg_tap(c, 91, "m:0")
    assert [p for m, p in calls["tg"] if m == "sendLocation"] == [{"chat_id": "91", "latitude": 35.7, "longitude": 51.4}]
    calls["tg"].clear()
    tg_tap(c, 91, "m:1")
    with SessionLocal() as db:   # upload a file so the "not on Telegram" note is reached
        from app.models import BotFile

        db.add(BotFile(bot_id=bid, block_id="cat", kind="document", filename="c.pdf", mime="application/pdf", size=3, data=b"%PD"))
        db.commit()
    calls["tg"].clear()
    tg_tap(c, 91, "m:1")
    assert any("فقط در بله" in t for t in sent(calls, "tg", 91))
    data = c.get(f"/api/bots/{bid}/customers", headers=H).json()
    assert [(i["name"], i["channel"]) for i in data["items"]] == [("سارا", "تلگرام")]


def test_customer_cap_applies_to_telegram_customers_too(tw, monkeypatch):
    c, H, make, calls, _ = tw
    monkeypatch.setitem(billing.PLANS["free"], "customers", 1)
    bid = make(SPEC)
    pb, pt = publish_both(c, H, bid)
    bale_msg(c, 71, f"/start {pb['code']}")
    calls["tg"].clear()
    tg_msg(c, 92, f"/start {pt['code']}")
    assert billing.FULL_TEXT in sent(calls, "tg", 92)


def test_announcement_reaches_bale_and_telegram_customers(tw):
    c, H, make, calls, _ = tw
    bid = make(SPEC)
    pb, pt = publish_both(c, H, bid)
    bale_msg(c, 72, f"/start {pb['code']}")
    tg_msg(c, 93, f"/start {pt['code']}")
    r = c.post(f"/api/bots/{bid}/broadcasts", json={"text": "تخفیف ویژه"}, headers=H)
    assert r.status_code == 200 and r.json()["audience"] == 2
    import time

    time.sleep(0.5)
    assert any("تخفیف ویژه" in t for t in sent(calls, "bale", 72)) and any("تخفیف ویژه" in t for t in sent(calls, "tg", 93))


def test_join_gate_on_telegram_uses_a_telegram_link(tw):
    c, H, make, calls, members = tw
    bid = make({**SPEC, "gate": {"channel": "@mycafe_channel"}})
    pb, pt = publish_both(c, H, bid)
    calls["tg"].clear()
    tg_msg(c, 94, f"/start {pt['code']}")
    markup = [p for m, p in calls["tg"] if m == "sendMessage" and p["chat_id"] == "94"][-1]["reply_markup"]["inline_keyboard"]
    assert markup[0][0]["url"] == "https://t.me/mycafe_channel" and markup[1][0]["callback_data"] == "gate:check"
    members["status"] = "member"
    calls["tg"].clear()
    tg_tap(c, 94, "gate:check")
    assert any("سلام" in t for t in sent(calls, "tg", 94))


def test_invite_link_on_telegram_is_a_t_me_link_and_counts_a_new_telegram_customer(tw):
    c, H, make, calls, _ = tw
    bid = make(SPEC)
    pb, pt = publish_both(c, H, bid)
    tg_msg(c, 95, f"/start {pt['code']}", "سارا")
    calls["tg"].clear()
    tg_tap(c, 95, "m:2")
    link = [t for t in sent(calls, "tg", 95) if "start=" in t][0]
    assert "https://t.me/tg_shared_bot?start=r" in link
    code = link.split("start=")[1].split()[0]
    calls["tg"].clear()
    tg_msg(c, 96, f"/start {code}", "علی")
    assert any("یک نفر با لینک اختصاصی شما وارد شد" in t for t in sent(calls, "tg", 95))


def test_forwarding_between_two_telegram_channels_uses_copy_message(tw):
    c, H, make, calls, _ = tw
    bid = make(SPEC)
    publish_both(c, H, bid)
    with SessionLocal() as db:
        a = ChatBinding(bot_id=bid, ch="tg", chat_id="-1001", kind="channel", title="A")
        b = ChatBinding(bot_id=bid, ch="tg", chat_id="-1002", kind="channel", title="B")
        db.add_all([a, b]); db.commit()
        aid, bid2 = a.id, b.id
    assert c.post(f"/api/bots/{bid}/forwards", json={"source": aid, "dest": bid2}, headers=H).status_code == 200
    calls["tg"].clear()
    tg(c, {"channel_post": {"message_id": 33, "chat": {"id": -1001, "type": "channel", "title": "A"}, "text": "خبر"}})
    assert [p for m, p in calls["tg"] if m == "copyMessage"] == [{"chat_id": "-1002", "from_chat_id": "-1001", "message_id": 33}]


def test_anonymous_chat_pairs_a_bale_customer_with_a_telegram_customer(tw):
    c, H, make, calls, _ = tw
    bid = make(SPEC)
    pb, pt = publish_both(c, H, bid)
    bale_msg(c, 73, f"/start {pb['code']}", "سارا")
    tg_msg(c, 97, f"/start {pt['code']}", "علی")
    bale_tap(c, 73, "m:3"); bale_tap(c, 73, "ac:find")
    calls["bale"].clear(); calls["tg"].clear()
    tg_tap(c, 97, "m:3"); tg_tap(c, 97, "ac:find")
    assert any("شریک گفتگو پیدا شد" in t for t in sent(calls, "bale", 73)) and any("شریک گفتگو پیدا شد" in t for t in sent(calls, "tg", 97))
    calls["tg"].clear()
    bale_msg(c, 73, "سلام از بله")
    assert sent(calls, "tg", 97) == ["👤 سلام از بله"] and "سارا" not in str(calls["tg"])
    calls["bale"].clear()
    tg_msg(c, 97, "سلام از تلگرام")
    assert sent(calls, "bale", 73) == ["👤 سلام از تلگرام"]
