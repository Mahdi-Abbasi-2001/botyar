"""Appointment calendars: times are generated from working hours; capacity is per staff member, date and time."""
from datetime import datetime, timedelta

from app.dates import TEHRAN, TEST_NOW
from app.engine import MemoryStore, handle, new_session
from app.spec import BotSpec


def make(staff=("سارا", "مینا"), capacity=1, hours=("09:00", "13:00"), duration=60, brk=("11:00", "12:00"), cancel=False, deadline=0, days_ahead=7):
    sch = {"days": [{"weekday": 0, "start": hours[0], "end": hours[1]}, {"weekday": 1, "start": hours[0], "end": hours[1]}],  # Saturday + Sunday
           "duration_minutes": duration, "capacity": capacity, "days_ahead": days_ahead, "staff": list(staff)}
    if brk:
        sch["break_start"], sch["break_end"] = brk
    return BotSpec.model_validate({"name": "سالن", "welcome": "سلام", "menu": [{"label": "نوبت", "block": "b"}],
                                   "blocks": [{"type": "booking", "id": "b", "title": "نوبت‌دهی", "schedule": sch, "allow_cancel": cancel, "cancel_deadline_hours": deadline},
                                              {"type": "admin_notify", "id": "n", "on": "b", "text": "نوبت جدید"}]})


class Chat:
    def __init__(self, spec, store, cust, now=TEST_NOW):
        self.spec, self.store, self.now, self.s = spec, store, now, new_session()
        self.s["cust"] = cust

    def say(self, *texts, now=None):
        out = None
        for t in texts:
            out = handle(self.spec, self.s, t, self.store, now or self.now)
        return out

    def book(self, staff_idx, day, hhmm, name="علی", phone="09123456789"):
        return self.say("/start", "m:0", f"f:{staff_idx}", f"d:{day}", f"t:{hhmm}", name, phone)


def buttons(actions):
    return [(b["text"], b["data"]) for a in actions for b in a.get("buttons", []) if b["data"] != "/menu"]


def text(actions):
    return "\n".join([a["text"] for a in actions] + [b["text"] for a in actions for b in a.get("buttons", [])])


SUN, SAT_NEXT = "20261004", "20261010"   # test clock is Saturday 3 Oct 12:00, so today has no future start times left


def test_flow_staff_then_days_then_times_with_the_break_excluded():
    spec, st = make(), MemoryStore()
    c = Chat(spec, st, "bale:1")
    out = c.say("/start", "m:0")
    assert [d for _, d in buttons(out)] == ["f:0", "f:1"]                                   # first: who
    out = c.say("f:0")
    days = buttons(out)
    assert [d for _, d in days] == ["d:20261004", "d:20261010"]                               # only working days (Sun 4th, Sat 10th); today is over
    assert "یکشنبه 1405/07/12" in days[0][0] and "3 نوبت خالی" in days[0][0]                  # 09:00, 10:00, 12:00 (11:00 collides with the break)
    out = c.say(f"d:{SUN}")
    assert [d for _, d in buttons(out)][:3] == ["t:0900", "t:1000", "t:1200"] and "t:1100" not in [d for _, d in buttons(out)]


def test_booking_creates_a_complete_record_and_notifies_the_owner():
    spec, st = make(), MemoryStore()
    out = Chat(spec, st, "bale:1").book(1, SUN, "1000")
    assert "با موفقیت" in text(out) and any(a["type"] == "notify_admin" for a in out)
    rec = st.rows["b"][0]
    assert (rec["slot"], rec["date"], rec["time"], rec["staff"], rec["status"]) == ("appt", "2026-10-04", "10:00", "مینا", "confirmed")
    assert rec["slot_label"] == "یکشنبه 1405/07/12 ساعت 10:00 — مینا" and rec["_cust"] == "bale:1"


def test_capacity_is_per_staff_member_and_per_time():
    spec, st = make(), MemoryStore()
    Chat(spec, st, "bale:1").book(0, SUN, "1000")                                             # سارا at 10:00
    sara = Chat(spec, st, "bale:2")
    sara.say("/start", "m:0", "f:0", f"d:{SUN}")
    assert "t:1000" not in [d for _, d in buttons(sara.say(f"d:{SUN}"))]                      # taken for سارا…
    mina = Chat(spec, st, "bale:3")
    mina.say("/start", "m:0", "f:1")
    assert "t:1000" in [d for _, d in buttons(mina.say(f"d:{SUN}"))]                          # …but free for مینا


def test_capacity_above_one_allows_parallel_customers():
    spec, st = make(staff=(), capacity=2), MemoryStore()
    for i in range(2):
        out = Chat(spec, st, f"bale:{i}").say("/start", "m:0", f"d:{SUN}", "t:0900", "علی", f"0912000000{i}")
        assert "با موفقیت" in text(out)
    c = Chat(spec, st, "bale:9")
    assert "t:0900" not in [d for _, d in buttons(c.say("/start", "m:0", f"d:{SUN}"))]


def test_two_customers_racing_for_the_same_time_the_second_is_sent_back_to_the_times():
    spec, st = make(staff=()), MemoryStore()
    a, b = Chat(spec, st, "bale:1"), Chat(spec, st, "bale:2")
    a.say("/start", "m:0", f"d:{SUN}", "t:0900", "الف")                                       # a is typing the phone number
    b.say("/start", "m:0", f"d:{SUN}", "t:0900", "ب")
    out = a.say("09120000001")                                                                # a finishes first
    assert "با موفقیت" in text(out)
    out = b.say("09120000002")                                                                # b loses the race
    assert "ظرفیت" in text(out) and "t:0900" not in [d for _, d in buttons(out)] and len(st.rows["b"]) == 1


def test_times_in_the_past_are_not_offered():
    spec, st = make(staff=()), MemoryStore()
    sunday_1030 = datetime(2026, 10, 4, 10, 30, tzinfo=TEHRAN)
    c = Chat(spec, st, "bale:1", sunday_1030)
    out = c.say("/start", "m:0", f"d:{SUN}")
    assert [d for _, d in buttons(out)][:1] == ["t:1200"]                                     # 09:00 and 10:00 already started


def test_many_times_are_paginated_and_navigation_edits_in_place():
    spec, st = make(staff=(), hours=("08:00", "20:00"), duration=30, brk=None), MemoryStore()   # 24 times a day
    c = Chat(spec, st, "bale:1")
    out = c.say("/start", "m:0", f"d:{SUN}")
    d = [x for _, x in buttons(out)]
    assert d[:8] == [f"t:{h:02d}{m:02d}" for h, m in [(8, 0), (8, 30), (9, 0), (9, 30), (10, 0), (10, 30), (11, 0), (11, 30)]] and "tp:1" in d and "tp:0" not in d
    assert "صفحه 1 از 3" in text(out)
    out = c.say("tp:1")
    assert out[0].get("edit") is True and "tp:0" in [x for _, x in buttons(out)] and "tp:2" in [x for _, x in buttons(out)]
    out = c.say("back")
    assert [x for _, x in buttons(out)][0].startswith("d:")                                    # back to the day list


def test_forged_or_stale_input_is_refused_at_every_step():
    spec, st = make(), MemoryStore()
    c = Chat(spec, st, "bale:1")
    assert "لطفاً یکی از گزینه" in text(c.say("/start", "m:0", "f:9"))
    c.say("f:0")
    for bad in ("d:20260101", "d:20261012", "d:20261009", "d:abc", "d:20261003"):             # past, beyond horizon, Friday (closed), junk, today (over)
        out = c.say(bad)
        assert "لطفاً یکی از روزها" in text(out), bad
    c.say(f"d:{SUN}")
    for bad in ("t:1100", "t:2500", "t:0800", "t:abc", "t:1300"):                              # break, impossible, before opening, junk, at closing
        assert "دیگر خالی نیست" in text(c.say(bad)), bad
    assert st.rows.get("b") is None


def test_a_fully_booked_calendar_says_so_politely():
    spec, st = make(staff=(), hours=("09:00", "10:00"), brk=None, days_ahead=1), MemoryStore()   # one time per working day; only Sunday within reach
    Chat(spec, st, "bale:1").say("/start", "m:0", f"d:{SUN}", "t:0900", "الف", "09120000001")
    out = Chat(spec, st, "bale:2").say("/start", "m:0")
    assert "نوبت خالی وجود ندارد" in text(out)


def test_cancelling_an_appointment_frees_the_time_and_respects_the_deadline():
    spec, st = make(staff=(), cancel=True, deadline=2), MemoryStore()
    a = Chat(spec, st, "bale:1")
    a.say("/start", "m:0", f"d:{SUN}", "t:1000", "الف", "09120000001")
    rid = st.rows["b"][0]["id"]
    one_hour_before = datetime(2026, 10, 4, 9, 0, tzinfo=TEHRAN)                              # deadline is 2h before 10:00
    out = a.say("/start", "m:1", f"x:0:{rid}", now=one_hour_before)
    assert "۲ ساعت" in text(out).replace("2", "۲") and st.rows["b"][0]["status"] == "confirmed"
    out = a.say("/start", "m:1", f"x:0:{rid}", "xy", now=datetime(2026, 10, 4, 7, 59, tzinfo=TEHRAN))
    assert st.rows["b"][0]["status"] == "cancelled"
    assert "t:1000" in [d for _, d in buttons(Chat(spec, st, "bale:2").say("/start", "m:0", f"d:{SUN}"))]   # bookable again


def test_an_appointment_that_already_started_is_not_listed_for_cancelling():
    spec, st = make(staff=(), cancel=True), MemoryStore()
    a = Chat(spec, st, "bale:1")
    a.say("/start", "m:0", f"d:{SUN}", "t:1000", "الف", "09120000001")
    before = datetime(2026, 10, 4, 9, 59, tzinfo=TEHRAN)
    assert "لغو:" in text(a.say("/start", "m:1", now=before))
    started = datetime(2026, 10, 4, 10, 1, tzinfo=TEHRAN)
    assert "هنوز ثبت فعالی ندارید" in text(a.say("/start", "m:1", now=started))


def test_typed_staff_name_works_and_unknown_names_do_not():
    spec, st = make(), MemoryStore()
    c = Chat(spec, st, "bale:1")
    assert "d:" in str(buttons(c.say("/start", "m:0", "سارا")))
    c2 = Chat(spec, st, "bale:2")
    assert "f:0" in str(buttons(c2.say("/start", "m:0", "نامعتبر")))
