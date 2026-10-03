"""Random conversations against every kind of bot: the engine must never crash, state must stay JSON-serialisable,
and the business invariants (capacity, stock) must always hold."""
import json
import random

from app import engine
from app.engine import MemoryStore, handle, new_session
from app.spec import BotSpec
from app.templates import load_template

HOSTILE = ["", " ", "x" * 5000, "p:999999", "pg:-1", "pg:99999999999999999999", "c:99", "c:-1", "s:zzz", "~5", "n:0", "n:-3", "n:99999999999",
           "i:", "m:99", "m:-1", "/admin", "<script>alert(1)</script>", "'; DROP TABLE users;--", "‌‌", "😀", "٠١٢٣", "۰۹۱۲۳۴۵۶۷۸۹",
           "09", "+98912", "back", "all", "search", "more", "checkout", "انصراف", "/start", "/menu", "None", "null", "{}", "[]", "NaN", "-1", "1e9"]

TABLE = BotSpec.model_validate({
    "name": "shop", "welcome": "سلام", "menu": [{"label": "خرید", "block": "shop"}, {"label": "فرم", "block": "f"}],
    "blocks": [{"type": "catalog_order", "id": "shop", "title": "فروشگاه", "source": "table", "min_total": 50000, "max_items": 3},
               {"type": "form", "id": "f", "title": "فرم", "fields": [{"key": "age", "label": "سن", "kind": "number"},
                                                                         {"key": "lvl", "label": "سطح", "kind": "choice", "choices": ["مبتدی", "پیشرفته"]}]},
               {"type": "admin_notify", "id": "n", "on": "shop", "text": "سفارش"}]})
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
    offered = [[] for _ in sessions]
    for _ in range(rnd.randint(*steps)):
        i = rnd.randrange(len(sessions))
        pool = offered[i]
        text = rnd.choice(pool) if pool and rnd.random() < p_valid else rnd.choice(HOSTILE)
        actions = handle(spec, sessions[i], text, st)
        offered[i] = buttons_of(actions)
        json.dumps(sessions[i], ensure_ascii=False)  # state must always be storable
        for a in actions:
            assert a["type"] in ("send", "notify_admin") and isinstance(a["text"], str)
    # invariants
    for b in spec.blocks:
        if b.type == "booking":
            for s in b.slots:
                assert st.count(b.id, slot=s.id, status="confirmed") <= s.capacity
        if b.type == "catalog_order" and b.source == "table":
            assert all(p["stock"] is None or p["stock"] >= 0 for p in st.catalog[b.id])
    return st


def test_fuzz_templates_and_table_catalog():
    engine.STALE_RESETS["count"] = 0
    specs = [(load_template("workshop"), None), (load_template("cafe"), None), (TABLE, PRODUCTS)]
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
