"""Weekly slots: capacity is counted per real date, so it resets by itself after each class."""
from datetime import datetime

import pytest

from app.dates import TEHRAN, TEST_NOW
from app.engine import MemoryStore, handle, new_session
from app.spec import BotSpec


def make(waitlist=False, cap=2):
    return BotSpec.model_validate({
        "name": "کلاس", "welcome": "سلام", "menu": [{"label": "ثبت‌نام", "block": "b"}],
        "blocks": [{"type": "booking", "id": "b", "title": "ثبت‌نام کلاس", "waitlist": waitlist,
                    "slots": [{"id": "thu", "label": "پنجشنبه ساعت ۱۰ صبح", "capacity": cap, "weekday": 5, "time": "10:00"},
                              {"id": "once", "label": "کارگاه ویژه ۲۵ مهر", "capacity": 1}]}]})


def at(y, m, d, hh=12, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=TEHRAN)


def labels(actions):
    return [b["text"] for a in actions for b in a["buttons"] if b["data"] != "/menu"]


def say(spec, st, now, *texts, sess=None):
    sess = sess if sess is not None else new_session()
    out = None
    for t in texts:
        out = handle(spec, sess, t, st, now)
    return out, sess


def book(spec, st, now, data, name="علی", phone="09123456789"):
    out, sess = say(spec, st, now, "/start", "m:0", data, name, phone)
    return out


def test_next_two_dates_are_offered_with_real_jalali_dates():
    out, _ = say(make(), MemoryStore(), TEST_NOW, "/start", "m:0")
    assert labels(out) == ["پنجشنبه ساعت ۱۰ صبح — 1405/07/16 (2 جای خالی)", "پنجشنبه ساعت ۱۰ صبح — 1405/07/23 (2 جای خالی)", "کارگاه ویژه ۲۵ مهر (1 جای خالی)"]
    assert [b["data"] for a in out for b in a["buttons"] if b["data"] != "/menu"] == ["s:thu@20261008", "s:thu@20261015", "s:once"]


def test_capacity_is_per_date_and_the_record_carries_the_date():
    spec, st = make(), MemoryStore()
    for i in range(2):
        book(spec, st, TEST_NOW, "s:thu@20261008", phone=f"0912000000{i}")
    rec = st.rows["b"][0]
    assert rec["date"] == "2026-10-08" and rec["slot_label"] == "پنجشنبه ساعت ۱۰ صبح — 1405/07/16" and rec["status"] == "confirmed"
    out, _ = say(spec, st, TEST_NOW, "/start", "m:0")
    assert "(تکمیل)" in labels(out)[0] and "2 جای خالی" in labels(out)[1]      # this Thursday full, next Thursday untouched
    out, _ = say(spec, st, TEST_NOW, "/start", "m:0", "s:thu@20261008")
    assert "ظرفیت" in "".join(a["text"] for a in out)                          # picking the full date is refused


def test_a_full_class_is_bookable_again_once_it_has_happened():
    """THE bug: capacity used to count every booking ever made, so a weekly class filled once and stayed full for good."""
    spec, st = make(), MemoryStore()
    for i in range(2):
        book(spec, st, TEST_NOW, "s:thu@20261008", phone=f"0912000000{i}")
    after_class = at(2026, 10, 8, 10, 1)                                      # Thursday 10:01, the class has started
    out, _ = say(spec, st, after_class, "/start", "m:0")
    assert labels(out)[:2] == ["پنجشنبه ساعت ۱۰ صبح — 1405/07/23 (2 جای خالی)", "پنجشنبه ساعت ۱۰ صبح — 1405/07/30 (2 جای خالی)"]
    out = book(spec, st, after_class, "s:thu@20261015")
    assert "با موفقیت" in "".join(a["text"] for a in out)


def test_booking_made_the_day_before_still_counts_after_the_weekend_boundary():
    """The trap a fixed 'reset every Saturday' rule would fall into: Friday's booking for next Thursday must survive Saturday."""
    spec, st = make(), MemoryStore()
    friday = at(2026, 10, 9, 11, 0)
    for i in range(2):
        book(spec, st, friday, "s:thu@20261015", phone=f"0912000000{i}")
    saturday = at(2026, 10, 10, 9, 0)
    out, _ = say(spec, st, saturday, "/start", "m:0")
    assert "(تکمیل)" in labels(out)[0] and "1405/07/23" in labels(out)[0]      # still full for 15 Oct
    assert "2 جای خالی" in labels(out)[1]                                      # 22 Oct free


def test_stale_forged_or_far_future_dates_are_refused():
    spec, st = make(), MemoryStore()
    for data in ("s:thu@20260101", "s:thu@20261022", "s:thu@20261009", "s:thu@abc", "s:nope@20261008"):
        out, sess = say(spec, st, TEST_NOW, "/start", "m:0", data)
        assert "لطفاً یکی از زمان‌ها" in "".join(a["text"] for a in out), data
        assert sess["step"] == "slot" and "slot" not in sess["data"]


def test_typed_label_picks_the_nearest_date():
    spec, st = make(), MemoryStore()
    out = say(spec, st, TEST_NOW, "/start", "m:0", "پنجشنبه ساعت ۱۰ صبح", "علی", "09123456789")[0]
    assert st.rows["b"][0]["date"] == "2026-10-08"


def test_waitlist_is_per_date_too():
    spec, st = make(waitlist=True, cap=1), MemoryStore()
    book(spec, st, TEST_NOW, "s:thu@20261008", phone="09120000001")
    out = book(spec, st, TEST_NOW, "s:thu@20261008", phone="09120000002")
    assert "لیست انتظار" in "".join(a["text"] for a in out)
    assert [r["status"] for r in st.rows["b"]] == ["confirmed", "waitlisted"]
    out = book(spec, st, TEST_NOW, "s:thu@20261015", phone="09120000003")      # next week is an independent class
    assert st.rows["b"][-1]["status"] == "confirmed"


def test_one_off_slots_keep_their_lifetime_capacity():
    spec, st = make(), MemoryStore()
    book(spec, st, TEST_NOW, "s:once")
    out, _ = say(spec, st, at(2027, 3, 1), "/start", "m:0")                    # months later
    assert "(تکمیل)" in labels(out)[-1]


@pytest.mark.parametrize("slot,fragment", [
    ({"id": "a", "label": "x", "capacity": 1, "weekday": 9, "time": "10:00"}, "weekday"),
    ({"id": "a", "label": "x", "capacity": 1, "weekday": 2}, "HH:MM"),
    ({"id": "a", "label": "x", "capacity": 1, "weekday": 2, "time": "25:00"}, "HH:MM"),
])
def test_weekly_slot_validation(slot, fragment):
    with pytest.raises(ValueError, match=fragment):
        BotSpec.model_validate({"name": "n", "welcome": "w", "menu": [{"label": "m", "block": "b"}],
                                "blocks": [{"type": "booking", "id": "b", "title": "t", "slots": [slot]}]})
