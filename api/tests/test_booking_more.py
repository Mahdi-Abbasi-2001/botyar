"""Booking, round 2: attendance confirmation from the reminder, staff per service, hours per staff, no-shows,
closed hours, repeating bookings, deposits."""
from datetime import datetime, timedelta

from app import outreach  # noqa: F401  (reminder_text)
from app.dates import TEHRAN, TEST_NOW
from app.engine import MemoryStore, handle, new_session, reminder_buttons
from app.spec import BotSpec


def make(**block):
    base = {"type": "booking", "id": "b", "title": "کلاس", "allow_cancel": True, "reminder_hours": 24,
            "slots": [{"id": "sun", "label": "یکشنبه ۱۰ صبح", "capacity": 1, "weekday": 1, "time": "10:00"}]}
    base.update(block)
    return BotSpec.model_validate({"name": "باشگاه", "welcome": "سلام", "menu": [{"label": "کلاس", "block": "b"}],
                                   "blocks": [base, {"type": "admin_notify", "id": "n", "on": "b", "text": "ثبت"}]})


class Chat:
    def __init__(self, spec, store, cust, now=TEST_NOW):
        self.spec, self.store, self.now, self.s = spec, store, now, new_session()
        self.s["cust"] = cust

    def say(self, *texts):
        out = []
        for t in texts:
            out = handle(self.spec, self.s, t, self.store, self.now)
        return out


def txt(out):
    return "\n".join(a.get("text", "") for a in out)


def booked(spec, store, cust, *extra):
    Chat(spec, store, cust).say("/start", "m:0", "s:sun@20261004", *extra, "علی", "09121234567")
    return store.find("b", _cust=cust)[-1]


# ---------- 1. attendance confirmation ----------
def test_the_reminder_asks_and_coming_is_recorded():
    spec, store = make(), MemoryStore()
    r = booked(spec, store, "a")
    assert [b["data"] for b in reminder_buttons(spec, spec.blocks[0], r)] == [f"rc:y:0:{r['id']}", f"rc:n:0:{r['id']}"]
    assert "اعلام کنید می‌آیید" in outreach.reminder_text(spec.blocks[0], r, datetime(2026, 10, 4, 10, tzinfo=TEHRAN))
    assert "منتظرتان هستیم" in txt(Chat(spec, store, "a").say(f"rc:y:0:{r['id']}"))
    assert store.find("b")[0]["attend"] == "yes"


def test_not_coming_frees_the_place_for_the_waitlist():
    spec, store = make(waitlist=True), MemoryStore()
    r = booked(spec, store, "a")
    booked(spec, store, "b")                                   # full: waitlisted
    out = Chat(spec, store, "a").say(f"rc:n:0:{r['id']}")
    assert "نوبت شما لغو شد" in txt(out)
    assert [x["status"] for x in store.find("b")] == ["cancelled", "confirmed"]
    assert any(a["type"] == "notify_customer" and a["cust"] == "b" for a in out)


def test_too_late_to_cancel_keeps_the_booking_and_warns_the_owner():
    spec, store = make(cancel_deadline_hours=48), MemoryStore()
    r = booked(spec, store, "a")
    out = Chat(spec, store, "a").say(f"rc:n:0:{r['id']}")
    assert store.find("b")[0]["status"] == "confirmed" and store.find("b")[0]["attend"] == "no"
    assert any(a["type"] == "notify_admin" and "نمی‌تواند بیاید" in a["text"] for a in out)


def test_nobody_can_answer_someone_elses_reminder():
    spec, store = make(), MemoryStore()
    r = booked(spec, store, "a")
    assert "دیگر فعال نیست" in txt(Chat(spec, store, "intruder").say(f"rc:n:0:{r['id']}"))
    assert store.find("b")[0]["status"] == "confirmed"
    assert reminder_buttons(make(reminder_confirm=False), make(reminder_confirm=False).blocks[0], r) == []


# ---------- 2/3. staff per service, hours per staff ----------
def salon(**sch):
    schedule = {"days": [{"weekday": 1, "start": "09:00", "end": "13:00"}], "duration_minutes": 60, "staff": ["سارا", "مینا"],
                "services": [{"id": "cut", "name": "کوتاهی", "duration_minutes": 60}, {"id": "color", "name": "رنگ", "duration_minutes": 60, "staff": ["سارا"]}]}
    schedule.update(sch)
    return BotSpec.model_validate({"name": "سالن", "welcome": "سلام", "menu": [{"label": "نوبت", "block": "b"}],
                                   "blocks": [{"type": "booking", "id": "b", "title": "نوبت", "schedule": schedule}]})


def data(out):
    return [b["data"] for a in out for b in a.get("buttons", [])]


def test_only_the_staff_who_do_a_service_are_offered():
    spec, store = salon(), MemoryStore()
    assert data(Chat(spec, store, "a").say("/start", "m:0", "sv:0"))[:2] == ["f:0", "f:1"]   # haircut: both
    out = Chat(spec, store, "a").say("/start", "m:0", "sv:1")                                  # colouring: only Sara -> no question
    assert "روز مورد نظر" in txt(out)
    c = Chat(spec, store, "a")
    c.say("/start", "m:0", "sv:1")
    assert c.s["data"]["staff"] == "سارا"
    c2 = Chat(spec, store, "b")
    c2.say("/start", "m:0", "sv:0")
    assert "لطفاً یکی از گزینه‌ها" in txt(c2.say("f:9"))


def test_a_staff_member_has_their_own_hours():
    spec, store = salon(staff_hours=[{"staff": "مینا", "days": [{"weekday": 1, "start": "15:00", "end": "18:00"}]}]), MemoryStore()
    sara = Chat(spec, store, "a").say("/start", "m:0", "sv:0", "f:0", "d:20261004")
    mina = Chat(spec, store, "b").say("/start", "m:0", "sv:0", "f:1", "d:20261004")
    assert data(sara)[:4] == ["t:0900", "t:1000", "t:1100", "t:1200"] and data(mina)[:3] == ["t:1500", "t:1600", "t:1700"]


def test_staff_rules_must_name_real_staff():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        salon(services=[{"id": "x", "name": "x", "duration_minutes": 60, "staff": ["کسی"]}])
    with pytest.raises(ValidationError):
        salon(staff_hours=[{"staff": "کسی", "days": [{"weekday": 1, "start": "09:00", "end": "12:00"}]}])


# ---------- 4. no-shows ----------
def test_no_shows_are_marked_after_the_start_and_block_online_booking_at_the_limit():
    import pytest
    from app.engine import mark_no_show
    spec, store = make(no_show_limit=1, reminder_hours=0), MemoryStore()
    r = booked(spec, store, "a")
    with pytest.raises(ValueError):
        mark_no_show(store, TEST_NOW, spec.blocks[0], r)                       # Sunday 10:00 has not come yet
    mark_no_show(store, datetime(2026, 10, 4, 11, tzinfo=TEHRAN), spec.blocks[0], r)
    assert store.find("b")[0]["status"] == "no_show"
    assert "حاضر نشدن" in txt(Chat(spec, store, "a").say("/start", "m:0"))   # 1 no-show = the limit
    assert "زمان مورد نظر" in txt(Chat(spec, store, "someone_else").say("/start", "m:0"))


# ---------- 5. hours closed by the owner ----------
def test_closed_hours_hide_appointment_times_for_everyone_or_one_staff_member():
    spec, store = salon(), MemoryStore()
    store.closed["b"] = [{"date": "2026-10-04", "start": "10:00", "end": "12:00", "staff": "مینا"}]
    sara = Chat(spec, store, "a").say("/start", "m:0", "sv:0", "f:0", "d:20261004")
    mina = Chat(spec, store, "b").say("/start", "m:0", "sv:0", "f:1", "d:20261004")
    assert "t:1000" in data(sara) and [x for x in data(mina) if x.startswith("t:")] == ["t:0900", "t:1200"]
    store.closed["b"] = [{"date": "2026-10-04", "start": "00:00", "end": "23:59", "staff": ""}]
    assert "d:20261004" not in data(Chat(spec, store, "c").say("/start", "m:0", "sv:0", "f:0"))   # the whole day is gone


def test_closed_hours_hide_a_class_session():
    spec, store = make(occurrences=2), MemoryStore()
    store.closed["b"] = [{"date": "2026-10-04", "start": "09:00", "end": "11:00", "staff": ""}]
    out = Chat(spec, store, "a").say("/start", "m:0")
    assert "s:sun@20261004" not in data(out) and "s:sun@20261011" in data(out)


# ---------- 6. repeating bookings ----------
def test_a_weekly_class_series_books_the_weeks_with_room_and_names_the_full_ones():
    spec, store = make(repeat_weeks=4, reminder_hours=0, slots=[{"id": "sun", "label": "یکشنبه ۱۰ صبح", "capacity": 1, "weekday": 1, "time": "10:00"}]), MemoryStore()
    store.add("b", {"slot": "sun", "date": "2026-10-18", "status": "confirmed", "_cust": "other"})   # week 3 is already full
    c = Chat(spec, store, "a")
    assert "چند هفته پشت سر هم" in txt(c.say("/start", "m:0", "s:sun@20261004"))
    out = c.say("rw:4", "علی", "09121234567")
    mine = sorted((r["date"], r["status"]) for r in store.find("b", _cust="a"))
    assert mine == [("2026-10-04", "confirmed"), ("2026-10-11", "confirmed"), ("2026-10-25", "confirmed")]
    assert "۱۴۰۵/۰۷/۱۹، ۱۴۰۵/۰۸/۰۳" in txt(out) and "جای خالی نداشت و رزرو نشد: ۱۴۰۵/۰۷/۲۶" in txt(out)
    assert len({r["_series"] for r in store.find("b", _cust="a")}) == 1


def test_an_appointment_series_keeps_staff_and_time_and_skips_closed_weeks():
    spec, store = salon(), MemoryStore()
    spec.blocks[0].repeat_weeks = 3
    store.closed["b"] = [{"date": "2026-10-11", "start": "09:00", "end": "13:00", "staff": ""}]
    c = Chat(spec, store, "a")
    c.say("/start", "m:0", "sv:1", "d:20261004", "t:1000", "rw:3", "سارا", "09121234567")
    rows = sorted(store.find("b", _cust="a"), key=lambda r: r["date"])
    assert [(r["date"], r["time"], r["staff"]) for r in rows] == [("2026-10-04", "10:00", "سارا"), ("2026-10-18", "10:00", "سارا")]


def test_one_session_only_is_a_normal_booking():
    spec, store = make(repeat_weeks=4, reminder_hours=0), MemoryStore()
    Chat(spec, store, "a").say("/start", "m:0", "s:sun@20261004", "rw:1", "علی", "09121234567")
    assert len(store.find("b")) == 1 and "_series" not in store.find("b")[0]


# ---------- 7. deposits ----------
def deposit_spec(**kw):
    return make(deposit=200000, reminder_hours=0, **kw)


def pay_chat(spec, store, cust):
    c = Chat(spec, store, cust)
    c.s["pay_ok"] = c.s["pay_sim"] = True
    return c


def test_a_deposit_holds_the_place_and_confirms_on_payment():
    spec, store = deposit_spec(), MemoryStore()
    out = pay_chat(spec, store, "a").say("/start", "m:0", "s:sun@20261004", "علی", "09121234567")
    row = store.find("b")[0]
    assert row["status"] == "awaiting_payment" and row["total"] == 200000 and "بیعانه‌ی نوبت" in txt(out)
    assert not any(a["type"] == "notify_admin" for a in out)                       # the owner hears only once it is paid
    assert "(تکمیل)" in str(Chat(spec, store, "b").say("/start", "m:0"))           # its place is held meanwhile
    out = pay_chat(spec, store, "a").say(f"pay:{row['id']}")
    assert "بیعانه پرداخت شد" in txt(out) and store.find("b")[0]["status"] == "confirmed" and store.find("b")[0]["paid"]
    assert any(a["type"] == "notify_admin" for a in out)
    assert "بیعانه‌ی این نوبت پرداخت شده" in txt(Chat(spec, store, "a").say("/start", "m:1", "x:0:1"))   # self-cancel goes via the owner


def test_an_unpaid_deposit_expires_and_frees_the_place():
    from app.engine import expire_unpaid
    spec, store = deposit_spec(), MemoryStore()
    pay_chat(spec, store, "a").say("/start", "m:0", "s:sun@20261004", "علی", "09121234567")
    notes = expire_unpaid(spec, store, TEST_NOW + timedelta(minutes=16))
    assert store.find("b")[0]["status"] == "cancelled" and "نوبت آزاد شد" in notes[0]["text"]
    assert "(1 جای خالی)" in str(Chat(spec, store, "b").say("/start", "m:0"))


def test_without_a_wallet_the_booking_is_confirmed_and_the_deposit_arranged_by_the_owner():
    spec, store = deposit_spec(), MemoryStore()
    out = Chat(spec, store, "a").say("/start", "m:0", "s:sun@20261004", "علی", "09121234567")
    assert store.find("b")[0]["status"] == "confirmed" and "مدیر درباره‌ی آن با شما هماهنگ" in txt(out)


def test_deposit_cannot_be_combined_with_a_waitlist_or_series():
    import pytest
    from pydantic import ValidationError
    for kw in ({"waitlist": True}, {"repeat_weeks": 4}):
        with pytest.raises(ValidationError):
            deposit_spec(**kw)
