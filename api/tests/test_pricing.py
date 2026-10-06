"""Delivery fee and discount codes on catalog orders."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app import engine  # noqa: E402
from app.engine import MemoryStore, handle, new_session  # noqa: E402
from app.spec import BotSpec  # noqa: E402


def make(fee=30000, free_over=0, codes=None, min_total=0, cancel=False):
    return BotSpec.model_validate({
        "name": "کافه", "welcome": "سلام", "menu": [{"label": "سفارش", "block": "o"}],
        "blocks": [{"type": "catalog_order", "id": "o", "title": "منو", "delivery_fee": fee, "free_delivery_over": free_over,
                    "discount_codes": codes or [], "min_total": min_total, "allow_cancel": cancel,
                    "items": [{"id": "latte", "name": "لاته", "price": 100000}, {"id": "cake", "name": "کیک", "price": 50000}],
                    "fields": [{"key": "name", "label": "نام شما؟", "kind": "text"}]}]})


def order(spec, store, cust, *steps):
    s = new_session()
    s["cust"] = cust
    out = None
    for t in ["/start", "m:0", *steps]:
        out = handle(spec, s, t, store)
    return out, s


def text(out):
    return "\n".join(a["text"] for a in out)


def place(spec, store, cust, code=None, items=("i:latte",)):
    steps = []
    for it in items:
        steps += [it, "n:1", "more"]
    steps = steps[:-1] + ["checkout"]
    steps += [code or "dc:no"] if spec.blocks[0].discount_codes else []
    return order(spec, store, cust, *steps, "سارا")


def test_delivery_fee_is_added_and_shown():
    spec, store = make(), MemoryStore()
    out, _ = place(spec, store, "a")
    assert "هزینه‌ی ارسال: 30,000" in text(out) and "جمع کل: 130,000" in text(out)
    assert store.find("o")[0]["total"] == 130000 and store.find("o")[0]["delivery_fee"] == 30000


def test_free_delivery_threshold_counts_the_goods_after_discount():
    codes = [{"code": "OFF50", "percent": 50}]
    spec, store = make(free_over=100000, codes=codes), MemoryStore()
    out, _ = place(spec, store, "a")                   # 100000 goods: free
    assert "رایگان" in text(out) and store.find("o")[0]["total"] == 100000
    out, _ = place(spec, store, "b", code="off50")     # 50000 after discount: below threshold, delivery charged
    assert store.find("o")[1]["total"] == 50000 + 30000


def test_percent_and_amount_codes_and_case_insensitivity():
    spec, store = make(fee=0, codes=[{"code": "SAVE10", "percent": 10}, {"code": "کد۲۰", "amount": 20000}]), MemoryStore()
    place(spec, store, "a", code="save10")
    place(spec, store, "b", code="کد20")               # Latin digits match the Persian-digit code
    assert [r["total"] for r in store.find("o")] == [90000, 80000]
    assert store.find("o")[0]["discount_code"] == "SAVE10"


def test_amount_discount_never_goes_below_zero():
    spec, store = make(fee=0, codes=[{"code": "BIG", "amount": 999999}]), MemoryStore()
    place(spec, store, "a", code="big")
    assert store.find("o")[0]["total"] == 0


def test_wrong_code_asks_again_and_none_is_allowed():
    spec, store = make(fee=0, codes=[{"code": "SAVE10", "percent": 10}]), MemoryStore()
    out, s = order(spec, store, "a", "i:latte", "n:1", "checkout", "bogus")
    assert "معتبر نیست" in text(out) and s["step"] == "code"
    out, s = order(spec, store, "a", "i:latte", "n:1", "checkout", "bogus", "ندارم", "سارا")
    assert store.find("o")[0]["total"] == 100000 and store.find("o")[0]["discount_code"] is None


def test_code_minimum_and_use_limit_with_cancel_giving_the_use_back():
    spec = make(fee=0, cancel=True, codes=[{"code": "ONCE", "percent": 10, "max_uses": 1, "min_total": 90000}])
    store = MemoryStore()
    out, s = order(spec, store, "a", "i:cake", "n:1", "checkout", "once")
    assert "حداقل" in text(out)
    place(spec, store, "a", code="once")
    out, _ = order(spec, store, "b", "i:latte", "n:1", "checkout", "once")
    assert "تمام شده" in text(out)
    row = store.find("o")[0]
    store.update("o", row["id"], status="cancelled")
    out, _ = order(spec, store, "b", "i:latte", "n:1", "checkout", "once")
    assert "اعمال شد" in text(out)


def test_last_use_taken_while_filling_the_form_is_dropped_honestly():
    spec = make(fee=0, codes=[{"code": "ONCE", "percent": 10, "max_uses": 1}])
    store = MemoryStore()
    a = new_session(); a["cust"] = "a"
    b = new_session(); b["cust"] = "b"
    for t in ["/start", "m:0", "i:latte", "n:1", "checkout", "once"]:
        handle(spec, a, t, store)
    for t in ["/start", "m:0", "i:latte", "n:1", "checkout", "once", "علی"]:
        handle(spec, b, t, store)
    out = handle(spec, a, "سارا", store)
    assert "اعمال نشد" in text(out) and [r["total"] for r in store.find("o")] == [90000, 100000]


def test_min_total_uses_goods_not_delivery_and_no_features_means_old_behaviour():
    spec, store = make(fee=0), MemoryStore()
    out, _ = order(spec, store, "a", "i:latte", "n:1", "checkout", "سارا")
    assert "هزینه‌ی ارسال" not in text(out) and store.find("o")[0]["total"] == 100000 and "discount" not in store.find("o")[0]


def test_spec_validation():
    with pytest.raises(ValidationError):
        make(codes=[{"code": "X1", "percent": 10, "amount": 5000}])
    with pytest.raises(ValidationError):
        make(codes=[{"code": "X1"}])
    with pytest.raises(ValidationError):
        make(codes=[{"code": "ab", "percent": 10}, {"code": "AB", "percent": 5}])
    with pytest.raises(ValidationError):
        make(codes=[{"code": "A B", "percent": 10}])
    with pytest.raises(ValidationError):
        make(codes=[{"code": "A1", "percent": 101}])
