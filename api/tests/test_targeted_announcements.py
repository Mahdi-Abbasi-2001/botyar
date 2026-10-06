"""Announcements to a group: one part of the bot, one upcoming session (reaches /stop-ers: it is their booking), recent customers."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import outreach  # noqa: E402
from app.dates import now_tehran  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import BotVersion, Broadcast, ChatSession, Publication, Record  # noqa: E402

SPEC = {"name": "باشگاه", "welcome": "سلام", "menu": [{"label": "کلاس", "block": "yoga"}, {"label": "فروشگاه", "block": "shop"}],
        "blocks": [{"type": "booking", "id": "yoga", "title": "کلاس یوگا", "slots": [{"id": "sat", "label": "یوگا ساعت ۸", "capacity": 10, "weekday": 0, "time": "20:00"}]},
                   {"type": "catalog_order", "id": "shop", "title": "فروشگاه", "items": [{"id": "mat", "name": "مت", "price": 1}]}]}


@pytest.fixture()
def gym(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    sent = []
    monkeypatch.setattr(outreach, "_deliver", lambda bid, bot_id, custs, text: sent.append(sorted(custs)))
    today = now_tehran().date()
    soon, later = (today.toordinal() + 2), (today.toordinal() + 9)
    from datetime import date
    d1, d2 = date.fromordinal(soon).isoformat(), date.fromordinal(later).isoformat()
    with TestClient(app) as c:
        H = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"username": "gym", "password": "123456"}).json()["token"]}
        bot = c.post("/api/bots", json={"template": "cafe"}, headers=H).json()["id"]
        with SessionLocal() as db:
            v = db.query(BotVersion).filter_by(bot_id=bot).first()
            v.spec = SPEC
            db.add(Publication(bot_id=bot, mode="own", version=v.version, code="GYM001", admin_code="GADM1"))
            for k, muted in (("bale:1", False), ("bale:2", True), ("bale:3", False), ("bale:4", False)):
                db.add(ChatSession(bot_id=bot, key=k, state={"muted": True} if muted else {}))
            now = now_tehran().isoformat()
            for col, data in [("yoga", {"slot": "sat", "date": d1, "status": "confirmed", "_cust": "bale:1", "_at": now}),
                              ("yoga", {"slot": "sat", "date": d1, "status": "confirmed", "_cust": "bale:2", "_at": now}),   # muted
                              ("yoga", {"slot": "sat", "date": d2, "status": "confirmed", "_cust": "bale:3", "_at": now}),
                              ("yoga", {"slot": "sat", "date": d1, "status": "cancelled", "_cust": "bale:4", "_at": now}),
                              ("shop", {"status": "new", "_cust": "bale:3", "_at": "2020-01-01T00:00:00+03:30"})]:
                db.add(Record(bot_id=bot, collection=col, data=data, sandbox=False))
            db.commit()
        yield c, H, bot, sent, d1


def test_groups_are_offered_with_their_sizes(gym):
    c, H, bot, sent, d1 = gym
    seg = {s["id"]: s for s in c.get(f"/api/bots/{bot}/broadcasts/segments", headers=H).json()}
    assert seg["all"]["size"] == 3                       # bale:2 sent /stop
    assert seg["block:yoga"]["size"] == 2 and seg["block:shop"]["size"] == 1 and seg["block:shop"]["label"] == "کسانی که در «فروشگاه» ثبت دارند"
    assert seg[f"session:yoga:sat:{d1}"]["size"] == 2    # its own booking: the muted customer is included, the cancelled one is not
    assert "یوگا ساعت ۸" in seg[f"session:yoga:sat:{d1}"]["label"]
    assert seg["recent:7"]["size"] == 3                  # 1, 3 and 4 acted this week (a cancellation is activity too); 2 is muted


def test_a_session_announcement_reaches_exactly_its_people(gym):
    c, H, bot, sent, d1 = gym
    r = c.post(f"/api/bots/{bot}/broadcasts", json={"text": "کلاس لغو شد", "segment": f"session:yoga:sat:{d1}"}, headers=H)
    assert r.status_code == 200 and r.json()["audience"] == 2 and sent[-1] == ["bale:1", "bale:2"]
    c.post(f"/api/bots/{bot}/broadcasts", json={"text": "تخفیف مت", "segment": "block:shop"}, headers=H)
    assert sent[-1] == ["bale:3"]
    items = c.get(f"/api/bots/{bot}/broadcasts", headers=H).json()["items"]
    assert items[0]["segment"] == "کسانی که در «فروشگاه» ثبت دارند" and "یوگا ساعت ۸" in items[1]["segment"]


def test_unknown_or_empty_groups_are_refused(gym):
    c, H, bot, sent, d1 = gym
    assert c.post(f"/api/bots/{bot}/broadcasts", json={"text": "x", "segment": "block:nope"}, headers=H).status_code == 409
    assert not sent


def test_the_segment_column_is_added_to_old_databases(tmp_path):
    from sqlalchemy import create_engine, inspect, text
    from app.migrate import add_column
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE broadcasts (id INTEGER PRIMARY KEY, text TEXT)"))
    assert add_column(eng, "broadcasts", "segment_label", "VARCHAR(200) DEFAULT ''") is True
    assert "segment_label" in {c["name"] for c in inspect(eng).get_columns("broadcasts")}
    assert add_column(eng, "broadcasts", "segment_label", "VARCHAR(200) DEFAULT ''") is False
