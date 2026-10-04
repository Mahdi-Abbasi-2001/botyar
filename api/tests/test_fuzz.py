"""Random conversations against every kind of bot: the engine must never crash, state must stay JSON-serialisable,
and the business invariants (capacity, stock) must always hold."""
import json
import random

from datetime import timedelta

from app import engine
from app.dates import TEST_NOW
from app.engine import MemoryStore, handle, new_session
from app.spec import BotSpec
from app.templates import load_template

HOSTILE = ["", " ", "x" * 5000, "p:999999", "pg:-1", "pg:99999999999999999999", "c:99", "c:-1", "s:zzz", "~5", "n:0", "n:-3", "n:99999999999",
           "i:", "m:99", "m:-1", "/admin", "<script>alert(1)</script>", "'; DROP TABLE users;--", "‌‌", "😀", "٠١٢٣", "۰۹۱۲۳۴۵۶۷۸۹",
           "09", "+98912", "f:0", "f:1", "d:20261004", "d:20261010", "t:0900", "t:1000", "t:1200", "tp:1", "x:0:1", "x:0:2", "x:1:1", "x:99:1", "x:0:-1", "x:0:99999999999", "xy", "xn", "m:2", "m:3", "ثبت‌های من", "back", "all", "search", "more", "checkout", "انصراف", "/start", "/menu", "None", "null", "{}", "[]", "NaN", "-1", "1e9"]

TABLE = BotSpec.model_validate({
    "name": "shop", "welcome": "سلام", "menu": [{"label": "خرید", "block": "shop"}, {"label": "فرم", "block": "f"}],
    "blocks": [{"type": "catalog_order", "id": "shop", "title": "فروشگاه", "source": "table", "min_total": 50000, "max_items": 3,
                "allow_cancel": True, "cancel_window_minutes": 30},
               {"type": "form", "id": "f", "title": "فرم", "fields": [{"key": "age", "label": "سن", "kind": "number"},
                                                                         {"key": "lvl", "label": "سطح", "kind": "choice", "choices": ["مبتدی", "پیشرفته"]}]},
               {"type": "admin_notify", "id": "n", "on": "shop", "text": "سفارش"}]})
BOOKING = BotSpec.model_validate({
    "name": "bk", "welcome": "سلام", "menu": [{"label": "ثبت‌نام", "block": "b"}],
    "blocks": [{"type": "booking", "id": "b", "title": "کلاس", "waitlist": True, "allow_cancel": True, "cancel_deadline_hours": 24, "occurrences": 2,
                "slots": [{"id": "thu", "label": "پنجشنبه", "capacity": 2, "weekday": 5, "time": "10:00"},
                          {"id": "once", "label": "رویداد", "capacity": 1}]},
               {"type": "admin_notify", "id": "n", "on": "b", "text": "ثبت‌نام"}]})
APPT = BotSpec.model_validate({
    "name": "ap", "welcome": "سلام", "menu": [{"label": "نوبت", "block": "b"}],
    "blocks": [{"type": "booking", "id": "b", "title": "نوبت‌دهی", "allow_cancel": True, "cancel_deadline_hours": 1,
                "schedule": {"days": [{"weekday": 0, "start": "09:00", "end": "13:00"}, {"weekday": 1, "start": "09:00", "end": "13:00"}],
                             "duration_minutes": 60, "capacity": 1, "days_ahead": 7, "staff": ["سارا", "مینا"], "break_start": "11:00", "break_end": "12:00"}},
               {"type": "admin_notify", "id": "n", "on": "b", "text": "نوبت"}]})
PRODUCTS = [{"name": f"کالا {i}", "category": ["الف", "ب", ""][i % 3], "price": 10000 * (i + 1), "stock": [None, 0, 1, 3][i % 4],
             "options": [{"name": "سایز", "choices": ["۴۰", "M"]}] if i % 2 else [], "description": ""} for i in range(14)]


def buttons_of(actions):
    return [b["data"] for a in actions if a["type"] == "send" for b in a.get("buttons", [])]


def run(spec, seed, catalog=None, steps=(5, 60), p_valid=0.7):
    rnd = random.Random(seed)
    st = MemoryStore()
    for b in spec.blocks:
        if b.type == "catalog_order" and b.source == "table":
            st.load_catalog(b.id, [dict(p) for p in (catalog or [])])
    sessions = [new_session() for _ in range(3)]  # three customers share the store
    for k, sess in enumerate(sessions):
        sess["cust"] = f"fz:{k}"
    offered = [[] for _ in sessions]
    for _ in range(rnd.randint(*steps)):
        i = rnd.randrange(len(sessions))
        pool = offered[i]
        text = rnd.choice(pool) if pool and rnd.random() < p_valid else rnd.choice(HOSTILE)
        now = TEST_NOW + timedelta(minutes=rnd.choice([0, 0, 5, 20, 45, 600, 3000]))  # the clock moves: windows and deadlines get hit
        actions = handle(spec, sessions[i], text, st, now)
        offered[i] = buttons_of(actions)
        json.dumps(sessions[i], ensure_ascii=False)  # state must always be storable
        for a in actions:
            assert a["type"] in ("send", "notify_admin", "notify_customer") and isinstance(a["text"], str)
    # invariants
    for b in spec.blocks:
        if b.type == "booking" and b.schedule:
            seen = {(r.get("staff", ""), r["date"], r["time"]) for r in st.rows.get(b.id, []) if r.get("status") == "confirmed"}
            for staff, day, hhmm in seen:
                n = st.count(b.id, slot="appt", status="confirmed", date=day, time=hhmm, **({"staff": staff} if staff else {}))
                assert n <= b.schedule.capacity, f"double-booked {staff} {day} {hhmm}"
        if b.type == "booking" and not b.schedule:
            for s in b.slots:
                if s.weekday is None:   # one-off slot: capacity counts for ever
                    assert st.count(b.id, slot=s.id, status="confirmed") <= s.capacity, f"overbooked one-off {s.id}"
                else:                   # weekly slot: capacity is per date
                    for day in {r["date"] for r in st.rows.get(b.id, []) if r.get("slot") == s.id and r.get("date")}:
                        assert st.count(b.id, slot=s.id, status="confirmed", date=day) <= s.capacity, f"overbooked {s.id} {day}"
        if b.type == "catalog_order" and b.source == "table":
            assert all(p["stock"] is None or p["stock"] >= 0 for p in st.catalog[b.id])
            # conservation law: shelf + (non-cancelled orders) == the original stock, whatever mix of buy / cancel happened
            for p, original in zip(st.catalog[b.id], [q["stock"] for q in catalog]):
                if original is None:
                    continue
                sold = sum(it.get("qty", 1) for r in st.rows.get("shop", []) if r["status"] != "cancelled" for it in r["items"] if it["id"] == p["id"])
                assert p["stock"] + sold == original, f"stock not conserved for product {p['id']}: shelf {p['stock']} + sold {sold} != {original}"
    return st


def test_fuzz_templates_and_table_catalog():
    engine.STALE_RESETS["count"] = 0
    specs = [(load_template("workshop"), None), (load_template("cafe"), None), (TABLE, PRODUCTS), (BOOKING, None), (APPT, None)]
    for spec, catalog in specs:
        for seed in range(700):
            try:
                run(spec, seed, catalog)
            except Exception as e:  # report which seed to replay
                raise AssertionError(f"{spec.name} seed={seed}: {type(e).__name__}: {e}") from e
    assert engine.STALE_RESETS["count"] == 0, "the stale-state recovery fired although the bot never changed: a real engine bug is being masked"


def test_fuzz_deep_table_shop_reaches_checkouts():
    engine.STALE_RESETS["count"] = 0
    """Longer, mostly-valid conversations so the multi-step catalog flow (options, quantity, stock, checkout) is really exercised."""
    orders = 0
    for seed in range(1500):
        try:
            st = run(TABLE, 10_000 + seed, PRODUCTS, steps=(60, 180), p_valid=0.93)
        except Exception as e:
            raise AssertionError(f"deep seed={10_000 + seed}: {type(e).__name__}: {e}") from e
        orders += len(st.rows.get("shop", []))
    assert orders >= 100, f"fuzz too shallow: only {orders} completed orders"
    assert engine.STALE_RESETS["count"] == 0


def test_fuzz_cancellation_paths_are_reached_and_everything_is_conserved():
    """Capacity per date and the stock conservation law must hold through any mix of buying, cancelling and waiting."""
    engine.STALE_RESETS["count"] = 0
    cancelled = {"b": 0, "shop": 0}
    for spec, cat, key, kw in [(BOOKING, None, "b", dict(steps=(40, 120), p_valid=0.9)), (TABLE, PRODUCTS, "shop", dict(steps=(80, 200), p_valid=0.95))]:
        for seed in range(800):
            try:
                st = run(spec, 50_000 + seed, cat, **kw)
            except Exception as e:
                raise AssertionError(f"{spec.name} seed={50_000 + seed}: {type(e).__name__}: {e}") from e
            cancelled[key] += sum(r.get("status") == "cancelled" for r in st.rows.get(key, []))
    assert cancelled["b"] >= 50 and cancelled["shop"] >= 15, f"fuzz too shallow: {cancelled}"
    assert engine.STALE_RESETS["count"] == 0


def test_fuzz_appointments_are_reached_and_never_double_booked():
    engine.STALE_RESETS["count"] = 0
    booked = 0
    for seed in range(1200):
        try:
            st = run(APPT, 70_000 + seed, None, steps=(30, 90), p_valid=0.92)
        except Exception as e:
            raise AssertionError(f"appointments seed={70_000 + seed}: {type(e).__name__}: {e}") from e
        booked += len(st.rows.get("b", []))
    assert booked >= 300, f"fuzz too shallow: {booked} appointments"
    assert engine.STALE_RESETS["count"] == 0
