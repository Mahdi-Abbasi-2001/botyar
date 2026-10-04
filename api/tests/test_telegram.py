"""Telegram channel: same engine as Bale, reached through the relay. No network: both messengers' API calls are faked."""
import itertools
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import bale, outreach, telegram  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

uid = itertools.count(5000)


@pytest.fixture()
def env(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "public_base_url", "https://example.test")
    monkeypatch.setattr(settings, "bale_shared_bot_token", "BALESHARED")
    monkeypatch.setattr(settings, "telegram_relay_url", "https://relay.example")
    monkeypatch.setattr(settings, "telegram_relay_key", "relay-key")
    monkeypatch.setattr(settings, "telegram_shared_bot_token", "123456:TGSHARED")
    monkeypatch.setattr(outreach, "PACE_SECONDS", 0)
    monkeypatch.setattr(outreach.threading, "Thread", lambda target, args=(), **kw: type("T", (), {"start": lambda self: target(*args)})())
    calls = {"bale": [], "tg": []}

    def faker(name):
        def fake(token, method, payload=None, timeout=15):
            if name == "tg" and token == "999:BAD":
                raise bale.BaleError("Unauthorized")
            calls[name].append((token, method, payload or {}))
            if method == "getMe":
                return {"username": "botyar_tg_bot" if name == "tg" else "botyar_test_bot"}
            return True
        return fake

    monkeypatch.setattr(bale, "api_call", faker("bale"))
    monkeypatch.setattr(telegram, "api_call", faker("tg"))
    bale._username_cache.clear()
    telegram._username_cache.clear()
    bale._seen.clear()  # the duplicate-update guard is process-wide; don't let our update ids hide other suites' updates
    with TestClient(app) as c:
        yield c, calls
    bale._seen.clear()


def owner(c, email="tg@x.com", template="workshop"):
    tok = c.post("/api/auth/register", json={"email": email, "password": "123456"}).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    return H, c.post("/api/bots", json={"template": template}, headers=H).json()["id"]


def msg(chat, text):
    return {"update_id": next(uid), "message": {"message_id": 1, "chat": {"id": chat, "type": "private"}, "from": {"id": chat, "first_name": "سارا"}, "text": text}}


def cb(chat, data):
    return {"update_id": next(uid), "callback_query": {"id": "q", "from": {"id": chat}, "data": data,
                                                       "message": {"message_id": 7, "chat": {"id": chat, "type": "private"}}}}


def sent(calls, chat):
    return [p for _, m, p in calls if m == "sendMessage" and str(p["chat_id"]) == str(chat)]


def test_shared_telegram_bot_full_journey_through_the_relay(env):
    c, calls = env
    H, bot = owner(c)
    st = c.get(f"/api/bots/{bot}/telegram", headers=H).json()
    assert st["enabled"] and not st["published"] and st["shared_bot_username"] == "botyar_tg_bot"
    st = c.post(f"/api/bots/{bot}/telegram/publish", json={"mode": "shared"}, headers=H).json()
    assert st["published"] and st["mode"] == "shared" and len(st["code"]) == 6
    url = f"/api/tghook/shared/{telegram.shared_hook_secret()}"
    assert c.post("/api/tghook/shared/wrong", json=msg(1, "hi")).status_code == 404

    # Telegram deep link: t.me/<bot>?start=CODE arrives as "/start CODE"
    c.post(url, json=msg(111, f"/start {st['code']}"))
    out = sent(calls["tg"], 111)
    assert "خوش آمدید" in out[-2]["text"] and out[-1]["reply_markup"]["inline_keyboard"]

    c.post(url, json=msg(999, f"/admin {st['admin_code']}"))
    assert c.get(f"/api/bots/{bot}/telegram", headers=H).json()["admin_linked"] is True

    for step in [cb(111, "m:0"), cb(111, "s:thu1"), msg(111, "علی"), msg(111, "۰۹۱۲۳۴۵۶۷۸۹")]:
        c.post(url, json=step)
    assert any(m == "answerCallbackQuery" for _, m, _ in calls["tg"])
    assert "با موفقیت" in sent(calls["tg"], 111)[-2]["text"]
    assert "🔔" in sent(calls["tg"], 999)[-1]["text"]
    assert not any(m in ("sendMessage", "answerCallbackQuery") for _, m, _ in calls["bale"])  # no chat traffic leaked to Bale

    live = c.get(f"/api/bots/{bot}/records?sandbox=false", headers=H).json()
    assert len(live) == 1 and live[0]["data"]["phone"] == "09123456789"
    from app.db import SessionLocal
    from app.models import Record

    with SessionLocal() as db:  # the customer is remembered as a Telegram customer (the API hides "_" fields)
        assert db.get(Record, live[0]["id"]).data["_cust"] == "tg:111"


def test_one_code_works_on_both_messengers(env):
    c, _ = env
    H, bot = owner(c)
    code = c.post(f"/api/bots/{bot}/publish", json={"mode": "shared"}, headers=H).json()["code"]
    assert c.post(f"/api/bots/{bot}/telegram/publish", json={"mode": "shared"}, headers=H).json()["code"] == code


def test_own_telegram_token_registers_the_relay_webhook(env):
    c, calls = env
    H, bot = owner(c)
    r = c.post(f"/api/bots/{bot}/telegram/publish", json={"mode": "own", "token": "999:BAD"}, headers=H)
    assert r.status_code == 400
    st = c.post(f"/api/bots/{bot}/telegram/publish", json={"mode": "own", "token": "777:GOODTOKEN"}, headers=H).json()
    assert st["mode"] == "own" and st["bot_username"] == "botyar_tg_bot"
    hook = [p for t, m, p in calls["tg"] if m == "setWebhook" and t == "777:GOODTOKEN"][-1]
    assert hook["url"].startswith("https://relay.example/hook/own/")  # Telegram must reach us through the relay
    path = hook["url"].split("/hook/", 1)[1]
    assert c.post(f"/api/tghook/{path}", json=msg(55, "/start")).status_code == 200
    assert "خوش آمدید" in sent(calls["tg"], 55)[-2]["text"]
    pub_id = path.split("/")[1]
    assert c.post(f"/api/tghook/own/{pub_id}/wrongsecret", json=msg(55, "/start")).status_code == 404

    # unpublishing removes the webhook and the status
    c.post(f"/api/bots/{bot}/telegram/unpublish", json={}, headers=H)
    assert any(m == "deleteWebhook" and t == "777:GOODTOKEN" for t, m, _ in calls["tg"])
    assert c.get(f"/api/bots/{bot}/telegram", headers=H).json()["published"] is False


def test_telegram_is_off_without_a_relay(env, monkeypatch):
    c, _ = env
    monkeypatch.setattr(settings, "telegram_relay_url", "")
    H, bot = owner(c)
    assert c.get(f"/api/bots/{bot}/telegram", headers=H).json()["enabled"] is False
    assert c.post(f"/api/bots/{bot}/telegram/publish", json={"mode": "shared"}, headers=H).status_code == 503


def test_other_owners_cannot_touch_telegram_publishing(env):
    c, _ = env
    _, bot = owner(c, "a@x.com")
    H2, _ = owner(c, "b@x.com")
    assert c.get(f"/api/bots/{bot}/telegram", headers=H2).status_code == 404
    assert c.post(f"/api/bots/{bot}/telegram/publish", json={"mode": "shared"}, headers=H2).status_code == 404
    assert c.post(f"/api/bots/{bot}/telegram/unpublish", json={}, headers=H2).status_code == 404


def test_customer_messages_go_out_on_their_own_messenger(env):
    c, calls = env
    H, bot = owner(c)
    c.post(f"/api/bots/{bot}/publish", json={"mode": "shared"}, headers=H)
    c.post(f"/api/bots/{bot}/telegram/publish", json={"mode": "shared"}, headers=H)
    from app.db import SessionLocal

    with SessionLocal() as db:
        n = bale.send_customer_actions(db, bot, [
            {"type": "notify_customer", "cust": "bale:10", "text": "برای بله"},
            {"type": "notify_customer", "cust": "tg:20", "text": "برای تلگرام"},
            {"type": "notify_customer", "cust": "sim:x", "text": "شبیه‌ساز"},
        ])
    assert n == 2
    assert [p["text"] for p in sent(calls["bale"], 10)] == ["برای بله"]
    assert [p["text"] for p in sent(calls["tg"], 20)] == ["برای تلگرام"]
    assert sent(calls["bale"], 20) == [] and sent(calls["tg"], 10) == []


def test_announcement_reaches_customers_on_both_messengers(env):
    c, calls = env
    H, bot = owner(c)
    code = c.post(f"/api/bots/{bot}/publish", json={"mode": "shared"}, headers=H).json()["code"]
    c.post(f"/api/bots/{bot}/telegram/publish", json={"mode": "shared"}, headers=H)
    c.post(f"/api/hook/shared/{bale.shared_hook_secret()}", json=msg(301, f"/start {code}"))
    tg = f"/api/tghook/shared/{telegram.shared_hook_secret()}"
    c.post(tg, json=msg(401, f"/start {code}"))
    c.post(tg, json=msg(402, f"/start {code}"))
    c.post(tg, json=msg(402, "/stop"))
    assert c.get(f"/api/bots/{bot}/broadcasts", headers=H).json()["audience"] == 2
    r = c.post(f"/api/bots/{bot}/broadcasts", json={"text": "تخفیف ویژه"}, headers=H)
    assert r.status_code == 200 and r.json()["audience"] == 2
    assert any("تخفیف" in p["text"] for p in sent(calls["bale"], 301))
    assert any("تخفیف" in p["text"] for p in sent(calls["tg"], 401))
    assert not any("تخفیف" in p["text"] for p in sent(calls["tg"], 402))
    assert c.get(f"/api/bots/{bot}/broadcasts", headers=H).json()["items"][0]["sent"] == 2


def test_place_freed_on_bale_goes_to_the_waiting_telegram_customer(env):
    from app.db import SessionLocal
    from app.models import Bot, BotVersion, User

    c, calls = env
    H, _ = owner(c, "wl@x.com")
    spec = {"name": "کلاس", "welcome": "سلام", "menu": [{"label": "ثبت‌نام", "block": "b"}],
            "blocks": [{"type": "booking", "id": "b", "title": "ثبت‌نام کلاس", "waitlist": True, "allow_cancel": True,
                        "slots": [{"id": "once", "label": "کارگاه ویژه", "capacity": 1}]}]}
    with SessionLocal() as db:
        uid = db.query(User).filter(User.email == "wl@x.com").one().id
        bot = Bot(user_id=uid, name="کلاس")
        db.add(bot)
        db.flush()
        db.add(BotVersion(bot_id=bot.id, version=1, spec=spec, note=""))
        db.commit()
        bid = bot.id
    code = c.post(f"/api/bots/{bid}/publish", json={"mode": "shared"}, headers=H).json()["code"]
    c.post(f"/api/bots/{bid}/telegram/publish", json={"mode": "shared"}, headers=H)
    bale_url, tg_url = f"/api/hook/shared/{bale.shared_hook_secret()}", f"/api/tghook/shared/{telegram.shared_hook_secret()}"
    for url, chat, phone in ((bale_url, 901, "09120000001"), (tg_url, 902, "09120000002")):  # Bale takes the place, Telegram waits
        c.post(url, json=msg(chat, f"/start {code}"))
        for step in (cb(chat, "m:0"), cb(chat, "s:once"), msg(chat, "مشتری"), msg(chat, phone)):
            c.post(url, json=step)
    assert "لیست انتظار" in sent(calls["tg"], 902)[-2]["text"]
    rid = next(r["id"] for r in c.get(f"/api/bots/{bid}/records?sandbox=false", headers=H).json() if r["data"]["status"] == "confirmed")
    calls["tg"].clear()
    c.post(bale_url, json=cb(901, "m:1"))           # «ثبت‌های من» on Bale
    c.post(bale_url, json=cb(901, f"x:0:{rid}"))
    c.post(bale_url, json=cb(901, "xy"))            # confirm the cancellation
    promo = sent(calls["tg"], 902)                  # the freed place reached the Telegram customer, on Telegram
    assert len(promo) == 1 and "جای خالی شد" in promo[0]["text"]
    assert sent(calls["bale"], 902) == []
    live = {r["data"]["phone"]: r["data"]["status"] for r in c.get(f"/api/bots/{bid}/records?sandbox=false", headers=H).json()}
    assert live == {"09120000001": "cancelled", "09120000002": "confirmed"}


def test_telegram_chats_never_get_payment_invoices(env):
    c, calls = env
    H, bot = owner(c, template="cafe")
    c.put(f"/api/bots/{bot}/payment", json={"wallet_token": "WALLET-TEST-1111111111111111"}, headers=H)
    code = c.post(f"/api/bots/{bot}/telegram/publish", json={"mode": "shared"}, headers=H).json()["code"]
    c.post(f"/api/tghook/shared/{telegram.shared_hook_secret()}", json=msg(77, f"/start {code}"))
    from app.db import SessionLocal
    from app.models import ChatSession

    with SessionLocal() as db:
        st = db.query(ChatSession).filter(ChatSession.key == "tg:77").one().state
    assert st["pay_ok"] is False
    assert not any(m == "sendInvoice" for _, m, _ in calls["tg"])
