"""Sessions on specific dates (a workshop of four meetings): offered until they start, capacity per session, reminders from the date."""
import pytest
from pydantic import ValidationError

from app.dates import TEST_NOW
from app.engine import MemoryStore, booking_start, handle, new_session
from app.spec import BotSpec, Slot

SPEC = BotSpec.model_validate({
    "name": "w", "welcome": "سلام", "menu": [{"label": "ثبت‌نام", "block": "b"}],
    "blocks": [{"type": "booking", "id": "b", "title": "کارگاه", "waitlist": True, "allow_cancel": True, "reminder_hours": 24,
                "slots": [{"id": f"s{i}", "label": f"جلسه‌ی {i}", "capacity": 1, "on": d, "time": "10:00"}
                          for i, d in enumerate(["1405/07/05", "1405/07/12", "1405/07/19", "1405/07/26"], 1)]}]})   # today is 1405/07/11


def buttons(out):
    return [(b["text"], b["data"]) for a in out for b in a.get("buttons", [])]


def register(st, cust, slot):
    s = new_session()
    s["cust"] = cust
    handle(SPEC, s, "m:0", st, TEST_NOW)
    out = handle(SPEC, s, slot, st, TEST_NOW)
    if "با همین مشخصات" in "".join(a.get("text", "") for a in out):  # a returning customer reuses the saved details
        return handle(SPEC, s, "ru:yes", st, TEST_NOW)
    for t in ("علی", "09121234567"):
        out = handle(SPEC, s, t, st, TEST_NOW)
    return out


def test_past_sessions_are_not_offered_and_future_ones_show_their_jalali_date():
    s = new_session()
    s["cust"] = "bale:1"
    out = handle(SPEC, s, "m:0", MemoryStore(), TEST_NOW)
    labels = [t for t, d in buttons(out) if d.startswith("s:")]
    assert labels == ["جلسه‌ی 2 — 1405/07/12 (1 جای خالی)", "جلسه‌ی 3 — 1405/07/19 (1 جای خالی)", "جلسه‌ی 4 — 1405/07/26 (1 جای خالی)"]


def test_each_session_has_its_own_capacity_and_a_full_one_takes_a_waiting_list():
    st = MemoryStore()
    register(st, "bale:1", "s:s2@20261004")
    assert st.find("b")[0]["status"] == "confirmed"
    out = register(st, "bale:2", "s:s2@20261004")
    assert st.find("b")[1]["status"] == "waitlisted" and "جایگاه شما در فهرست انتظار" in "".join(a.get("text", "") for a in out)
    register(st, "bale:2", "s:s3@20261011")
    assert [r["status"] for r in st.find("b")] == ["confirmed", "waitlisted", "confirmed"]    # another session is still free


def test_a_reminder_can_find_the_start_of_a_dated_session():
    st = MemoryStore()
    register(st, "bale:1", "s:s3@20261011")
    row = st.find("b")[0]
    start = booking_start(SPEC.blocks[0], row, TEST_NOW.tzinfo)
    assert start is not None and (start.year, start.month, start.day, start.hour) == (2026, 10, 11, 10)


def test_a_dated_session_needs_a_valid_date_a_time_and_no_weekday():
    for bad in ({"on": "2026-10-11", "time": "10:00"}, {"on": "1405/07/19"}, {"on": "1405/07/19", "time": "10:00", "weekday": 2}):
        with pytest.raises(ValidationError):
            Slot(id="x", label="l", capacity=1, **bad)
    assert Slot(id="x", label="l", capacity=1, on="1405/07/19", time="16:30").on == "1405/07/19"


def test_when_every_session_has_passed_the_customer_is_told_nothing_is_open():
    spec = BotSpec.model_validate({**SPEC.model_dump(), "blocks": [{**SPEC.model_dump()["blocks"][0], "slots": [{"id": "old", "label": "قدیمی", "capacity": 1, "on": "1405/07/01", "time": "10:00"}]}]})
    s = new_session()
    s["cust"] = "bale:1"
    out = handle(spec, s, "m:0", MemoryStore(), TEST_NOW)
    assert "جلسه‌ای برای ثبت‌نام باز نیست" in "".join(a.get("text", "") for a in out)
