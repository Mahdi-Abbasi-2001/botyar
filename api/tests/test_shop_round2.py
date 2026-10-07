"""Shop round 2: card-to-card payment, product photos, a shared map location, back-in-stock and low-stock alerts,
repeating the last order, and delivery/pickup time windows with a limit per window."""
from datetime import timedelta

import pytest
from pydantic import ValidationError

from app.dates import TEST_NOW
from app.engine import MemoryStore, confirm_transfer, expire_unpaid, handle, new_session, restock_notices, set_order_status
from app.spec import BotSpec

CARD = "6037-9975-1234-5678"


def shop(products=None, **block):
    spec = BotSpec.model_validate({"name": "فروشگاه", "welcome": "سلام", "menu": [{"label": "خرید", "block": "o"}],
                                   "blocks": [{"type": "catalog_order", "id": "o", "title": "محصولات", "source": "table",
                                               "fields": [{"key": "name", "label": "نام شما؟"}], **block},
                                              {"type": "admin_notify", "id": "n", "on": "o", "text": "سفارش جدید"}]})
    store = MemoryStore()
    store.load_catalog("o", products if products is not None else [
        {"name": "کفش", "category": "", "price": 100000, "stock": 5, "options": [], "description": ""},
        {"name": "کیف", "category": "", "price": 200000, "stock": 0, "options": [], "description": ""}])
    return spec, store


class Chat:
    def __init__(self, spec, store, cust="bale:1", now=TEST_NOW):
        self.spec, self.store, self.now, self.s = spec, store, now, new_session()
        self.s["cust"], self.s["test"] = cust, True  # no «same details?» shortcut: replies stay literal

    def say(self, *texts):
        out = []
        for t in texts:
            out = handle(self.spec, self.s, t, self.store, self.now)
        return out


def txt(out):
    return "\n".join(a.get("text", "") for a in out)


def btns(out):
    return [(b["text"], b["data"]) for a in out for b in a.get("buttons", []) if b["data"] != "/menu"]


# ---------- card-to-card ----------
def test_card_payment_shows_the_card_takes_a_reference_and_waits_for_the_owner():
    spec, store = shop(payment="card", card_number=CARD, card_holder="مریم احمدی")
    c = Chat(spec, store)
    out = c.say("/start", "m:0", "p:1", "n:2", "checkout", "مریم")
    assert "6037 9975 1234 5678" in txt(out) and "به نام مریم احمدی" in txt(out) and "200,000" in txt(out)
    assert not any(a["type"] == "notify_admin" for a in out)               # nothing for the owner until the receipt
    rec = store.find("o")[0]
    assert rec["status"] == "awaiting_transfer" and store.product("o", 1)["stock"] == 3  # stock is held
    out = c.say("12")                                                      # too short to be a reference
    assert "دست‌کم ۴ رقم" in txt(out)
    out = c.say("۴۵۶۷۸۹")
    assert "رسید شما دریافت شد" in txt(out)
    note = next(a for a in out if a["type"] == "notify_admin")
    assert "پیگیری: 456789" in note["text"] and "«ثبت‌ها»" in note["text"]
    assert store.find("o")[0]["status"] == "transfer_sent"
    with pytest.raises(ValueError):
        set_order_status(store, TEST_NOW, spec.block("o"), store.find("o")[0], "preparing")
    msgs = confirm_transfer(store, TEST_NOW, spec.block("o"), store.find("o")[0])
    assert store.find("o")[0]["status"] == "new" and store.find("o")[0]["paid"] is True
    assert msgs[0]["cust"] == "bale:1" and "واریز شما تأیید شد" in msgs[0]["text"]
    with pytest.raises(ValueError):
        confirm_transfer(store, TEST_NOW, spec.block("o"), store.find("o")[0])


def test_a_receipt_photo_is_forwarded_to_the_owner():
    spec, store = shop(payment="card", card_number=CARD)
    c = Chat(spec, store)
    c.say("/start", "m:0", "p:1", "n:1", "checkout", "مریم")
    out = c.say("photo:AgADBAADxyz")
    note = next(a for a in out if a["type"] == "notify_admin")
    assert note["photo"] == "AgADBAADxyz" and "عکس رسید" in note["text"]


def test_the_receipt_button_works_after_leaving_and_the_customer_can_cancel():
    spec, store = shop(payment="card", card_number=CARD)
    c = Chat(spec, store)
    out = c.say("/start", "m:0", "p:1", "n:1", "checkout", "مریم")
    send_btn, cancel_btn = [d for _, d in btns(out) if d.startswith(("tr:", "tx:"))]
    c.say("/start")
    assert "شماره‌ی پیگیری" in txt(c.say(send_btn))
    c.say("/start")
    out = c.say(cancel_btn)
    assert "سفارش لغو شد" in txt(out) and store.find("o")[0]["status"] == "cancelled" and store.product("o", 1)["stock"] == 5
    other = Chat(spec, store, cust="bale:2")                                # someone else's order is not theirs to cancel
    assert "قابل لغو نیست" in txt(other.say(cancel_btn))


def test_an_order_with_no_receipt_expires_and_returns_its_stock():
    spec, store = shop(payment="card", card_number=CARD, card_wait_minutes=30)
    c = Chat(spec, store)
    c.say("/start", "m:0", "p:1", "n:2", "checkout", "مریم")
    assert expire_unpaid(spec, store, TEST_NOW + timedelta(minutes=20)) == []
    out = expire_unpaid(spec, store, TEST_NOW + timedelta(minutes=31))
    assert "به موقع نرسید" in out[0]["text"] and store.find("o")[0]["status"] == "cancelled" and store.product("o", 1)["stock"] == 5


def test_card_payment_needs_a_real_card_number():
    with pytest.raises(ValidationError, match="card_number"):
        shop(payment="card")
    with pytest.raises(ValidationError, match="card_number"):
        shop(payment="card", card_number="1234")
    spec, _ = shop(payment="card", card_number="۶۰۳۷۹۹۷۵۱۲۳۴۵۶۷۸")
    assert spec.block("o").card_number == "6037 9975 1234 5678"


# ---------- product photos ----------
def test_a_product_photo_is_sent_before_its_details():
    spec, store = shop([{"name": "کفش", "category": "", "price": 100000, "stock": 5, "options": [], "description": "", "photo": True},
                        {"name": "کیف", "category": "", "price": 200000, "stock": 5, "options": [], "description": ""}])
    c = Chat(spec, store)
    out = c.say("/start", "m:0", "p:1")
    assert out[0] == {"type": "media", "block": "product:1", "kind": "image"} and "«کفش» — 100,000 تومان" in out[1]["text"]
    out = c.say("n:1", "more", "p:2")
    assert not any(a["type"] == "media" for a in out)


# ---------- map location ----------
def test_a_location_question_takes_a_shared_location_or_a_written_address():
    spec = BotSpec.model_validate({"name": "x", "welcome": "سلام", "menu": [{"label": "سفارش", "block": "o"}],
                                   "blocks": [{"type": "catalog_order", "id": "o", "title": "منو", "items": [{"id": "a", "name": "پیتزا", "price": 1}],
                                               "fields": [{"key": "address", "label": "نشانی؟", "kind": "location"}]}]})
    store = MemoryStore()
    c = Chat(spec, store)
    out = c.say("/start", "m:0", "i:a", "checkout")
    assert "موقعیت مکانی" in txt(out)
    assert "نشانی را کامل" in txt(c.say("خ"))
    c.say("loc:35.6997,51.338")
    assert store.find("o")[0]["address"] == "https://www.google.com/maps?q=35.699700,51.338000"
    c.say("/start", "m:0", "i:a", "checkout", "تهران، خیابان آزادی، پلاک ۱۲")
    assert store.find("o")[1]["address"] == "تهران، خیابان آزادی، پلاک ۱۲"


def test_a_photo_or_location_where_none_was_asked_for_is_refused_politely():
    spec, store = shop()
    c = Chat(spec, store)
    c.say("/start")
    assert "پیام متنی" in txt(c.say("photo:abc"))
    assert "پیام متنی" in txt(c.say("loc:35.1,51.2"))


# ---------- back in stock ----------
def test_back_in_stock_alert_is_sent_once():
    spec, store = shop()
    c = Chat(spec, store)
    out = c.say("/start", "m:0", "p:2")
    assert ("🔔 موجود شد خبرم کن", "ns:2") in btns(out)
    assert "خبرتان می‌کنیم" in txt(c.say("ns:2"))
    c.say("ns:2")
    assert len(store.find("_restock")) == 1                                 # asking twice is remembered once
    assert restock_notices(spec, store, TEST_NOW) == []                     # still out of stock
    store.catalog["o"][1]["stock"] = 3
    out = restock_notices(spec, store, TEST_NOW)
    assert out[0]["cust"] == "bale:1" and "دوباره موجود شد" in out[0]["text"] and out[0]["buttons"][0]["data"] == "go:o"
    assert restock_notices(spec, store, TEST_NOW) == []


def test_no_alert_button_when_turned_off():
    spec, store = shop(restock_alerts=False)
    out = Chat(spec, store).say("/start", "m:0", "p:2")
    assert not any(d.startswith("ns:") for _, d in btns(out))


# ---------- low stock ----------
def test_low_stock_tells_the_owner_when_the_threshold_is_crossed():
    spec, store = shop(low_stock_alert=3)
    c = Chat(spec, store)
    out = c.say("/start", "m:0", "p:1", "n:1", "checkout", "مریم")          # 5 -> 4: nothing
    assert not any("موجودی" in a.get("text", "") for a in out if a["type"] == "notify_admin")
    out = c.say("/start", "m:0", "p:1", "n:2", "checkout", "مریم")          # 4 -> 2: crossed
    assert any(a["type"] == "notify_admin" and "موجودی «کفش» به 2 عدد رسید" in a["text"] for a in out)
    out = c.say("/start", "m:0", "p:1", "n:2", "checkout", "مریم")          # 2 -> 0: sold out
    assert any(a["type"] == "notify_admin" and "موجودی «کفش» تمام شد" in a["text"] for a in out)


# ---------- repeat the last order ----------
def test_repeat_last_order_uses_todays_prices_and_drops_what_is_gone():
    spec, store = shop([{"name": "لاته", "category": "", "price": 100000, "stock": None, "description": "",
                         "options": [{"name": "سایز", "choices": ["معمولی", "بزرگ"], "prices": [0, 30000]}]},
                        {"name": "کیک", "category": "", "price": 80000, "stock": 5, "options": [], "description": ""}])
    c = Chat(spec, store)
    out = c.say("/start", "m:0")
    assert not any(d == "ro" for _, d in btns(out))                         # first visit: nothing to repeat
    c.say("p:1", "بزرگ", "n:2", "more", "p:2", "n:1", "checkout", "مریم")
    store.catalog["o"][0]["price"] = 110000
    store.catalog["o"][1]["stock"] = 0
    out = c.say("/start", "m:0")
    assert ("🔁 تکرار همین سفارش", "ro") in btns(out) and "لاته بزرگ × 2" in txt(out)
    out = c.say("ro")
    assert "کیک" in txt(out[:1]) and "لاته بزرگ × 2 — 280,000 تومان" in txt(out)
    c.say("checkout", "مریم")
    assert store.find("o")[1]["total"] == 280000


def test_no_repeat_offer_when_turned_off():
    spec, store = shop(repeat_order=False)
    c = Chat(spec, store)
    c.say("/start", "m:0", "p:1", "n:1", "checkout", "مریم")
    assert not any(d == "ro" for _, d in btns(c.say("/start", "m:0")))


# ---------- delivery / pickup time ----------
WINDOWS = [{"start": "11:00", "end": "12:00"}, {"start": "12:15", "end": "13:00"}, {"start": "13:00", "end": "14:00"}, {"start": "14:00", "end": "15:00"}]


def test_time_windows_hide_past_and_full_ones_and_are_saved():
    spec, store = shop(time_windows=WINDOWS, per_window=1)                 # TEST_NOW is 12:00; lead 30 minutes
    c = Chat(spec, store)
    out = c.say("/start", "m:0", "p:1", "n:1", "checkout")
    assert [t for t, _ in btns(out)] == ["امروز ۱۳:۰۰ تا ۱۴:۰۰", "امروز ۱۴:۰۰ تا ۱۵:۰۰"]
    assert "انتخاب کنید" in txt(c.say("tw:0:0"))                             # a past window is refused
    out = c.say("tw:0:2", "مریم")
    assert "زمان تحویل: امروز ۱۳:۰۰ تا ۱۴:۰۰" in txt(out)
    assert any(a["type"] == "notify_admin" and "زمان تحویل" in a["text"] for a in out)
    rec = store.find("o")[0]
    assert rec["delivery_time"] == "امروز ۱۳:۰۰ تا ۱۴:۰۰" and rec["_tw"] == 2 and rec["_tw_day"] == TEST_NOW.date().isoformat()
    out = Chat(spec, store, cust="bale:2").say("/start", "m:0", "p:1", "n:1", "checkout")
    assert [t for t, _ in btns(out)] == ["امروز ۱۴:۰۰ تا ۱۵:۰۰"]               # 13–14 is full now


def test_a_window_taken_while_typing_is_asked_again():
    spec, store = shop(time_windows=WINDOWS, per_window=1)
    a, b = Chat(spec, store), Chat(spec, store, cust="bale:2")
    a.say("/start", "m:0", "p:1", "n:1", "checkout", "tw:0:3")
    b.say("/start", "m:0", "p:1", "n:1", "checkout", "tw:0:3", "رضا")
    out = a.say("مریم")
    assert "همین حالا پر شد" in txt(out) and [t for t, _ in btns(out)] == ["امروز ۱۳:۰۰ تا ۱۴:۰۰"]
    a.say("tw:0:2", "مریم")
    assert store.find("o")[1]["_tw"] == 2


def test_no_window_left_keeps_the_cart_and_tomorrow_can_be_offered():
    spec, store = shop(time_windows=[{"start": "09:00", "end": "10:00"}])
    out = Chat(spec, store).say("/start", "m:0", "p:1", "n:1", "checkout")
    assert "برای امروز" in txt(out) and ("ثبت سفارش", "checkout") in btns(out)
    spec, store = shop(time_windows=[{"start": "09:00", "end": "10:00"}], window_days=2)
    out = Chat(spec, store).say("/start", "m:0", "p:1", "n:1", "checkout")
    assert [t for t, _ in btns(out)] == ["فردا ۰۹:۰۰ تا ۱۰:۰۰"]


def test_windows_validation():
    with pytest.raises(ValidationError):
        shop(time_windows=[{"start": "14:00", "end": "13:00"}])
    with pytest.raises(ValidationError, match="duplicate"):
        shop(time_windows=[{"start": "13:00", "end": "14:00"}, {"start": "13:00", "end": "14:00"}])
