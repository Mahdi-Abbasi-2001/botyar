"""Reminders (once, before the start, never for late bookings) and owner announcements (audience, /stop, daily limit, isolation)."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from datetime import timedelta  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import bale, outreach  # noqa: E402
from app.config import settings  # noqa: E402
from app.dates import TEST_NOW  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Bot, BotVersion, Broadcast, ChatSession, User  # noqa: E402

SPEC = {"name": "سالن", "welcome": "سلام", "menu": [{"label": "نوبت", "block": "b"}],
        "blocks": [{"type": "booking", "id": "b", "title": "نوبت", "reminder_hours": 24, "allow_cancel": True,
                    "schedule": {"days": [{"weekday": 1, "start": "09:00", "end": "13:00"}], "duration_minutes": 60, "capacity": 1, "days_ahead": 8}},
                   {"type": "admin_notify", "id": "n", "on": "b", "text": "نوبت جدید"}]}
SUN = "20261004"


@pytest.fixture()
def world(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    bale._seen.clear()
    monkeypatch.setattr(settings, "public_base_url", "https://example.test")
    monkeypatch.setattr(settings, "bale_shared_bot_token", "SHAREDTOKEN")
    monkeypatch.setattr(outreach, "PACE_SECONDS", 0)
    sent = []

    def fake(token, method, payload=None, timeout=15):
        if method == "sendMessage":
            sent.append((str(payload["chat_id"]), payload["text"]))
        return {"username": "botyar_test_bot"} if method == "getMe" else True

    monkeypatch.setattr(bale, "api_call", fake)
    monkeypatch.setattr(outreach.threading, "Thread", lambda target, args=(), **kw: type("T", (), {"start": lambda self: target(*args)})())
    with TestClient(app) as c:
        tok = c.post("/api/auth/register", json={"email": "o@x.com", "password": "123456"}).json()["token"]
        H = {"Authorization": f"Bearer {tok}"}
        with SessionLocal() as db:
            uid = db.query(User).filter(User.email == "o@x.com").one().id
            bot = Bot(user_id=uid, name="سالن")
            db.add(bot)
            db.flush()
            db.add(BotVersion(bot_id=bot.id, version=1, spec=SPEC, note=""))
            db.commit()
            bid = bot.id
        pub = c.post(f"/api/bots/{bid}/publish", json={"mode": "shared"}, headers=H).json()
        yield c, H, bid, pub, sent


def hook(c):
    n = [9000]

    def post(update):
        n[0] += 1
        update["update_id"] = n[0]
        return c.post(f"/api/hook/shared/{bale.shared_hook_secret()}", json=update)

    def msg(chat, text):
        return post({"message": {"message_id": 1, "from": {"id": chat, "first_name": "x"}, "chat": {"id": chat, "type": "private"}, "text": text}})

    def tap(chat, data):
        return post({"callback_query": {"id": "q", "from": {"id": chat}, "data": data, "message": {"message_id": 7, "chat": {"id": chat, "type": "private"}}}})

    return msg, tap


def add_booking(bid, chat, booked_at, status="confirmed"):
    from app.models import Record

    with SessionLocal() as db:
        db.add(Record(bot_id=bid, collection="b", sandbox=False, data={
            "slot": "appt", "slot_label": "یکشنبه 1405/07/12 ساعت 09:00", "date": "2026-10-04", "time": "09:00", "name": "علی", "phone": "09121234567",
            "status": status, "_cust": f"bale:{chat}", "_at": booked_at.isoformat()}))
        db.commit()


def test_reminder_is_sent_once_when_due_and_not_before(world):
    c, H, bid, pub, sent = world
    add_booking(bid, 502, TEST_NOW - timedelta(days=3))
    with SessionLocal() as db:
        sent.clear()
        assert outreach.due_reminders(db, TEST_NOW - timedelta(days=2)) == 0 and sent == []        # 57 h before: too early
        assert outreach.due_reminders(db, TEST_NOW) == 1                                          # 21 h before: due
        assert len(sent) == 1 and sent[0][0] == "502" and "یادآوری" in sent[0][1] and "ساعت ۰۹:۰۰" in sent[0][1]
        assert outreach.due_reminders(db, TEST_NOW + timedelta(hours=2)) == 0 and len(sent) == 1   # never twice


def test_a_booking_made_inside_the_window_gets_no_pointless_reminder(world):
    c, H, bid, pub, sent = world
    add_booking(bid, 503, TEST_NOW - timedelta(hours=1))                                          # booked 20 h before the start
    with SessionLocal() as db:
        sent.clear()
        assert outreach.due_reminders(db, TEST_NOW) == 0 and sent == []


def test_cancelled_waitlisted_and_started_bookings_are_not_reminded(world):
    c, H, bid, pub, sent = world
    add_booking(bid, 504, TEST_NOW - timedelta(days=3), "cancelled")
    add_booking(bid, 505, TEST_NOW - timedelta(days=3), "waitlisted")
    with SessionLocal() as db:
        sent.clear()
        assert outreach.due_reminders(db, TEST_NOW) == 0
        add_booking(bid, 506, TEST_NOW - timedelta(days=3))
        assert outreach.due_reminders(db, TEST_NOW + timedelta(hours=22)) == 0                    # appointment already started


def test_broadcast_reaches_active_customers_only_and_stop_works(world):
    c, H, bid, pub, sent = world
    msg, tap = hook(c)
    for chat in (601, 602, 603):
        msg(chat, f"/start {pub['code']}")
    msg(602, "/stop")
    assert c.get(f"/api/bots/{bid}/broadcasts", headers=H).json()["audience"] == 2
    sent.clear()
    r = c.post(f"/api/bots/{bid}/broadcasts", json={"text": "تخفیف ویژه این هفته"}, headers=H)
    assert r.status_code == 200 and r.json()["audience"] == 2
    got = sorted(chat for chat, t in sent if "تخفیف" in t)
    assert got == ["601", "603"] and all("/stop" in t for _, t in sent)
    info = c.get(f"/api/bots/{bid}/broadcasts", headers=H).json()
    assert info["items"][0]["sent"] == 2 and info["items"][0]["done"] is True
    msg(602, "/resume")
    assert c.get(f"/api/bots/{bid}/broadcasts", headers=H).json()["audience"] == 3
    msg(602, "/start")                                              # welcome resets the chat but /stop survives a restart of the chat
    msg(603, "/stop")
    msg(603, "/start")
    assert c.get(f"/api/bots/{bid}/broadcasts", headers=H).json()["audience"] == 2


def test_broadcast_limits_and_authorization(world):
    c, H, bid, pub, sent = world
    msg, _ = hook(c)
    assert c.post(f"/api/bots/{bid}/broadcasts", json={"text": "سلام"}, headers=H).status_code == 409      # nobody yet
    msg(701, f"/start {pub['code']}")
    for i in range(3):
        assert c.post(f"/api/bots/{bid}/broadcasts", json={"text": f"پیام {i}"}, headers=H).status_code == 200
    assert c.post(f"/api/bots/{bid}/broadcasts", json={"text": "چهارم"}, headers=H).status_code == 429
    assert c.post(f"/api/bots/{bid}/broadcasts", json={"text": "x" * 1001}, headers=H).status_code == 422
    tok2 = c.post("/api/auth/register", json={"email": "z@x.com", "password": "123456"}).json()["token"]
    H2 = {"Authorization": f"Bearer {tok2}"}
    assert c.get(f"/api/bots/{bid}/broadcasts", headers=H2).status_code == 404
    assert c.post(f"/api/bots/{bid}/broadcasts", json={"text": "هک"}, headers=H2).status_code == 404
    assert c.get(f"/api/bots/{bid}/broadcasts").status_code in (401, 403)
