"""The owner closes hours from the dashboard; bookings already there are counted, not cancelled."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from datetime import date, timedelta  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.dates import jalali_str  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import BotVersion, Record  # noqa: E402

SPEC = {"name": "سالن", "welcome": "سلام", "menu": [{"label": "نوبت", "block": "b"}],
        "blocks": [{"type": "booking", "id": "b", "title": "نوبت", "schedule": {"days": [{"weekday": d, "start": "09:00", "end": "18:00"} for d in range(7)],
                                                                             "duration_minutes": 60, "staff": ["سارا"]}}]}


@pytest.fixture()
def owner():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        H = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"username": "salon", "password": "123456"}).json()["token"]}
        bot = c.post("/api/bots", json={"template": "cafe"}, headers=H).json()["id"]
        day = date.today() + timedelta(days=3)
        with SessionLocal() as db:
            db.query(BotVersion).filter_by(bot_id=bot).first().spec = SPEC
            for t, st in (("14:00", "confirmed"), ("16:00", "confirmed"), ("15:00", "cancelled")):
                db.add(Record(bot_id=bot, collection="b", sandbox=False, data={"slot": "appt", "date": day.isoformat(), "time": t, "staff": "سارا", "status": st}))
            db.commit()
        yield c, H, bot, day


def test_close_an_afternoon_count_clashes_list_and_reopen(owner):
    c, H, bot, day = owner
    r = c.post(f"/api/bots/{bot}/time-off", json={"block_id": "b", "date": jalali_str(day), "start": "13:00", "end": "17:00", "note": "تعطیلی"}, headers=H)
    assert r.status_code == 200 and r.json()["clashes"] == 2 and r.json()["date"] == day.isoformat()
    rows = c.get(f"/api/bots/{bot}/time-off", headers=H).json()
    assert [(x["start"], x["end"], x["note"]) for x in rows] == [("13:00", "17:00", "تعطیلی")]
    assert c.delete(f"/api/bots/{bot}/time-off/{rows[0]['id']}", headers=H).json() == {"ok": True}
    assert c.get(f"/api/bots/{bot}/time-off", headers=H).json() == []


@pytest.mark.parametrize("body", [{"date": "دیروز"}, {"start": "17:00", "end": "13:00"}, {"staff": "کسی"}, {"block_id": "nope"}])
def test_bad_input_is_explained(owner, body):
    c, H, bot, day = owner
    base = {"block_id": "b", "date": jalali_str(day), "start": "13:00", "end": "17:00"}
    assert c.post(f"/api/bots/{bot}/time-off", json={**base, **body}, headers=H).status_code == 422
