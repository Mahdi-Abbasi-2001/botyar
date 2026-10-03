import itertools
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import bale  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

uid = itertools.count(1000)


@pytest.fixture()
def env(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "public_base_url", "https://example.test")
    monkeypatch.setattr(settings, "bale_shared_bot_token", "SHAREDTOKEN")
    calls: list[tuple[str, dict]] = []

    def fake(token, method, payload=None, timeout=15):
        calls.append((method, payload or {}))
        if method == "getMe":
            return {"username": "botyar_test_bot"}
        return True

    monkeypatch.setattr(bale, "api_call", fake)
    bale._username_cache.clear()
    with TestClient(app) as c:
        yield c, calls


def msg(chat, text):
    return {"update_id": next(uid), "message": {"message_id": 1, "chat": {"id": chat, "type": "private"}, "text": text}}


def cb(chat, data):
    return {"update_id": next(uid), "callback_query": {"id": "q1", "from": {"id": chat}, "data": data,
                                                       "message": {"chat": {"id": chat, "type": "private"}}}}


def sent(calls, chat):
    return [p for m, p in calls if m == "sendMessage" and str(p["chat_id"]) == str(chat)]


def test_shared_bot_full_journey(env):
    c, calls = env
    tok = c.post("/api/auth/register", json={"email": "o@x.com", "password": "123456"}).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    bot = c.post("/api/bots", json={"template": "workshop"}, headers=H).json()["id"]
    st = c.post(f"/api/bots/{bot}/publish", json={"mode": "shared"}, headers=H).json()
    assert st["published"] and st["mode"] == "shared" and len(st["code"]) == 6 and st["shared_bot_username"] == "botyar_test_bot"
    url = f"/api/hook/shared/{bale.shared_hook_secret()}"

    assert c.post("/api/hook/shared/wrong", json=msg(1, "hi")).status_code == 404

    # unknown chat is asked for the code
    c.post(url, json=msg(111, "/start"))
    assert "کد ربات" in sent(calls, 111)[-1]["text"]
    # sending the code opens the bot: welcome + menu with inline buttons
    c.post(url, json=msg(111, st["code"].lower()))
    out = sent(calls, 111)
    assert "خوش آمدید" in out[-2]["text"] and len(out[-1]["reply_markup"]["inline_keyboard"]) == 2

    # owner links their chat for notifications
    c.post(url, json=msg(999, f"/admin {st['admin_code']}"))
    assert c.get(f"/api/bots/{bot}/publication", headers=H).json()["admin_linked"] is True
    c.post(url, json=msg(999, "/admin WRONGCODE"))
    assert "نامعتبر" in sent(calls, 999)[-1]["text"]

    # customer books via buttons; callback queries are acknowledged
    for step in [cb(111, "m:0"), cb(111, "s:thu1"), msg(111, "علی"), msg(111, "۰۹۱۲۳۴۵۶۷۸۹")]:
        c.post(url, json=step)
    assert any(m == "answerCallbackQuery" for m, _ in calls)
    assert "با موفقیت" in sent(calls, 111)[-2]["text"]
    assert "🔔" in sent(calls, 999)[-1]["text"] and "علی" in sent(calls, 999)[-1]["text"]

    live = c.get(f"/api/bots/{bot}/records?sandbox=false", headers=H).json()
    assert len(live) == 1 and live[0]["data"]["phone"] == "09123456789"
    assert c.get(f"/api/bots/{bot}/records?sandbox=true", headers=H).json() == []

    # /switch forgets the link
    c.post(url, json=msg(111, "/switch"))
    c.post(url, json=msg(111, "m:0"))
    assert "کد ربات" in sent(calls, 111)[-1]["text"]


def test_duplicate_delivery_is_ignored(env):
    c, calls = env
    tok = c.post("/api/auth/register", json={"email": "d@x.com", "password": "123456"}).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    bot = c.post("/api/bots", json={"template": "cafe"}, headers=H).json()["id"]
    code = c.post(f"/api/bots/{bot}/publish", json={"mode": "shared"}, headers=H).json()["code"]
    url = f"/api/hook/shared/{bale.shared_hook_secret()}"
    same = msg(222, code)
    c.post(url, json=same)
    n = len(sent(calls, 222))
    c.post(url, json=same)  # Bale retry of the very same update
    assert len(sent(calls, 222)) == n


def test_long_button_data_gets_a_short_token():
    long_label = "گزینه‌ای با نام خیلی خیلی طولانی فارسی که از شصت و چهار بایت بیشتر است"
    store: dict = {}
    mk = bale.to_markup([{"text": long_label, "data": long_label}, {"text": "کوتاه", "data": "m:0"}], store)
    d0 = mk["inline_keyboard"][0][0]["callback_data"]
    assert d0 == "~0" and store["~0"] == long_label and len(d0.encode()) <= 64
    assert mk["inline_keyboard"][1][0]["callback_data"] == "m:0"


def test_cannot_publish_when_tests_fail(env):
    from app.db import SessionLocal
    from app.models import VersionTests

    c, _ = env
    tok = c.post("/api/auth/register", json={"email": "f@x.com", "password": "123456"}).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    bot = c.post("/api/bots", json={"template": "cafe"}, headers=H).json()["id"]
    with SessionLocal() as db:
        db.add(VersionTests(bot_id=bot, version=1, scenarios=[], results=[{"name": "x", "passed": False, "failures": ["boom"], "transcript": []}]))
        db.commit()
    r = c.post(f"/api/bots/{bot}/publish", json={"mode": "shared"}, headers=H)
    assert r.status_code == 409 and "تست" in r.json()["detail"]
