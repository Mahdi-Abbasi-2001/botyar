"""Sub-menus and quizzes."""
import pytest
from pydantic import ValidationError

from app.engine import MemoryStore, handle, new_session
from app.spec import BotSpec


def labels(out):
    return [b["data"] for a in out for b in a.get("buttons", [])]


def text(out):
    return "\n".join(a["text"] for a in out)


MENU = {"name": "فروشگاه", "welcome": "سلام", "menu": [{"label": "محصولات", "block": "prod"}, {"label": "تماس", "block": "contact_msg"}],
        "blocks": [{"type": "menu", "id": "prod", "title": "کدام دسته؟", "items": [{"label": "لپ‌تاپ", "block": "lap"}, {"label": "موبایل", "block": "mob"}, {"label": "ثبت‌نام خبرنامه", "block": "news"}]},
                   {"type": "message", "id": "lap", "text": "لپ‌تاپ‌ها از ۲۰ میلیون شروع می‌شوند."},
                   {"type": "message", "id": "mob", "text": "موبایل‌ها از ۸ میلیون."},
                   {"type": "form", "id": "news", "title": "خبرنامه", "fields": [{"key": "name", "label": "نام شما؟", "kind": "text"}]},
                   {"type": "message", "id": "contact_msg", "text": "تلفن ۰۲۱"}]}


def test_submenu_shows_buttons_and_messages_keep_the_customer_inside_it():
    sp, s, st = BotSpec.model_validate(MENU), new_session(), MemoryStore()
    handle(sp, s, "/start", st)
    out = handle(sp, s, "m:0", st)
    assert labels(out) == ["s:0", "s:1", "s:2", "/menu"] and "کدام دسته" in text(out)
    out = handle(sp, s, "s:0", st)
    assert "۲۰ میلیون" in text(out) and labels(out) == ["s:0", "s:1", "s:2", "/menu"] and s["block"] == "prod"   # siblings stay available
    out = handle(sp, s, "موبایل", st)                                                                          # typed label works
    assert "۸ میلیون" in text(out)


def test_submenu_can_open_a_form_and_back_returns_to_the_main_menu():
    sp, s, st = BotSpec.model_validate(MENU), new_session(), MemoryStore()
    for t in ["/start", "m:0", "s:2"]:
        out = handle(sp, s, t, st)
    assert "نام شما" in text(out)
    out = handle(sp, s, "سارا", st)
    assert st.find("news")[0]["name"] == "سارا" and labels(out)[0] == "m:0"
    handle(sp, s, "m:0", st)
    out = handle(sp, s, "/menu", st)
    assert s["block"] is None and labels(out)[:2] == ["m:0", "m:1"]


def test_garbage_in_a_submenu_reprompts():
    sp, s, st = BotSpec.model_validate(MENU), new_session(), MemoryStore()
    for t in ["/start", "m:0"]:
        handle(sp, s, t, st)
    for junk in ["s:99", "x", "s:-1", "m:1"]:
        out = handle(sp, s, junk, st)
        assert "لطفاً" in text(out) and s["block"] == "prod"


def test_nested_submenus_work_and_loops_or_bad_targets_are_rejected():
    d = {"name": "x", "welcome": "س", "menu": [{"label": "الف", "block": "a"}],
         "blocks": [{"type": "menu", "id": "a", "title": "الف", "items": [{"label": "ب", "block": "b"}]},
                    {"type": "menu", "id": "b", "title": "ب", "items": [{"label": "متن", "block": "m"}]},
                    {"type": "message", "id": "m", "text": "ته خط"}]}
    sp, s, st = BotSpec.model_validate(d), new_session(), MemoryStore()
    for t in ["/start", "m:0", "s:0"]:
        out = handle(sp, s, t, st)
    assert s["block"] == "b" and labels(out)[0] == "s:0"
    assert "ته خط" in text(handle(sp, s, "s:0", st))
    loop = {**d, "blocks": [{"type": "menu", "id": "a", "title": "الف", "items": [{"label": "ب", "block": "b"}]},
                            {"type": "menu", "id": "b", "title": "ب", "items": [{"label": "الف", "block": "a"}]}]}
    with pytest.raises(ValidationError):
        BotSpec.model_validate(loop)
    with pytest.raises(ValidationError):
        BotSpec.model_validate({**d, "blocks": [{"type": "menu", "id": "a", "title": "الف", "items": [{"label": "؟", "block": "nope"}]}]})
    with pytest.raises(ValidationError):
        BotSpec.model_validate({**d, "blocks": [{"type": "menu", "id": "a", "title": "الف", "items": []}]})


QUIZ = {"name": "مسابقه", "welcome": "سلام", "menu": [{"label": "آزمون", "block": "q"}],
        "blocks": [{"type": "quiz", "id": "q", "title": "آزمون جغرافیا",
                    "questions": [{"question": "پایتخت ایران؟", "options": ["تهران", "اصفهان", "شیراز"], "correct": 0},
                                  {"question": "بزرگ‌ترین دریاچه؟", "options": ["ارومیه", "زاینده‌رود"], "correct": 0}]},
                   {"type": "admin_notify", "id": "n", "on": "q", "text": "نتیجه"}]}


def take(sp, st, answers, cust="bale:1"):
    s = new_session()
    s["cust"], s["cust_name"] = cust, "سارا"
    handle(sp, s, "/start", st)
    out = handle(sp, s, "m:0", st)
    outs = [out]
    for a in answers:
        out = handle(sp, s, a, st)
        outs.append(out)
    return outs, s


def test_quiz_scores_gives_feedback_stores_the_result_and_notifies_the_owner():
    sp, st = BotSpec.model_validate(QUIZ), MemoryStore()
    outs, s = take(sp, st, ["qa:0", "qa:1"])
    assert "سؤال 1 از 2" in text(outs[0]) and labels(outs[0]) == ["qa:0", "qa:1", "qa:2", "/menu"]
    assert text(outs[1]).startswith("✅ درست!") and "سؤال 2 از 2" in text(outs[1])
    last = outs[2]
    assert "❌ نادرست. پاسخ درست: ارومیه" in text(last) and "نتیجه‌ی شما: 1 از 2 (50٪)" in text(last)
    assert any(a["type"] == "notify_admin" and "سارا: 1 از 2" in a["text"] for a in last)
    row = st.find("q")[0]
    assert (row["score"], row["total"], row["percent"], row["who"]) == (1, 2, 50, "سارا") and s["block"] is None


def test_quiz_typed_option_text_works_junk_is_ignored_and_retaking_is_allowed():
    sp, st = BotSpec.model_validate(QUIZ), MemoryStore()
    outs, s = take(sp, st, ["نمی‌دانم", "تهران", "ارومیه"])
    assert "لطفاً" in text(outs[1]) and "نتیجه‌ی شما: 2 از 2 (100٪)" in text(outs[3])
    take(sp, st, ["qa:2", "qa:1"], cust="bale:2")
    assert [r["score"] for r in st.find("q")] == [2, 0]


def test_quiz_can_hide_answers_and_validates_its_spec():
    d = {**QUIZ, "blocks": [{**QUIZ["blocks"][0], "show_answers": False}, QUIZ["blocks"][1]]}
    outs, _ = take(BotSpec.model_validate(d), MemoryStore(), ["qa:1", "qa:1"])
    assert "درست" not in text(outs[1]) and "نادرست" not in text(outs[2])
    bad = {**QUIZ["blocks"][0], "questions": [{"question": "سؤال؟؟", "options": ["الف", "ب"], "correct": 2}]}
    with pytest.raises(ValidationError):
        BotSpec.model_validate({**QUIZ, "blocks": [bad]})
    with pytest.raises(ValidationError):
        BotSpec.model_validate({**QUIZ, "blocks": [{**QUIZ["blocks"][0], "result_text": "{zzz}"}]})
    with pytest.raises(ValidationError):
        BotSpec.model_validate({**QUIZ, "blocks": [{**QUIZ["blocks"][0], "questions": [{"question": "سؤال؟؟", "options": ["الف"], "correct": 0}]}]})


def test_quiz_in_a_submenu_and_mid_quiz_republish_does_not_crash():
    d = {"name": "x", "welcome": "س", "menu": [{"label": "بازی", "block": "m"}],
         "blocks": [{"type": "menu", "id": "m", "title": "چه بازی؟", "items": [{"label": "آزمون", "block": "q"}]}, QUIZ["blocks"][0]]}
    sp, st, s = BotSpec.model_validate(d), MemoryStore(), new_session()
    for t in ["/start", "m:0", "s:0", "qa:0"]:
        handle(sp, s, t, st)
    shorter = BotSpec.model_validate({**d, "blocks": [d["blocks"][0], {**QUIZ["blocks"][0], "questions": QUIZ["blocks"][0]["questions"][:1]}]})
    out = handle(shorter, s, "qa:0", st)           # the customer is on question 2 of a quiz that now has 1 question
    assert "به‌روزرسانی" in text(out) and s["block"] is None
