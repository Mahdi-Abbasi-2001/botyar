"""Shop features: option prices, quantities on short menus, viewing/editing the cart, product descriptions, order hours."""
from datetime import datetime

from app.dates import TEHRAN, TEST_NOW
from app.engine import MemoryStore, handle, new_session
from app.spec import BotSpec


def cafe(**block):
    return BotSpec.model_validate({"name": "کافه", "welcome": "سلام", "menu": [{"label": "سفارش", "block": "o"}],
                                   "blocks": [{"type": "catalog_order", "id": "o", "title": "منو",
                                               "items": [{"id": "latte", "name": "لاته", "price": 100000,
                                                          "options": [{"name": "سایز", "choices": ["معمولی", "بزرگ"], "prices": [0, 30000]}]},
                                                         {"id": "cake", "name": "کیک", "price": 80000}],
                                               "fields": [{"key": "name", "label": "نام شما؟"}], **block}]})


class Chat:
    def __init__(self, spec, store=None, now=TEST_NOW):
        self.spec, self.store, self.now, self.s = spec, store or MemoryStore(), now, new_session()
        self.s["cust"] = "c1"

    def say(self, *texts):
        out = []
        for t in texts:
            out = handle(self.spec, self.s, t, self.store, self.now)
        return out


def btns(out):
    return [b["text"] for a in out for b in a.get("buttons", []) if b["data"] != "/menu"]


def txt(out):
    return "\n".join(a.get("text", "") for a in out)


def test_option_price_is_shown_and_added():
    c = Chat(cafe())
    out = c.say("/start", "m:0", "i:latte")
    assert btns(out) == ["معمولی", "بزرگ (+30,000 تومان)"]
    out = c.say("بزرگ", "checkout", "سارا")
    assert "جمع کل: 130,000" in txt(out) and c.store.find("o")[0]["items"][0]["price"] == 130000


def test_short_menus_can_ask_for_a_quantity():
    c = Chat(cafe(ask_quantity=True))
    out = c.say("/start", "m:0", "i:cake")
    assert "تعداد را انتخاب کنید" in txt(out)
    out = c.say("n:3", "checkout", "سارا")
    assert "جمع کل: 240,000" in txt(out) and c.store.find("o")[0]["items"][0]["qty"] == 3
    plain = Chat(cafe())                                             # default: unchanged, one per tap
    assert "به سفارش اضافه شد" in txt(plain.say("/start", "m:0", "i:cake"))


def test_the_cart_can_be_viewed_and_a_line_removed():
    c = Chat(cafe())
    out = c.say("/start", "m:0", "i:cake", "more", "i:latte", "معمولی")
    assert "🛒 سبد خرید" in btns(out)
    out = c.say("cart")
    assert "1. کیک — 80,000 تومان" in txt(out) and "2. لاته معمولی — 100,000 تومان" in txt(out) and "جمع کالاها: 180,000" in txt(out)
    out = c.say("rm:0")
    assert out[0].get("edit") and "کیک" not in txt(out) and "جمع کالاها: 100,000" in txt(out)
    out = c.say("checkout", "سارا")
    assert [i["name"] for i in c.store.find("o")[0]["items"]] == ["لاته"]


def test_a_product_description_is_shown_when_picked():
    spec = BotSpec.model_validate({"name": "لباس", "welcome": "سلام", "menu": [{"label": "خرید", "block": "o"}],
                                   "blocks": [{"type": "catalog_order", "id": "o", "title": "محصولات", "source": "table", "fields": [{"key": "name", "label": "نام؟"}]}]})
    store = MemoryStore()
    store.load_catalog("o", [{"name": "مانتو کتان", "category": "مانتو", "price": 1250000, "stock": None, "description": "کتان خنک، مناسب تابستان",
                              "options": [{"name": "سایز", "choices": ["M", "XL"], "prices": [0, 50000]}]}])
    out = Chat(spec, store).say("/start", "m:0", "p:1")
    assert "«مانتو کتان» — 1,250,000 تومان\nکتان خنک، مناسب تابستان" in txt(out) and "XL (+50,000 تومان)" in btns(out)


def test_order_hours_close_the_shop_outside_them():
    hours = [{"weekday": 0, "start": "12:00", "end": "15:00"}, {"weekday": 0, "start": "19:00", "end": "23:00"}]  # Saturday lunch and dinner
    spec = cafe(order_hours=hours)
    assert "منو" in txt(Chat(spec).say("/start", "m:0")) and "آیتم مورد نظر" in txt(Chat(spec).say("/start", "m:0"))  # 12:00 Saturday: open
    late = datetime(2026, 10, 3, 16, 0, tzinfo=TEHRAN)
    out = Chat(spec, now=late).say("/start", "m:0")
    assert "در حال حاضر سفارش نمی‌پذیریم" in txt(out) and "شنبه ۱۲:۰۰ تا ۱۵:۰۰؛ شنبه ۱۹:۰۰ تا ۲۳:۰۰" in txt(out)
