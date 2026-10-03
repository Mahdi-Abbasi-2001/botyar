from app.engine import MemoryStore, handle, new_session
from app.spec import BotSpec

SPEC = BotSpec.model_validate({
    "name": "فروشگاه لباس", "welcome": "سلام!",
    "menu": [{"label": "خرید", "block": "shop"}],
    "blocks": [
        {"type": "catalog_order", "id": "shop", "title": "فروشگاه", "source": "table", "min_total": 100000, "max_items": 3},
        {"type": "admin_notify", "id": "n", "on": "shop", "text": "سفارش جدید"},
    ],
})

SIZES = [{"name": "سایز", "choices": ["۴۰", "۴۲", "M"]}]
PRODUCTS = (
    [{"name": f"پیراهن {i}", "category": "مردانه", "price": 450000, "stock": 5 if i == 1 else None, "options": SIZES, "description": ""} for i in range(1, 7)]
    + [{"name": f"مانتو {i}", "category": "زنانه", "price": 800000, "stock": 2, "options": [], "description": ""} for i in range(1, 4)]
    + [{"name": "شال مشکی", "category": "اکسسوری", "price": 90000, "stock": 0, "options": [], "description": ""}]
)


def store():
    s = MemoryStore()
    s.load_catalog("shop", PRODUCTS)
    return s


def say(st, sess, *texts):
    out = []
    for t in texts:
        out = handle(SPEC, sess, t, st)
    return out


def see(actions):
    return "\n".join([a["text"] for a in actions] + [b["text"] for a in actions for b in a.get("buttons", [])])


def test_categories_then_paginated_list():
    st, sess = store(), new_session()
    out = say(st, sess, "/start", "m:0")
    assert "مردانه" in see(out) and "زنانه" in see(out) and "اکسسوری" in see(out)
    out = say(st, sess, "c:0")
    assert "صفحه 1 از 2" in see(out) and "پیراهن 1" in see(out) and "پیراهن 6" not in see(out)
    out = say(st, sess, "pg:1")
    assert "صفحه 2 از 2" in see(out) and "پیراهن 6" in see(out)
    assert "صفحه 2 از 2" in see(say(st, sess, "pg:99"))  # an out-of-range page clamps to the last one


def test_persian_size_matches_ascii_digits_and_stock_is_decremented():
    st, sess = store(), new_session()
    say(st, sess, "/start", "m:0", "c:0", "p:1")  # product 1 (stock 5) asks for size
    out = say(st, sess, "42")                      # typed with ASCII digits, button is «۴۲»
    assert "تعداد" in see(out)
    out = say(st, sess, "n:2")
    assert "× 2" in see(out)
    say(st, sess, "checkout", "مریم", "09123456789")
    row = st.rows["shop"][0]
    assert row["total"] == 900000 and row["items"][0]["options"] == {"سایز": "۴۲"} and row["items"][0]["qty"] == 2
    assert st.product("shop", 1)["stock"] == 3


def test_quantity_over_stock_is_rejected():
    st, sess = store(), new_session()
    say(st, sess, "/start", "m:0", "c:0", "p:1", "M")
    out = say(st, sess, "9")
    assert "حداکثر موجودی" in see(out) and "5" in see(out)


def test_out_of_stock_product_cannot_be_picked():
    st, sess = store(), new_session()
    out = say(st, sess, "/start", "m:0", "c:2", "p:10")
    assert "موجود نیست" in see(out)


def test_search_normalises_arabic_letters():
    st, sess = store(), new_session()
    say(st, sess, "/start", "m:0", "search")
    out = say(st, sess, "پيراهن")  # Arabic ي in the query
    assert "نتیجه‌ی جستجو" in see(out) and "پیراهن 1" in see(out)
    out = say(st, sess, "ژاکت")    # free text in the list = a new search
    assert "محصولی پیدا نشد" in see(out)


def test_two_customers_race_for_the_last_items():
    st = store()
    a, b = new_session(), new_session()
    for s in (a, b):  # both put 2 of the "مانتو" (stock 2) in their carts
        say(st, s, "/start", "m:0", "c:1", "p:7", "n:2")
    say(st, b, "checkout", "ب", "09120000002")
    assert st.product("shop", 7)["stock"] == 0
    out = say(st, a, "checkout", "الف", "09120000001")  # a's contact step triggers the reservation
    assert "کافی نیست" in see(out) and a["data"]["_cart"] == []
    assert len(st.rows["shop"]) == 1  # only b's order exists


def test_empty_cart_cannot_check_out_after_stock_removal():
    st = store()
    a, b = new_session(), new_session()
    for s_ in (a, b):
        say(st, s_, "/start", "m:0", "c:1", "p:7", "n:2")
    say(st, b, "checkout", "ب", "09120000002")
    say(st, a, "checkout", "الف", "09120000001")  # reservation fails, a's cart is now empty
    assert a["step"] == "more" and a["data"]["_cart"] == []
    assert "خالی" in see(say(st, a, "checkout"))


def test_minimum_total_is_enforced_for_table_catalogs():
    st, sess = store(), new_session()
    cheap = [{"name": "جوراب", "category": "", "price": 30000, "stock": None, "options": [], "description": ""}]
    st.load_catalog("shop", cheap)
    say(st, sess, "/start", "m:0", "p:1", "n:1")
    assert "حداقل" in see(say(st, sess, "checkout"))


def test_empty_catalog_message():
    st, sess = MemoryStore(), new_session()
    out = say(st, sess, "/start", "m:0")
    assert "محصولی ثبت نشده" in see(out) and sess["block"] is None


def test_spec_inline_still_requires_items():
    try:
        BotSpec.model_validate({"name": "x", "welcome": "x", "menu": [{"label": "a", "block": "o"}],
                                "blocks": [{"type": "catalog_order", "id": "o", "title": "t"}]})
        assert False
    except ValueError as e:
        assert "at least one item" in str(e)
