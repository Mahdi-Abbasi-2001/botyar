"""Staff members link their own chat («/staff CODE») and hear about their own bookings; nobody else's."""
import itertools
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import bale, testing  # noqa: E402
from app.config import settings  # noqa: E402
from app.dates import TEST_NOW  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.engine import MemoryStore, cancel_record, handle, new_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import BotVersion, StaffLink  # noqa: E402
from app.spec import BotSpec  # noqa: E402

SPEC = {"name": "سالن", "welcome": "سلام", "menu": [{"label": "نوبت", "block": "b"}],
        "blocks": [{"type": "booking", "id": "b", "title": "نوبت‌دهی", "allow_cancel": True,
                    "schedule": {"days": [{"weekday": 1, "start": "09:00", "end": "12:00"}], "duration_minutes": 60, "staff": ["سارا", "مینا"]}}]}
uid = itertools.count(5000)


def test_a_booking_and_its_cancellation_tell_that_staff_member_only():
    spec, store, s = BotSpec.model_validate(SPEC), MemoryStore(), new_session()
    s["cust"] = "bale:1"
    out = [a for t in ["/start", "m:0", "f:0", "d:20261004", "t:0900", "علی", "09121234567"] for a in handle(spec, s, t, store, TEST_NOW)]
    staff = [a for a in out if a["type"] == "notify_staff"]
    assert len(staff) == 1 and staff[0]["staff"] == "سارا" and "نوبت تازه برای شما" in staff[0]["text"]
    assert "نوبت تازه برای شما" not in testing._texts(out)  # never shown to the customer (nor in the agent's tests)
    actions, _ = cancel_record(spec, store, TEST_NOW, spec.blocks[0], store.find("b")[0], by="owner", reason="بیماری")
    assert any(a["type"] == "notify_staff" and a["staff"] == "سارا" and "توسط مدیر لغو شد" in a["text"] for a in actions)


@pytest.fixture()
def env(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "public_base_url", "https://example.test")
    monkeypatch.setattr(settings, "bale_shared_bot_token", "SHAREDTOKEN")
    calls = []
    monkeypatch.setattr(bale, "api_call", lambda token, method, payload=None, timeout=15: calls.append((method, payload or {})) or ({"username": "botyar_test_bot"} if method == "getMe" else True))
    bale._username_cache.clear()
    with TestClient(app) as c:
        H = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"username": "salon", "password": "123456"}).json()["token"]}
        bot = c.post("/api/bots", json={"template": "cafe"}, headers=H).json()["id"]
        with SessionLocal() as db:
            db.query(BotVersion).filter_by(bot_id=bot).first().spec = SPEC
            db.commit()
        c.post(f"/api/bots/{bot}/publish", json={"mode": "shared"}, headers=H)
        yield c, H, bot, calls


def msg(chat, text):
    return {"update_id": next(uid), "message": {"message_id": 1, "chat": {"id": chat, "type": "private"}, "text": text}}


def sent_to(calls, chat):
    return [p["text"] for m, p in calls if m == "sendMessage" and str(p.get("chat_id")) == str(chat)]


def test_staff_link_with_a_code_and_get_their_own_bookings(env):
    c, H, bot, calls = env
    staff = c.get(f"/api/bots/{bot}/staff", headers=H).json()
    assert [s["name"] for s in staff] == ["سارا", "مینا"] and all(s["code"].startswith("S") and not s["linked"] for s in staff)
    hook = f"/api/hook/shared/{bale.shared_hook_secret()}"
    c.post(hook, json=msg(900, "/staff WRONG1"))
    assert "کد همکار نامعتبر است" in sent_to(calls, 900)[-1]
    c.post(hook, json=msg(900, f"/staff {staff[0]['code'].lower()}"))
    assert "نوبت‌های «سارا»" in sent_to(calls, 900)[-1]
    assert c.get(f"/api/bots/{bot}/staff", headers=H).json()[0] == {"name": "سارا", "code": staff[0]["code"], "linked": True, "messenger": "bale"}

    with SessionLocal() as db:   # a live chat turn: the engine's staff notice reaches Sara's chat, not Mina's
        bale.deliver("SHAREDTOKEN", "77", [{"type": "notify_staff", "staff": "سارا", "text": "📅 نوبت تازه"}], {}, bot_id=bot, db=db)
        bale.deliver("SHAREDTOKEN", "77", [{"type": "notify_staff", "staff": "مینا", "text": "📅 مال مینا"}], {}, bot_id=bot, db=db)
        assert sent_to(calls, 900)[-1] == "📅 نوبت تازه"
        assert bale.send_customer_actions(db, bot, [{"type": "notify_staff", "staff": "سارا", "text": "❌ لغو توسط مدیر"}]) == 1  # from the dashboard
    assert sent_to(calls, 900)[-1] == "❌ لغو توسط مدیر"


def test_reset_unlinks_and_gives_a_new_code(env):
    c, H, bot, calls = env
    old = c.get(f"/api/bots/{bot}/staff", headers=H).json()[1]
    c.post(f"/api/hook/shared/{bale.shared_hook_secret()}", json=msg(901, f"/staff {old['code']}"))
    new = c.post(f"/api/bots/{bot}/staff/reset", json={"name": "مینا"}, headers=H).json()[1]
    assert new["code"] != old["code"] and not new["linked"]
    with SessionLocal() as db:
        assert db.query(StaffLink).filter_by(name="مینا").first().chat_id == ""
