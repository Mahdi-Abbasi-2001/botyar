"""The names of the built-in menu entries and the customer-visible discount codes."""
from app.engine import MemoryStore, handle, my_label, new_session
from app.spec import BotSpec

SHOP = {"type": "catalog_order", "id": "o", "title": "فروشگاه", "allow_cancel": True,
        "items": [{"id": "a", "name": "تی‌شرت", "price": 100000}, {"id": "b", "name": "شلوار", "price": 300000}],
        "fields": [{"key": "name", "label": "نام شما؟", "kind": "text"}],
        "discount_codes": [{"code": "YALDA", "percent": 10, "min_total": 200000, "max_uses": 2},
                           {"code": "VIP", "amount": 50000, "visible": False}]}
APPT = {"type": "booking", "id": "ap", "title": "نوبت", "allow_cancel": True,
        "schedule": {"days": [{"weekday": 0, "start": "09:00", "end": "12:00"}], "duration_minutes": 60, "capacity": 1, "days_ahead": 7}}
CLASS = {"type": "booking", "id": "cl", "title": "کلاس", "allow_cancel": True, "slots": [{"id": "s", "label": "شنبه", "capacity": 5}]}


def spec(*blocks, menu=None):
    blocks = list(blocks)
    return BotSpec.model_validate({"name": "x", "welcome": "سلام", "menu": menu or [{"label": "ثبت سفارش", "block": blocks[0]["id"]}], "blocks": blocks})


def chat(sp, st=None, cust="bale:1"):
    s, st = new_session(), st or MemoryStore()
    s["cust"] = cust
    return s, st


def buttons(out):
    return [(b["text"], b["data"]) for a in out for b in a.get("buttons", [])]


def test_my_entry_is_named_after_what_the_bot_takes():
    assert my_label(spec(SHOP)) == "سفارش‌های من"
    assert my_label(spec(APPT)) == "نوبت‌های من"
    assert my_label(spec(CLASS)) == "ثبت‌نام‌های من"
    assert my_label(spec(SHOP, APPT)) == "سفارش‌ها و نوبت‌های من"
    assert my_label(spec(SHOP, APPT, CLASS)) == "سفارش‌ها، نوبت‌ها و ثبت‌نام‌های من"
    no_cancel = {**SHOP, "allow_cancel": False}
    sp = spec(no_cancel)
    s, st = chat(sp)
    out = handle(sp, s, "/start", st)
    assert [t for t, _ in buttons(out)] == ["ثبت سفارش", "کدهای تخفیف"]                     # no «my» entry when nothing can be cancelled


def test_menu_shows_my_entry_then_the_codes_entry_with_stable_data():
    sp = spec(SHOP)
    s, st = chat(sp)
    out = handle(sp, s, "/start", st)
    assert buttons(out) == [("ثبت سفارش", "m:0"), ("سفارش‌های من", "m:1"), ("کدهای تخفیف", "m:2")]
    out = handle(sp, s, "m:1", st)
    assert "هنوز ثبت فعالی ندارید" in out[0]["text"]
    out = handle(sp, s, "کدهای تخفیف", st)                                                  # the typed label works too
    assert "YALDA" in out[0]["text"]


def test_codes_list_shows_only_visible_codes_with_conditions_and_uses_left():
    sp = spec(SHOP)
    s, st = chat(sp)
    handle(sp, s, "/start", st)
    out = handle(sp, s, "m:2", st)
    text = out[0]["text"]
    assert "• YALDA — 10٪ تخفیف · برای سفارش بالای 200,000 تومان · 2 بار دیگر قابل استفاده است" in text
    assert "VIP" not in text and buttons(out)[0] == ("ثبت سفارش", "go:o")
    out = handle(sp, s, "go:o", st)                                                          # the button starts the order
    assert s["block"] == "o"
    # use YALDA once: one use left; use it again: it disappears from the list
    for who in ("bale:7", "bale:8"):
        s2, _ = chat(sp, st, who)
        for t in ["/start", "m:0", "i:a", "n:1", "more", "i:b", "n:1", "checkout", "YALDA", "سارا"]:
            handle(sp, s2, t, st)
        out = handle(sp, s, "/menu", st)
        text = handle(sp, s, "m:2", st)[0]["text"]
        assert ("1 بار دیگر" in text) if who == "bale:7" else ("فعلاً کد تخفیف فعالی نداریم" in text)
    assert st.find("o")[0]["discount_code"] == "YALDA"


def test_checkout_offers_visible_codes_as_buttons_and_private_codes_still_work_when_typed():
    sp = spec(SHOP)
    s, st = chat(sp)
    for t in ["/start", "m:0", "i:a", "n:1", "more", "i:b", "n:1"]:
        out = handle(sp, s, t, st)
    out = handle(sp, s, "checkout", st)
    assert [b for b in buttons(out)] == [("🎁 YALDA", "dc:0"), ("ندارم", "dc:no")]
    out = handle(sp, s, "dc:1", st)                                                          # forging the private code's button does nothing
    assert "معتبر نیست" in out[0]["text"] or s["data"].get("_code") is None
    out = handle(sp, s, "dc:0", st)
    assert "اعمال شد" in out[0]["text"] and s["data"]["_code"] == "YALDA"
    s2, _ = chat(sp, st, "bale:9")
    for t in ["/start", "m:0", "i:a", "n:1", "checkout", "vip"]:
        out = handle(sp, s2, t, st)
    assert "اعمال شد" in out[0]["text"] and s2["data"]["_code"] == "VIP"                     # a private code is typed in


def test_no_codes_entry_without_visible_codes_and_the_flag_is_part_of_the_spec():
    private = {**SHOP, "discount_codes": [{"code": "VIP", "amount": 50000, "visible": False}]}
    sp = spec(private)
    s, st = chat(sp)
    assert [t for t, _ in buttons(handle(sp, s, "/start", st))] == ["ثبت سفارش", "سفارش‌های من"]
    out = handle(sp, s, "m:2", st)
    assert "متوجه نشدم" in out[0]["text"]
    assert BotSpec.model_validate({"name": "x", "welcome": "س", "menu": [{"label": "a", "block": "o"}], "blocks": [SHOP]}).blocks[0].discount_codes[0].visible is True
