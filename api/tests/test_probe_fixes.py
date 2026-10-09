from app import fidelity
from app.spec import BotSpec


def _spec(blocks, menu=None):
    return {"name": "x", "welcome": "سلام", "menu": menu or [{"label": "الف", "block": blocks[0]["id"]}], "blocks": blocks, "gate": None}


def test_missing_fact_message_is_a_slip():
    sp = _spec([{"type": "message", "id": "em", "text": "شماره تماس در این پیام درج نشده است."}])
    assert any("اینجا" in p for p in fidelity.problems(sp, ""))


def test_assumption_claims_must_exist():
    sp = _spec([{"type": "message", "id": "m", "text": "سلام"}])
    out = fidelity.problems(sp, "", "یادآوری ۲۴ ساعت قبل اضافه می‌کنم\nثبت نظر پس از ویزیت را اضافه می‌کنم")
    assert len(out) == 2
    assert not fidelity.problems(sp, "", "کد تخفیف تعریف نمی‌کنم")


def test_reward_code_is_hidden():
    order = {"type": "catalog_order", "id": "o", "title": "t", "source": "inline", "items": [{"id": "a", "name": "الف", "price": 1000}],
             "discount_codes": [{"code": "WIN10", "percent": 10}]}
    quiz = {"type": "quiz", "id": "q", "title": "q", "questions": [{"question": "کدام درست است؟", "options": ["الف", "ب"], "correct": 0}], "pass_percent": 50, "pass_code": "WIN10"}
    spec = BotSpec.model_validate(_spec([quiz, order], [{"label": "آزمون", "block": "q"}, {"label": "سفارش", "block": "o"}]))
    assert spec.blocks[1].discount_codes[0].visible is False


def test_every_request_block_needs_an_owner_notification():
    form = {"type": "form", "id": "f", "title": "فرم", "fields": [{"key": "name", "label": "نام", "kind": "text"}]}
    assert any("admin_notify" in p for p in fidelity.problems(_spec([form]), ""))
    notify = {"type": "admin_notify", "id": "n", "on": "f", "text": "درخواست جدید"}
    assert not [p for p in fidelity.problems(_spec([form, notify]), "") if "admin_notify" in p]


def test_referral_discount_needs_a_real_code_and_limitation_messages_are_refused():
    order = {"type": "catalog_order", "id": "o", "title": "t", "source": "inline", "items": [{"id": "a", "name": "الف", "price": 1000}]}
    notify = {"type": "admin_notify", "id": "n", "on": "o", "text": "سفارش جدید"}
    ref = {"type": "referral", "id": "r", "text": "x", "goal": 3, "reward_text": "۱۰٪ تخفیف می‌گیرید"}
    got = " | ".join(fidelity.problems(_spec([order, notify, ref]), ""))
    assert "reward_code" in got
    msg = {"type": "message", "id": "d", "text": "ربات نرخ دلار را نمایش نمی‌دهد."}
    assert "cannot do" in " | ".join(fidelity.problems(_spec([msg]), ""))


def test_card_to_card_asked_but_not_built_is_noted_for_the_owner():
    order = {"type": "catalog_order", "id": "o", "payment": "none"}
    assert fidelity.notices({"blocks": [order]}, "پرداخت کارت‌به‌کارت هم اضافه کن")
    assert not fidelity.notices({"blocks": [{**order, "payment": "card"}]}, "پرداخت کارت‌به‌کارت هم اضافه کن")
    assert not fidelity.notices({"blocks": [order]}, "منو را عوض کن")


def test_referral_goal_must_match_the_friends_the_owner_named():
    order = {"type": "catalog_order", "id": "o", "title": "t", "source": "inline", "items": [{"id": "a", "name": "الف", "price": 1000}],
             "discount_codes": [{"code": "INVITE10", "percent": 10, "visible": False}]}
    notify = {"type": "admin_notify", "id": "n", "on": "o", "text": "سفارش جدید"}
    ref = {"type": "referral", "id": "r", "text": "x", "goal": 5, "reward_text": "تخفیف", "reward_code": "INVITE10"}
    owner = "دعوت دوستان: هر کس ۳ نفر را دعوت کند ۱۰٪ تخفیف بگیرد"
    assert any("goal is 5" in p for p in fidelity.problems(_spec([order, notify, ref]), owner))
    assert not any("goal" in p for p in fidelity.problems(_spec([order, notify, {**ref, "goal": 3}]), owner))


def test_phone_stays_in_the_text_unless_a_contact_card_was_asked_for():
    msg = {"type": "message", "id": "m", "text": "تلفن: ۰۷۱۳۲۳۴۵۶۷۸", "contact": {"phone": "07132345678", "name": "کافه"}}
    assert any("contact" in p for p in fidelity.problems(_spec([msg]), "تلفن ۰۷۱۳۲۳۴۵۶۷۸"))
    assert not any("contact" in p for p in fidelity.problems(_spec([msg]), "یک دکمه بذار که با یک لمس زنگ بزنن؛ تلفن ۰۷۱۳۲۳۴۵۶۷۸"))
    assert not any("contact" in p for p in fidelity.problems(_spec([{**msg, "contact": None}]), "تلفن ۰۷۱۳۲۳۴۵۶۷۸"))


def test_closing_at_midnight_is_accepted():
    from app.spec import WorkDay
    assert WorkDay(weekday=4, start="08:00", end="24:00").end == "23:59"
    assert WorkDay(weekday=4, start="08:00", end="00:00").end == "23:59"
    import pytest
    with pytest.raises(ValueError):
        WorkDay(weekday=4, start="18:00", end="02:00")  # past midnight into the next day is not supported


def test_a_change_request_cannot_silently_wipe_a_shops_discount_code_or_delivery():
    from app.agent import dropped_fields, restore_dropped
    old = {"blocks": [{"id": "order", "type": "catalog_order", "discount_codes": [{"code": "WELCOME10", "percent": 10}], "delivery_fee": 35000,
                       "order_hours": [{"weekday": 0, "start": "08:00", "end": "23:00"}]}]}
    new = {"blocks": [{"id": "order", "type": "catalog_order", "discount_codes": [], "delivery_fee": 0,
                       "order_hours": [{"weekday": 0, "start": "08:00", "end": "22:00"}]}]}
    req = "سفارش‌گیری فقط تا ساعت ۲۲ باشد و یک براونی هم به منو اضافه کن."
    assert len(dropped_fields(old, new, req)) == 2
    fixed = restore_dropped(old, new, req)["blocks"][0]
    assert fixed["discount_codes"][0]["code"] == "WELCOME10" and fixed["delivery_fee"] == 35000
    assert fixed["order_hours"][0]["end"] == "22:00"          # what the owner changed is kept as changed
    assert restore_dropped(old, new, "کد تخفیف را حذف کن") is None  # an explicit removal is respected
