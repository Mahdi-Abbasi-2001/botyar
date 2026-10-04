"""Customers cancelling their own bookings/orders: ownership, capacity, waitlist promotion, deadlines, stock."""
from datetime import timedelta

from app.dates import TEST_NOW
from app.engine import MemoryStore, handle, new_session
from app.spec import BotSpec


def booking_spec(waitlist=True, cap=1, deadline=0, allow=True):
    return BotSpec.model_validate({
        "name": "کلاس", "welcome": "سلام", "menu": [{"label": "ثبت‌نام", "block": "b"}],
        "blocks": [{"type": "booking", "id": "b", "title": "ثبت‌نام کلاس", "waitlist": waitlist, "allow_cancel": allow, "cancel_deadline_hours": deadline,
                    "slots": [{"id": "thu", "label": "پنجشنبه ساعت ۱۰ صبح", "capacity": cap, "weekday": 5, "time": "10:00"}]},
                   {"type": "admin_notify", "id": "n", "on": "b", "text": "ثبت‌نام جدید"}]})


class Chat:
    """One customer in one channel, sharing the bot's store with everyone else."""
    def __init__(self, spec, store, cust, now=TEST_NOW):
        self.spec, self.store, self.now = spec, store, now
        self.s = new_session()
        self.s["cust"] = cust

    def say(self, *texts, now=None):
        out = None
        for t in texts:
            out = handle(self.spec, self.s, t, self.store, now or self.now)
        return out

    def book(self, data="s:thu@20261008", name="علی", phone="09123456789"):
        return self.say("/start", "m:0", data, name, phone)


def text(actions):
    return "\n".join([a["text"] for a in actions if "text" in a] + [b["text"] for a in actions for b in a.get("buttons", [])])


def kinds(actions):
    return [a["type"] for a in actions]


def test_no_cancel_entry_unless_a_block_allows_it():
    spec = booking_spec(allow=False)
    out = Chat(spec, MemoryStore(), "bale:1").say("/start")
    assert [b["text"] for b in out[-1]["buttons"]] == ["ثبت‌نام"]
    out = Chat(booking_spec(), MemoryStore(), "bale:1").say("/start")
    assert [b["text"] for b in out[-1]["buttons"]] == ["ثبت‌نام", "ثبت‌های من"] and out[-1]["buttons"][-1]["data"] == "m:1"


def test_with_nothing_booked_the_list_is_empty():
    out = Chat(booking_spec(), MemoryStore(), "bale:1").say("/start", "m:1")
    assert "هنوز ثبت فعالی ندارید" in text(out)


def test_cancel_frees_the_place_and_tells_the_owner():
    spec, st = booking_spec(waitlist=False), MemoryStore()
    a = Chat(spec, st, "bale:1")
    a.book()
    assert "(تکمیل)" in text(Chat(spec, st, "bale:2").say("/start", "m:0"))        # the only place is taken
    out = a.say("/start", "m:1")
    assert "لغو: پنجشنبه ساعت ۱۰ صبح — 1405/07/16 — تأیید شده" in text(out)
    rec_id = st.rows["b"][0]["id"]
    out = a.say(f"x:0:{rec_id}")
    assert "لغو شود" in text(out)
    out = a.say("xy")
    assert "لغو شد" in text(out) and "notify_admin" in kinds(out) and "❌ لغو توسط مشتری" in text(out)
    assert st.rows["b"][0]["status"] == "cancelled"
    assert "1 جای خالی" in text(Chat(spec, st, "bale:3").say("/start", "m:0"))      # bookable again


def test_nobody_can_cancel_someone_elses_booking_even_with_a_forged_id():
    spec, st = booking_spec(waitlist=False, cap=2), MemoryStore()
    a, b = Chat(spec, st, "bale:1"), Chat(spec, st, "bale:2")
    a.book(phone="09120000001")
    victim = st.rows["b"][0]["id"]
    assert "هنوز ثبت فعالی ندارید" in text(b.say("/start", "m:1"))               # B does not even see A's booking
    b.say("/start", "m:0")  # B is somewhere else; now B tries to inject the forged click after opening his own list
    b.book(phone="09120000002")
    b.say("/start", "m:1")
    out = b.say(f"x:0:{victim}")                                                  # forged: A's record id
    assert "لطفاً یکی از موارد" in text(out)
    assert b.say("xy") is not None and st.find("b", id=victim)[0]["status"] == "confirmed"
    # a customer with no identity (unknown channel) can never cancel anything
    anon = Chat(spec, st, None)
    assert "هنوز ثبت فعالی ندارید" in text(anon.say("/start", "m:1"))


def test_waitlist_promotion_goes_to_the_first_person_waiting_for_the_same_date_and_they_are_told():
    spec, st = booking_spec(waitlist=True, cap=1), MemoryStore()
    a, x, y, b, c = (Chat(spec, st, f"bale:{i}") for i in (1, 2, 3, 4, 5))
    a.book(phone="09120000001")                                  # id1  confirmed, 8 Oct
    x.book(data="s:thu@20261015", phone="09120000002")           # id2  confirmed, 15 Oct
    y.book(data="s:thu@20261015", phone="09120000003")           # id3  WAITLISTED for 15 Oct (lowest waiting id, but another date!)
    b.book(phone="09120000004")                                  # id4  waitlisted, 8 Oct
    c.book(phone="09120000005")                                  # id5  waitlisted, 8 Oct
    assert [r["status"] for r in st.rows["b"]] == ["confirmed", "confirmed", "waitlisted", "waitlisted", "waitlisted"]
    out = a.say("/start", "m:1", "x:0:1", "xy")
    promo = [t for t in out if t["type"] == "notify_customer"]
    assert len(promo) == 1 and promo[0]["cust"] == "bale:4" and "جای خالی شد" in promo[0]["text"]   # b (8 Oct), not y (15 Oct)
    assert [r["status"] for r in st.rows["b"]] == ["cancelled", "confirmed", "waitlisted", "confirmed", "waitlisted"]
    assert "✅ از لیست انتظار تأیید شد" in text(out)                                # the owner hears about both events
    assert sum(r["status"] == "confirmed" and r["date"] == "2026-10-08" for r in st.rows["b"]) == 1   # capacity never exceeded


def test_cancelling_a_waitlisted_booking_promotes_nobody():
    spec, st = booking_spec(waitlist=True, cap=1), MemoryStore()
    a, b, c = (Chat(spec, st, f"bale:{i}") for i in (1, 2, 3))
    a.book(phone="09120000001")
    b.book(phone="09120000002")
    c.book(phone="09120000003")
    out = b.say("/start", "m:1", f"x:0:{st.rows['b'][1]['id']}", "xy")
    assert "notify_customer" not in kinds(out)
    assert [r["status"] for r in st.rows["b"]] == ["confirmed", "cancelled", "waitlisted"]


def test_declining_the_confirmation_keeps_the_booking_and_a_second_cancel_is_refused():
    spec, st = booking_spec(), MemoryStore()
    a = Chat(spec, st, "bale:1")
    a.book()
    rid = st.rows["b"][0]["id"]
    a.say("/start", "m:1", f"x:0:{rid}", "xn")
    assert st.rows["b"][0]["status"] == "confirmed"
    a.say("/start", "m:1", f"x:0:{rid}", "xy")
    assert st.rows["b"][0]["status"] == "cancelled"
    # an old confirmation button pressed again
    a.s.update(block="__my__", step="confirm", data={"bi": 0, "rid": rid})
    out = a.say("xy")
    assert "دیگر قابل لغو نیست" in text(out) and st.rows["b"][0]["status"] == "cancelled"


def test_deadline_before_a_dated_class():
    spec, st = booking_spec(deadline=24), MemoryStore()
    a = Chat(spec, st, "bale:1")
    a.book()                                                                       # class: Thursday 2026-10-08 10:00
    rid = st.rows["b"][0]["id"]
    wed_late = TEST_NOW.replace(day=7, hour=10, minute=1)                         # 23h59m before
    out = a.say("/start", "m:1", f"x:0:{rid}", now=wed_late)
    assert "۲۴ ساعت" in text(out).replace("24", "۲۴") and st.rows["b"][0]["status"] == "confirmed"
    wed_early = TEST_NOW.replace(day=7, hour=9, minute=59)                        # 24h01m before
    out = a.say("/start", "m:1", f"x:0:{rid}", "xy", now=wed_early)
    assert st.rows["b"][0]["status"] == "cancelled"


def test_past_bookings_are_not_listed():
    spec, st = booking_spec(), MemoryStore()
    a = Chat(spec, st, "bale:1")
    a.book()
    after = TEST_NOW + timedelta(days=6)                                           # Friday 9 Oct: the class is over
    assert "هنوز ثبت فعالی ندارید" in text(a.say("/start", "m:1", now=after))


ORDER = BotSpec.model_validate({
    "name": "فروشگاه", "welcome": "سلام", "menu": [{"label": "خرید", "block": "shop"}],
    "blocks": [{"type": "catalog_order", "id": "shop", "title": "فروشگاه", "source": "table", "allow_cancel": True, "cancel_window_minutes": 30},
               {"type": "admin_notify", "id": "n", "on": "shop", "text": "سفارش جدید"}]})
PRODUCTS = [{"name": "کفش", "category": "", "price": 100000, "stock": 5, "options": [], "description": ""}]


def order_store():
    st = MemoryStore()
    st.load_catalog("shop", [dict(p) for p in PRODUCTS])
    return st


def test_order_cancel_within_the_window_restores_stock_and_after_it_is_refused():
    st = order_store()
    a = Chat(ORDER, st, "bale:1")
    a.say("/start", "m:0", "p:1", "n:2", "checkout", "مریم", "09123456789")
    assert st.product("shop", 1)["stock"] == 3
    rid = st.rows["shop"][0]["id"]
    late = TEST_NOW + timedelta(minutes=45)
    out = a.say("/start", "m:1", f"x:0:{rid}", now=late)
    assert "۳۰ دقیقه" in text(out).replace("30", "۳۰") and st.rows["shop"][0]["status"] == "new" and st.product("shop", 1)["stock"] == 3
    out = a.say("/start", "m:1", f"x:0:{rid}", "xy", now=TEST_NOW + timedelta(minutes=10))
    assert "سفارش شما لغو شد" in text(out) and st.rows["shop"][0]["status"] == "cancelled"
    assert st.product("shop", 1)["stock"] == 5                                     # the 2 pairs are back on the shelf


def test_records_are_stamped_internally_but_the_summary_never_leaks_the_identity():
    st = order_store()
    a = Chat(ORDER, st, "bale:777")
    out = a.say("/start", "m:0", "p:1", "n:1", "checkout", "مریم", "09123456789")
    assert st.rows["shop"][0]["_cust"] == "bale:777" and "_at" in st.rows["shop"][0]
    assert "bale:777" not in text(out) and "_cust" not in text(out)
