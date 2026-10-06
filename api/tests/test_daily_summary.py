"""The owner's morning summary: what it says, and that it is sent once a day from 8:00 and can be turned off."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from datetime import date, datetime  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import bale, outreach  # noqa: E402
from app.dates import TEHRAN  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.engine import MemoryStore, daily_summary  # noqa: E402
from app.main import app  # noqa: E402
from app.models import BotVersion, Publication, Record  # noqa: E402
from app.spec import BotSpec  # noqa: E402

TODAY = date(2026, 10, 3)  # Saturday 1405/07/11
SPEC = {
    "name": "سالن رز", "welcome": "سلام", "menu": [{"label": "نوبت", "block": "appt"}],
    "blocks": [
        {"type": "booking", "id": "appt", "title": "نوبت‌دهی", "schedule": {"days": [{"weekday": 0, "start": "09:00", "end": "18:00"}], "duration_minutes": 30}},
        {"type": "booking", "id": "yoga", "title": "کلاس یوگا", "waitlist": True, "slots": [{"id": "s", "label": "یوگا ساعت ۸", "capacity": 10, "weekday": 0, "time": "20:00"}]},
        {"type": "catalog_order", "id": "shop", "title": "فروشگاه", "items": [{"id": "x", "name": "شامپو", "price": 1}]},
        {"type": "faq", "id": "faq", "title": "سؤال‌ها", "entries": [{"question": "ساعت کاری؟", "answer": "۹ تا ۱۸"}]},
        {"type": "contact", "id": "msg", "title": "پیام به ما"}]}

ROWS = [("appt", {"slot": "appt", "date": "2026-10-03", "time": "14:00", "name": "مینا", "phone": "09120000002", "status": "confirmed"}),
        ("appt", {"slot": "appt", "date": "2026-10-03", "time": "10:30", "name": "سارا", "service": "رنگ مو", "status": "confirmed"}),
        ("appt", {"slot": "appt", "date": "2026-10-03", "time": "11:00", "name": "لغوی", "status": "cancelled"}),
        ("appt", {"slot": "appt", "date": "2026-10-04", "time": "10:00", "name": "فردا", "status": "confirmed"}),
        ("yoga", {"slot": "s", "date": "2026-10-03", "party": 3, "status": "confirmed"}),
        ("yoga", {"slot": "s", "date": "2026-10-03", "status": "waitlisted"}),
        ("shop", {"status": "new"}), ("shop", {"status": "preparing"}), ("shop", {"status": "done"}),
        ("faq", {"question": "پارکینگ دارید؟", "status": "unanswered"}),
        ("msg", {"thread": "t1", "from": "customer", "text": "سلام"}), ("msg", {"thread": "t2", "from": "customer", "text": "؟"}),
        ("msg", {"thread": "t2", "from": "owner", "text": "بله"})]


def test_the_summary_lists_today_in_time_order_and_what_waits_for_the_owner():
    store = MemoryStore()
    for col, data in ROWS:
        store.add(col, data)
    text = daily_summary(BotSpec.model_validate(SPEC), store, TODAY, TEHRAN)
    assert text.startswith("☀️ خلاصه‌ی امروز شنبه ۱۴۰۵/۰۷/۱۱ · سالن رز")
    assert text.index("۱۰:۳۰ سارا (رنگ مو)") < text.index("۱۴:۰۰ مینا · ۰۹۱۲۰۰۰۰۰۰۲") and "لغوی" not in text
    assert "یوگا ساعت ۸: ۳ از ۱۰ نفر · ۱ در لیست انتظار" in text
    assert "۲ سفارش باز (۱ سفارش جدید، ۱ در حال آماده‌سازی)" in text
    assert "۱ سؤال بی‌پاسخ" in text and "۱ گفت‌وگو منتظر پاسخ شما" in text and "فردا: ۱ نوبت" in text


def test_nothing_to_report_means_no_message():
    assert daily_summary(BotSpec.model_validate(SPEC), MemoryStore(), TODAY, TEHRAN) is None


@pytest.fixture()
def live_bot(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    sent = []
    monkeypatch.setattr(bale, "send_owner", lambda db, bot_id, text: sent.append((bot_id, text)) or True)
    with TestClient(app) as c:
        H = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"username": "salon", "password": "123456"}).json()["token"]}
        bot = c.post("/api/bots", json={"template": "cafe"}, headers=H).json()["id"]
        with SessionLocal() as db:
            v = db.query(BotVersion).filter_by(bot_id=bot).first()
            v.spec = SPEC
            db.add(Publication(bot_id=bot, mode="shared", version=v.version, code="ABC123", admin_code="ADM1", admin_chat_id="555"))
            for col, data in ROWS:
                db.add(Record(bot_id=bot, collection=col, data=data, sandbox=False))
            db.add(Record(bot_id=bot, collection="faq", data={"question": "تست", "status": "unanswered"}, sandbox=True))  # simulator: never counted
            db.commit()
        yield c, H, bot, sent


def at(hh, mm=0, day=3):
    return datetime(2026, 10, day, hh, mm, tzinfo=TEHRAN)


def test_sent_once_a_day_from_eight_and_it_can_be_turned_off(live_bot):
    c, H, bot, sent = live_bot
    with SessionLocal() as db:
        assert outreach.daily_digests(db, at(7, 59)) == 0
        assert outreach.daily_digests(db, at(8, 1)) == 1 and "۱ سؤال بی‌پاسخ" in sent[0][1]
        assert outreach.daily_digests(db, at(13)) == 0        # once a day
    assert c.get(f"/api/bots/{bot}/publication", headers=H).json()["daily_summary"] is True
    assert c.put(f"/api/bots/{bot}/digest", json={"enabled": False}, headers=H).json() == {"daily_summary": False}
    with SessionLocal() as db:
        assert outreach.daily_digests(db, at(8, 1, day=4)) == 0 and len(sent) == 1
