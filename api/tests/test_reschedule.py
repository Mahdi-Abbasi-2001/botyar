"""Customers change the time of their own booking: the old place is released only when the new one is certain."""
from app.dates import TEST_NOW
from app.engine import MemoryStore, handle, new_session
from app.spec import BotSpec

from tests.test_appointments import Chat, SUN, SAT_NEXT, make, text


def slots_spec(waitlist=False, cap=1):
    return BotSpec.model_validate({"name": "کارگاه", "welcome": "سلام", "menu": [{"label": "ثبت‌نام", "block": "b"}],
        "blocks": [{"type": "booking", "id": "b", "title": "کارگاه", "allow_cancel": True, "waitlist": waitlist, "occurrences": 2,
                    "slots": [{"id": "a", "label": "الف", "capacity": cap}, {"id": "c", "label": "ب", "capacity": cap}]},
                   {"type": "admin_notify", "id": "n", "on": "b", "text": "ثبت جدید"}]})


def test_appointment_reschedule_moves_the_place_and_keeps_contact_details():
    spec, st = make(cancel=True), MemoryStore()
    c = Chat(spec, st, "bale:1")
    c.book(0, SUN, "0900", "علی", "09121111111")
    mine = c.say("/start", "m:1")
    assert "xr" not in text(mine)
    pick = next(b["data"] for a in mine for b in a.get("buttons", []) if b["data"].startswith("x:"))
    out = c.say(pick)
    assert "xr" in [b["data"] for a in out for b in a.get("buttons", [])]
    c.say("xr", "f:0", f"d:{SUN}")
    out = c.say("t:1000")
    rows = st.find("b")
    assert [r["status"] for r in rows] == ["cancelled", "confirmed"]
    assert rows[1]["time"] == "10:00" and rows[1]["name"] == "علی" and rows[1]["phone"] == "09121111111"
    assert "زمان شما تغییر کرد" in text(out) and any(a["type"] == "notify_admin" and "تغییر زمان" in a["text"] for a in out)
    assert c.s["block"] is None


def test_a_taken_or_own_time_is_refused_and_the_old_booking_survives():
    spec, st = make(cancel=True), MemoryStore()
    a, b = Chat(spec, st, "bale:1"), Chat(spec, st, "bale:2")
    a.book(0, SUN, "0900")
    b.book(0, SUN, "1000", "رضا", "09122222222")
    mine = a.say("/start", "m:1")
    a.say(next(x["data"] for m in mine for x in m.get("buttons", []) if x["data"].startswith("x:")), "xr", "f:0", f"d:{SUN}")
    out = a.say("t:0900")
    assert "خالی نیست" in text(out) and [r["status"] for r in st.find("b")] == ["confirmed", "confirmed"]  # the own time is simply not offered
    out = a.say("t:1000")                                   # not offered: already taken by someone else
    assert [r["status"] for r in st.find("b") if r["name"] == "علی"] == ["confirmed"] and a.s["block"] == "b"


def test_slot_booking_reschedule_never_goes_to_a_waitlist_and_releases_the_old_place_for_the_waiting_customer():
    spec, st = slots_spec(waitlist=True), MemoryStore()
    ids = {}
    for cust, slot in (("bale:1", 0), ("bale:2", 1)):
        s = new_session(); s["cust"] = cust
        out = handle(spec, s, "/start", st)
        out = handle(spec, s, "m:0", st)
        data = [b["data"] for a in out for b in a.get("buttons", [])]
        handle(spec, s, data[slot], st)
        for t in ("علی", "09123456789"):
            handle(spec, s, t, st)
    w = new_session(); w["cust"] = "bale:3"                  # waitlisted for the first slot
    out = handle(spec, w, "/start", st); out = handle(spec, w, "m:0", st)
    handle(spec, w, [b["data"] for a in out for b in a.get("buttons", [])][0], st)
    for t in ("سارا", "09121234567"):
        handle(spec, w, t, st)
    assert [r["status"] for r in st.find("b")] == ["confirmed", "confirmed", "waitlisted"]
    # customer 1 wants the (full) second slot: refused, keeps the first
    s = new_session(); s["cust"] = "bale:1"
    out = handle(spec, s, "/start", st)
    out = handle(spec, s, "m:1", st)
    pick = next(x["data"] for a in out for x in a.get("buttons", []) if x["data"].startswith("x:"))
    handle(spec, s, pick, st)
    out = handle(spec, s, "xr", st)
    datas = [b["data"] for a in out for b in a.get("buttons", [])]
    out = handle(spec, s, datas[1], st)
    assert [r["status"] for r in st.find("b")][:1] == ["confirmed"] and s["block"] == "b"
    assert not any(a["type"] == "notify_customer" for a in out)


def test_owner_cannot_be_bypassed_by_forging_replace_and_deadline_applies():
    spec = make(cancel=True, deadline=3)
    st = MemoryStore()
    c = Chat(spec, st, "bale:1")
    c.book(0, SUN, "0900")
    from datetime import timedelta
    late = (TEST_NOW + timedelta(days=1)).replace(hour=7, minute=0)         # 2 hours before the appointment
    mine = c.say("/start", "m:1", now=late)
    out = c.say(next(x["data"] for m in mine for x in m.get("buttons", []) if x["data"].startswith("x:")), now=late)
    assert "مهلت" in text(out) or "لغو" in text(out)
