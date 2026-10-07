"""Booking features: services of different lengths, prices, holidays, minimum notice, a per-customer limit, groups."""
from app.dates import TEST_NOW
from app.engine import MemoryStore, cancel_record, handle, new_session
from app.spec import BotSpec

SUN = "20261004"  # test clock: Saturday 1405/07/11 12:00; Sunday is 1405/07/12


def salon(services=True, **block):
    sch = {"days": [{"weekday": 0, "start": "09:00", "end": "18:00"}, {"weekday": 1, "start": "09:00", "end": "12:00"}], "duration_minutes": 30, "days_ahead": 7}
    if services:
        sch["services"] = [{"id": "cut", "name": "کوتاهی مو", "duration_minutes": 30, "price": 250000},
                           {"id": "color", "name": "رنگ مو", "duration_minutes": 90, "price": 900000}]
    return BotSpec.model_validate({"name": "سالن", "welcome": "سلام", "menu": [{"label": "نوبت", "block": "b"}],
                                   "blocks": [{"type": "booking", "id": "b", "title": "نوبت‌دهی", "schedule": sch, "allow_cancel": True, **block}]})


def event(**block):
    return BotSpec.model_validate({"name": "تور", "welcome": "سلام", "menu": [{"label": "ثبت‌نام", "block": "b"}],
                                   "blocks": [{"type": "booking", "id": "b", "title": "تور", "slots": [{"id": "t1", "label": "تور جمعه", "capacity": 5, "price": 1200000}], **block}]})


class Chat:
    def __init__(self, spec, store, cust):
        self.spec, self.store, self.s = spec, store, new_session()
        self.s["cust"] = cust

    def say(self, *texts):
        out = []
        for t in texts:
            out = handle(self.spec, self.s, t, self.store, TEST_NOW)
        return out


def btns(out):
    return [b["text"] for a in out for b in a.get("buttons", [])]


def data(out):
    return [b["data"] for a in out for b in a.get("buttons", [])]


def txt(out):
    return "\n".join(a.get("text", "") for a in out)


def test_services_show_length_and_price_and_long_ones_block_overlapping_times():
    spec, store = salon(), MemoryStore()
    out = Chat(spec, store, "a").say("/start", "m:0")
    assert btns(out)[-2:] == ["کوتاهی مو — 30 دقیقه — 250,000 تومان", "رنگ مو — 90 دقیقه — 900,000 تومان"]
    Chat(spec, store, "a").say("/start", "m:0", "sv:1", f"d:{SUN}", "t:0900", "سارا", "09121234567")  # colouring 09:00-10:30
    row = store.find("b")[0]
    assert row["service"] == "رنگ مو" and row["price"] == 900000 and "رنگ مو" in row["slot_label"]
    cut = Chat(spec, store, "b").say("/start", "m:0", "sv:0", f"d:{SUN}")
    assert "t:0900" not in data(cut) and "t:1000" not in data(cut) and "t:1030" in data(cut)
    color = Chat(spec, store, "c").say("/start", "m:0", "sv:1", f"d:{SUN}")
    assert data(color)[:1] == ["t:1030"]  # 10:30-12:00 is the only 90-minute gap left on Sunday


def test_closed_days_and_minimum_notice():
    spec = salon(services=False, closed_dates=["1405/07/12"], min_notice_hours=3)
    out = Chat(spec, MemoryStore(), "a").say("/start", "m:0")
    assert f"d:{SUN}" not in data(out)                       # Sunday is a holiday
    today = Chat(spec, MemoryStore(), "a").say("/start", "m:0", "d:20261003")
    assert data(today)[0] == "t:1500"                         # 12:00 now + 3 hours notice


def test_one_active_booking_per_customer_but_rescheduling_still_works():
    spec, store = salon(services=False, max_active_per_customer=1), MemoryStore()
    c = Chat(spec, store, "a")
    c.say("/start", "m:0", f"d:{SUN}", "t:0900", "سارا", "09121234567")
    assert "۱ نوبت فعال دارید" in txt(c.say("/start", "m:0")) and "نوبت‌های من" in txt(c.say("/start", "m:0"))
    c.say("/start", "m:1", "x:0:1", "xr", f"d:{SUN}", "t:1000")  # move it: allowed
    assert [(r["time"], r["status"]) for r in store.find("b")] == [("09:00", "cancelled"), ("10:00", "confirmed")]


def test_slot_price_and_party_size_take_places_and_waitlist_promotes_a_group_that_fits():
    spec, store = event(max_party=4, waitlist=True), MemoryStore()
    out = Chat(spec, store, "a").say("/start", "m:0")
    assert "تور جمعه · 1,200,000 تومان (5 جای خالی)" in btns(out)
    assert "چند نفر هستید" in txt(Chat(spec, store, "a").say("/start", "m:0", "s:t1"))
    Chat(spec, store, "a").say("/start", "m:0", "s:t1", "pz:4", "علی", "09121234567")
    assert "(1 جای خالی)" in btns(Chat(spec, store, "x").say("/start", "m:0"))[0]
    Chat(spec, store, "b").say("/start", "m:0", "s:t1", "pz:3", "مینا", "09121234568")   # does not fit: waitlisted
    Chat(spec, store, "c").say("/start", "m:0", "s:t1", "pz:1", "رضا", "09121234569")     # fits: confirmed
    assert [(r["party"], r["status"]) for r in store.find("b")] == [(4, "confirmed"), (3, "waitlisted"), (1, "confirmed")]
    _, promoted = cancel_record(spec, store, TEST_NOW, spec.blocks[0], store.find("b")[0], by="customer")
    assert promoted["party"] == 3 and store.find("b")[1]["status"] == "confirmed"   # 4 places freed, the group of 3 moves up


def test_a_group_that_does_not_fit_without_a_waitlist_is_told_how_many_places_are_left():
    spec, store = event(max_party=4), MemoryStore()
    Chat(spec, store, "a").say("/start", "m:0", "s:t1", "pz:4", "علی", "09121234567")
    out = Chat(spec, store, "b").say("/start", "m:0", "s:t1", "pz:2")
    assert "فقط ۱ جای خالی" in txt(out)
