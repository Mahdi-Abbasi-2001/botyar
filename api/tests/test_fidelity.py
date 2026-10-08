"""Checks that a designed spec still holds what the owner said."""
from app import fidelity


def spec(**blocks):
    out = [{"type": k, **v} for k, v in blocks.items()]
    out += [{"type": "admin_notify", "id": "n_" + b["id"], "on": b["id"], "text": "جدید"} for b in out if b["type"] in ("form", "booking", "catalog_order", "contact")]  # as in a real bot
    return {"welcome": "سلام", "menu": [], "blocks": out}


def test_owner_text_keeps_only_what_the_owner_wrote():
    h = "OWNER: ساعت ۱۶:۳۰\nBOTYAR: ❓ سؤال: ساعت ۱۰:۰۰؟\nOWNER: بله"
    t = fidelity.owner_text(h, "آخرین پیام")
    assert "16:30" in t.replace("۱۶:۳۰", "16:30") or "۱۶:۳۰" in t
    assert "۱۰:۰۰" not in t and "آخرین پیام" in t


def test_a_given_time_phone_card_handle_and_link_must_be_in_the_bot():
    owner = "کلاس ساعت ۱۶:۳۰، شماره ۰۲۱۱۲۳۴۵۶۷۸، کارت ۶۰۳۷-۹۹۷۵-۱۲۳۴-۵۶۷۸، کانال @english_daily و instagram.com/cafe"
    bare = spec(message={"id": "m", "text": "سلام"})
    got = " | ".join(fidelity.problems(bare, owner))
    for needle in ("16:30", "02112345678", "card number", "@english_daily", "instagram.com/cafe"):
        assert needle in got, needle
    full = spec(message={"id": "m", "text": "تماس: ۰۲۱۱۲۳۴۵۶۷۸", "links": [{"label": "ا", "url": "https://instagram.com/cafe"}],
                         "join": [{"channel": "@english_daily"}]},
                booking={"id": "b", "slots": [{"id": "s", "label": "x", "capacity": 1, "weekday": 3, "time": "16:30"}]},
                catalog_order={"id": "o", "card_number": "6037997512345678"})
    assert fidelity.problems(full, owner) == []


def test_appointment_length_must_match_the_minutes_said():
    sch = lambda n: spec(booking={"id": "b", "schedule": {"days": [{"weekday": 2, "start": "10:00", "end": "14:00"}], "duration_minutes": n, "services": []}})
    assert any("45" in p for p in fidelity.problems(sch(30), "نوبت‌های ۴۵ دقیقه‌ای"))
    assert fidelity.problems(sch(45), "نوبت‌های ۴۵ دقیقه‌ای") == []
    assert fidelity.problems(sch(30), "نوبت‌ها هر روز") == []                  # nothing said: nothing to check


def test_a_weekday_range_must_be_complete_in_the_schedule():
    days = lambda ds: spec(booking={"id": "b", "schedule": {"days": [{"weekday": d, "start": "09:00", "end": "17:00"} for d in ds], "duration_minutes": 30}})
    assert fidelity.problems(days([0, 1, 2, 3]), "شنبه تا چهارشنبه ۹ تا ۱۷")
    assert fidelity.problems(days([0, 1, 2, 3, 4]), "شنبه تا چهارشنبه ۹ تا ۱۷") == []
    assert fidelity.problems(days([0, 1, 2, 3]), "", "کار از شنبه تا چهارشنبه است")        # the assumption is checked too


def test_free_delivery_needs_a_fee_and_no_instruction_text_reaches_customers():
    shop = spec(catalog_order={"id": "o", "free_delivery_over": 500000, "delivery_fee": 0})
    assert any("delivery_fee" in p for p in fidelity.problems(shop, ""))
    assert fidelity.problems(spec(catalog_order={"id": "o", "free_delivery_over": 500000, "delivery_fee": 40000}), "") == []
    bad = spec(message={"id": "m", "text": "ساعت کاری: لطفاً ساعت‌های کاری را اینجا وارد کنید."})
    assert any("اینجا" in p for p in fidelity.problems(bad, ""))


def test_a_personality_quiz_must_have_enough_written_questions():
    q = lambda n, pick: spec(quiz={"id": "q", "personality": [{"id": "a"}], "pick": pick, "questions": [{}] * n})
    assert fidelity.problems(q(6, 10), "")
    assert fidelity.problems(q(12, 10), "") == []


def test_owner_directed_wording_in_customer_texts_is_caught():
    for text in ("ساعت کاری و نشانی کافه را می‌توانید در این بخش به‌روزرسانی کنید.", "قیمت‌ها را در پنل اصلاح کنید", "پیش از انتشار این متن را عوض کنید"):
        assert fidelity.problems(spec(message={"id": "m", "text": text}), ""), text
    assert fidelity.problems(spec(message={"id": "m", "text": "ساعت کاری: هر روز ۸ تا ۲۲"}), "") == []
