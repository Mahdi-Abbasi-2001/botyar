"""A returning customer is offered their saved name/number in one tap («با همین مشخصات ادامه می‌دهید؟»)."""
from app.dates import TEST_NOW
from app.engine import MemoryStore, handle, new_session
from app.spec import BotSpec

SPEC = BotSpec.model_validate({
    "name": "کافه", "welcome": "سلام", "menu": [{"label": "سفارش", "block": "o"}, {"label": "کلاس", "block": "b"}],
    "blocks": [{"type": "catalog_order", "id": "o", "title": "منو", "items": [{"id": "cake", "name": "کیک", "price": 80000}],
                "fields": [{"key": "name", "label": "نام شما؟"}, {"key": "phone", "label": "موبایل؟", "kind": "phone"}, {"key": "note", "label": "توضیح سفارش؟", "required": False}]},
               {"type": "booking", "id": "b", "title": "کلاس", "slots": [{"id": "s1", "label": "شنبه ۵ عصر", "capacity": 9}],
                "fields": [{"key": "name", "label": "نام شما؟"}, {"key": "phone", "label": "موبایل؟", "kind": "phone"}, {"key": "age", "label": "سن؟", "kind": "number"}]}]})


def chat(store, cust="c1", test=False):
    s = new_session()
    s["cust"] = cust
    if test:
        s["test"] = True

    def say(*texts):
        out = []
        for t in texts:
            out = handle(SPEC, s, t, store, TEST_NOW)
        return out
    return say


def txt(out):
    return "\n".join(a.get("text", "") for a in out)


def test_details_from_an_order_are_offered_in_a_booking_and_only_the_rest_is_asked():
    store = MemoryStore()
    chat(store)("/start", "m:0", "i:cake", "checkout", "سارا", "09121234567", "skip")
    say = chat(store)
    out = say("/start", "m:1", "s:s1")
    assert "با همین مشخصات ادامه می‌دهید؟" in txt(out) and "نام شما: سارا" in txt(out) and "موبایل: 09121234567" in txt(out)
    assert "سن؟" in txt(say("ru:yes"))               # the booking's own question is still asked
    say("۳۰")
    row = store.find("b")[0]
    assert (row["name"], row["phone"], row["age"]) == ("سارا", "09121234567", 30) and "_prefilled" not in row


def test_new_details_can_be_given_instead():
    store = MemoryStore()
    chat(store)("/start", "m:0", "i:cake", "checkout", "سارا", "09121234567", "skip")
    say = chat(store)
    say("/start", "m:0", "i:cake", "checkout")
    assert "نام شما؟" in txt(say("ru:no"))
    say("مریم", "09129999999", "skip")
    assert store.find("o")[1]["name"] == "مریم"
    assert "مریم" in txt(chat(store)("/start", "m:0", "i:cake", "checkout"))   # the latest details are offered next time


def test_order_specific_answers_are_not_reused_and_other_customers_see_nothing():
    store = MemoryStore()
    chat(store)("/start", "m:0", "i:cake", "checkout", "سارا", "09121234567", "پشت در بگذارید")
    out = chat(store)("/start", "m:0", "i:cake", "checkout")
    assert "پشت در" not in txt(out)                    # «توضیح سفارش» is about that order, not the person
    assert "نام شما؟" in txt(chat(store, "someone_else")("/start", "m:0", "i:cake", "checkout"))


def test_automated_tests_never_get_the_shortcut():
    store = MemoryStore()
    chat(store, test=True)("/start", "m:0", "i:cake", "checkout", "سارا", "09121234567", "skip")
    assert "نام شما؟" in txt(chat(store, test=True)("/start", "m:0", "i:cake", "checkout"))
