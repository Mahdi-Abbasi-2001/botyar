"""Delivery zones: the customer picks where the order goes (e.g. Tehran / other cities) and that area's fee is charged."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.engine import MemoryStore, handle, new_session  # noqa: E402
from app.spec import BotSpec  # noqa: E402

ZONES = [{"label": "تهران", "fee": 100000}, {"label": "سایر شهرها", "fee": 200000}, {"label": "تحویل حضوری", "fee": 0}]


def make(zones=ZONES, free_over=0, codes=None, fee=0):
    return BotSpec.model_validate({
        "name": "لباس", "welcome": "سلام", "menu": [{"label": "سفارش", "block": "o"}],
        "blocks": [{"type": "catalog_order", "id": "o", "title": "محصولات", "delivery_zones": zones, "delivery_fee": fee,
                    "free_delivery_over": free_over, "discount_codes": codes or [],
                    "items": [{"id": "shirt", "name": "پیراهن", "price": 500000}],
                    "fields": [{"key": "name", "label": "نام شما؟", "kind": "text"}]},
                   {"type": "admin_notify", "id": "n", "on": "o", "text": "سفارش جدید"}]})


def run(spec, store, *steps):
    s = new_session()
    s["cust"] = "c1"
    outs = []
    for t in ["/start", "m:0", "i:shirt", "n:1", "checkout", *steps]:
        outs = handle(spec, s, t, store)
    return outs


def text(out):
    return "\n".join(a.get("text", "") for a in out)


def test_checkout_asks_for_the_area_and_charges_its_fee():
    spec, store = make(), MemoryStore()
    s = new_session()
    s["cust"] = "c1"
    for t in ["/start", "m:0", "i:shirt", "n:1"]:
        handle(spec, s, t, store)
    ask = handle(spec, s, "checkout", store)
    assert "محل ارسال را انتخاب کنید" in text(ask)
    assert [b["text"] for b in ask[-1]["buttons"]] == ["تهران - 100,000 تومان", "سایر شهرها - 200,000 تومان", "تحویل حضوری (ارسال رایگان)"]
    out = [handle(spec, s, "z:1", store), handle(spec, s, "مریم", store)][-1]
    assert "هزینه‌ی ارسال (سایر شهرها): 200,000 تومان" in text(out) and "جمع کل: 700,000" in text(out)
    rec = store.find("o")[0]
    assert rec["total"] == 700000 and rec["delivery_fee"] == 200000 and rec["delivery_zone"] == "سایر شهرها"
    assert any(a.get("type") == "notify_admin" and "محل ارسال: سایر شهرها" in a["text"] for a in out)


def test_free_zone_and_free_delivery_threshold():
    spec, store = make(), MemoryStore()
    out = run(spec, store, "z:2", "مریم")
    assert "هزینه‌ی ارسال (تحویل حضوری): رایگان" in text(out) and store.find("o")[0]["total"] == 500000
    spec, store = make(free_over=400000), MemoryStore()
    out = run(spec, store, "z:0", "مریم")           # goods 500,000 ≥ 400,000: Tehran delivery is free too
    assert "هزینه‌ی ارسال (تهران): رایگان" in text(out) and store.find("o")[0]["total"] == 500000


def test_zone_comes_before_the_discount_code_and_both_apply():
    spec, store = make(codes=[{"code": "OFF10", "percent": 10}]), MemoryStore()
    s = new_session()
    s["cust"] = "c1"
    for t in ["/start", "m:0", "i:shirt", "n:1", "checkout"]:
        handle(spec, s, t, store)
    assert "کد تخفیف دارید" in text(handle(spec, s, "z:0", store))
    handle(spec, s, "off10", store)
    out = handle(spec, s, "مریم", store)
    assert "جمع کل: 550,000" in text(out)          # 500,000 - 10% + 100,000 Tehran


def test_typing_the_area_works_and_nonsense_asks_again():
    spec, store = make(), MemoryStore()
    out = run(spec, store, "شیراز")
    assert "لطفاً یکی از گزینه‌ها را انتخاب کنید" in text(out) and "محل ارسال" in text(out)
    out = run(spec, store, "سایر شهرها", "مریم")
    assert store.find("o")[0]["delivery_zone"] == "سایر شهرها"


def test_without_zones_nothing_changes():
    spec, store = make(zones=[], fee=30000), MemoryStore()
    out = run(spec, store, "مریم")
    assert "هزینه‌ی ارسال: 30,000" in text(out) and "delivery_zone" not in store.find("o")[0]


@pytest.mark.parametrize("zones,fee", [(ZONES[:1], 0), (ZONES, 30000), ([ZONES[0], ZONES[0]], 0)])
def test_invalid_zone_setups_are_rejected(zones, fee):
    with pytest.raises(ValidationError):
        make(zones=zones, fee=fee)
