"""Scheduled announcements: one-time and daily, Tehran time, limits, delivery only to opted-in customers, authorisation."""
from datetime import datetime, timedelta, timezone

from app import outreach
from app.db import SessionLocal
from app.models import ScheduledBroadcast

from tests.test_outreach import hook, world  # noqa: F401  (the fixture builds a published bot with a fake Bale)


def setup(world):
    c, H, bid, pub, sent = world
    msg, _ = hook(c)
    for chat in (801, 802):
        msg(chat, f"/start {pub['code']}")
    msg(802, "/stop")
    return c, H, bid, pub, sent


def tehran(dt_utc):
    return dt_utc.astimezone(outreach.TEHRAN).strftime("%Y-%m-%dT%H:%M")


def test_one_time_announcement_is_created_listed_run_once_and_reaches_only_opted_in_customers(world):
    c, H, bid, pub, sent = setup(world)
    soon = datetime.now(timezone.utc) + timedelta(minutes=5)
    r = c.post(f"/api/bots/{bid}/scheduled", json={"text": "تخفیف آخر هفته", "mode": "once", "at": tehran(soon)}, headers=H)
    assert r.status_code == 200 and r.json()["mode"] == "once" and r.json()["active"] is True
    assert len(c.get(f"/api/bots/{bid}/scheduled", headers=H).json()["items"]) == 1
    sent.clear()
    with SessionLocal() as db:
        assert outreach.due_scheduled(db, datetime.now(timezone.utc)) == 0                          # not yet
        assert outreach.due_scheduled(db, soon + timedelta(minutes=2)) == 1
        assert outreach.due_scheduled(db, soon + timedelta(minutes=3)) == 0                          # one-time: never again
    got = [chat for chat, t in sent if "تخفیف آخر هفته" in t]
    assert got == ["801"]                                                                           # 802 sent /stop
    item = c.get(f"/api/bots/{bid}/scheduled", headers=H).json()["items"][0]
    assert item["active"] is False and item["last_status"] == "ارسال شد"


def test_daily_announcement_moves_to_the_next_day_and_can_be_cancelled(world):
    c, H, bid, pub, sent = setup(world)
    r = c.post(f"/api/bots/{bid}/scheduled", json={"text": "صبح بخیر", "mode": "daily", "time": "08:30"}, headers=H).json()
    first = datetime.fromisoformat(r["next_run"])
    assert first.strftime("%H:%M") == "08:30" and first > datetime.now(timezone.utc)
    sent.clear()
    with SessionLocal() as db:
        assert outreach.due_scheduled(db, first + timedelta(minutes=1)) == 1
        row = db.query(ScheduledBroadcast).one()
        nxt = row.next_run if row.next_run.tzinfo else row.next_run.replace(tzinfo=timezone.utc)
        assert nxt - first.astimezone(timezone.utc) == timedelta(days=1) and row.active is True
    assert [chat for chat, t in sent if "صبح بخیر" in t] == ["801"]
    assert c.delete(f"/api/bots/{bid}/scheduled/{r['id']}", headers=H).status_code == 200
    with SessionLocal() as db:
        assert outreach.due_scheduled(db, first + timedelta(days=2)) == 0


def test_the_daily_limit_is_shared_with_manual_announcements_and_a_skipped_run_is_recorded(world):
    c, H, bid, pub, sent = setup(world)
    for i in range(3):
        assert c.post(f"/api/bots/{bid}/broadcasts", json={"text": f"دستی {i}"}, headers=H).status_code == 200
    soon = datetime.now(timezone.utc) + timedelta(minutes=5)
    c.post(f"/api/bots/{bid}/scheduled", json={"text": "زمان‌بندی", "mode": "once", "at": tehran(soon)}, headers=H)
    with SessionLocal() as db:
        assert outreach.due_scheduled(db, soon + timedelta(minutes=1)) == 0
    assert "حداکثر" in c.get(f"/api/bots/{bid}/scheduled", headers=H).json()["items"][0]["last_status"]


def test_validation_limits_and_authorisation(world):
    c, H, bid, pub, sent = world
    S = f"/api/bots/{bid}/scheduled"
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    far = datetime.now(timezone.utc) + timedelta(days=200)
    ok = datetime.now(timezone.utc) + timedelta(hours=2)
    assert c.post(S, json={"text": "x", "mode": "once", "at": tehran(past)}, headers=H).status_code == 422
    assert c.post(S, json={"text": "x", "mode": "once", "at": tehran(far)}, headers=H).status_code == 422
    assert c.post(S, json={"text": "x", "mode": "once", "at": "garbage"}, headers=H).status_code == 422
    for bad in ("25:00", "8:30", "08-30", "ab:cd", ""):
        assert c.post(S, json={"text": "x", "mode": "daily", "time": bad}, headers=H).status_code == 422
    assert c.post(S, json={"text": "x", "mode": "weekly"}, headers=H).status_code == 422
    assert c.post(S, json={"text": " ", "mode": "daily", "time": "08:00"}, headers=H).status_code == 422
    for i in range(5):
        assert c.post(S, json={"text": f"t{i}", "mode": "once", "at": tehran(ok)}, headers=H).status_code == 200
    assert c.post(S, json={"text": "sixth", "mode": "once", "at": tehran(ok)}, headers=H).status_code == 409
    other = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"email": "z@x.com", "password": "123456"}).json()["token"]}
    sid = c.get(S, headers=H).json()["items"][0]["id"]
    assert c.get(S, headers=other).status_code == 404
    assert c.post(S, json={"text": "x", "mode": "daily", "time": "08:00"}, headers=other).status_code == 404
    assert c.delete(f"{S}/{sid}", headers=other).status_code == 404
