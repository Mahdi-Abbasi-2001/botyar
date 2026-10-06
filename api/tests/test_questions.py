"""Question kinds shared by forms, bookings and orders, plus the form's own rules (review, one per customer,
capacity, deadline)."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from datetime import datetime  # noqa: E402

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app import dates  # noqa: E402
from app.engine import MemoryStore, handle, new_session  # noqa: E402
from app.spec import BotSpec  # noqa: E402

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=dates.TEHRAN)  # 1405/07/11


def national(nine: str) -> str:
    s = sum(int(nine[i]) * (10 - i) for i in range(9)) % 11
    return nine + str(s if s < 2 else 11 - s)


def bot(fields, **form):
    return BotSpec.model_validate({"name": "ثبت‌نام", "welcome": "سلام", "menu": [{"label": "ثبت‌نام", "block": "f"}],
                                   "blocks": [{"type": "form", "id": "f", "title": "فرم ثبت‌نام", "fields": fields, "done_text": "ثبت شد", **form}]})


class Chat:
    def __init__(self, spec, store=None, cust="c1"):
        self.spec, self.store, self.s = spec, store or MemoryStore(), new_session()
        self.s["cust"] = cust

    def say(self, *texts):
        out = []
        for t in texts:
            out = handle(self.spec, self.s, t, self.store, now=NOW)
        return out


def txt(out):
    return "\n".join(a.get("text", "") for a in out)


def buttons(out):
    return [b["text"] for a in out for b in a.get("buttons", [])]


def test_optional_questions_can_be_skipped_with_a_button():
    spec = bot([{"key": "name", "label": "نام؟"}, {"key": "note", "label": "توضیح؟", "required": False}])
    c = Chat(spec)
    out = c.say("/start", "m:0", "سارا")
    assert "رد کردن" in buttons(out)
    c.say("skip")
    assert c.store.find("f")[0]["note"] == "" and c.store.find("f")[0]["name"] == "سارا"


def test_email_national_id_date_and_number_range():
    spec = bot([{"key": "email", "label": "ایمیل؟", "kind": "email"}, {"key": "nid", "label": "کد ملی؟", "kind": "national_id"},
                {"key": "born", "label": "تاریخ تولد؟", "kind": "date"}, {"key": "age", "label": "سن؟", "kind": "number", "min_value": 18, "max_value": 60}])
    c = Chat(spec)
    c.say("/start", "m:0")
    assert "ایمیل معتبر نیست" in txt(c.say("sara at mail"))
    c.say(" Sara@Mail.com ")
    assert "کد ملی معتبر نیست" in txt(c.say("1111111111"))
    assert "کد ملی معتبر نیست" in txt(c.say("0012345678" if national("001234567") != "0012345678" else "0012345679"))
    out = c.say(national("001234567"))
    assert "۱۴۰۳/۰۸/۱۵" in txt(out)  # the date question shows an example
    assert "تاریخ معتبر نیست" in txt(c.say("دیروز"))
    c.say("۱۵ آبان ۱۳۸۰")
    assert "بین ۱۸ و ۶۰" in txt(c.say("۱۲"))
    c.say("۳۰")
    row = c.store.find("f")[0]
    assert row["email"] == "sara@mail.com" and row["nid"] == national("001234567") and row["born"] == "1380/08/15" and row["age"] == 30


def test_multi_choice_toggles_and_finishes():
    spec = bot([{"key": "days", "label": "کدام روزها آزادید؟", "kind": "multi", "choices": ["شنبه", "دوشنبه", "چهارشنبه"]}])
    c = Chat(spec)
    out = c.say("/start", "m:0")
    assert "تمام" in buttons(out)
    assert "دست‌کم یک گزینه" in txt(c.say("mt:done"))
    out = c.say("mt:2")
    assert out[0].get("edit") and "✅ چهارشنبه" in buttons(out)
    c.say("mt:0", "mt:2", "mt:1", "mt:done")  # chooses شنبه, removes چهارشنبه, chooses دوشنبه
    assert c.store.find("f")[0]["days"] == "شنبه، دوشنبه"


def test_conditional_questions_follow_the_earlier_answer():
    spec = bot([{"key": "car", "label": "خودرو دارید؟", "kind": "choice", "choices": ["بله", "خیر"]},
                {"key": "plate", "label": "شماره‌ی پلاک؟", "show_if": {"field": "car", "equals": ["بله"]}},
                {"key": "name", "label": "نام؟"}])
    c = Chat(spec)
    out = c.say("/start", "m:0", "خیر")
    assert "نام؟" in txt(out) and "پلاک" not in txt(out)
    c.say("علی")
    assert "plate" not in c.store.find("f")[0]
    c2 = Chat(spec, c.store, "c2")
    assert "پلاک" in txt(c2.say("/start", "m:0", "بله"))


def test_review_before_submit_and_start_again():
    spec = bot([{"key": "name", "label": "نام؟"}, {"key": "phone", "label": "موبایل؟", "kind": "phone"}], confirm_before_submit=True)
    c = Chat(spec)
    out = c.say("/start", "m:0", "سارا", "09121234567")
    assert "لطفاً اطلاعات را بررسی کنید" in txt(out) and "نام: سارا" in txt(out) and not c.store.find("f")
    assert "نام؟" in txt(c.say("fc:redo"))
    c.say("مریم", "09121234567", "fc:yes")
    assert [r["name"] for r in c.store.find("f")] == ["مریم"]


def test_one_per_customer_capacity_and_deadline():
    spec = bot([{"key": "name", "label": "نام؟"}], one_per_customer=True, max_submissions=2)
    store = MemoryStore()
    Chat(spec, store, "a").say("/start", "m:0", "الف")
    assert "قبلاً این فرم را ثبت کرده‌اید" in txt(Chat(spec, store, "a").say("/start", "m:0"))
    Chat(spec, store, "b").say("/start", "m:0", "ب")
    assert "به پایان رسیده" in txt(Chat(spec, store, "c").say("/start", "m:0"))
    assert "به پایان رسیده" in txt(Chat(bot([{"key": "name", "label": "نام؟"}], closes_on="1405/07/10")).say("/start", "m:0"))
    assert "نام؟" in txt(Chat(bot([{"key": "name", "label": "نام؟"}], closes_on="1405/07/11")).say("/start", "m:0"))  # the last day still counts


@pytest.mark.parametrize("fields,form", [
    ([{"key": "a", "label": "؟", "show_if": {"field": "b", "equals": ["x"]}}, {"key": "b", "label": "؟"}], {}),       # refers to a later question
    ([{"key": "a", "label": "؟", "kind": "choice", "choices": ["x", "y"]}, {"key": "b", "label": "؟", "show_if": {"field": "a", "equals": ["z"]}}], {}),
    ([{"key": "a", "label": "؟", "kind": "multi", "choices": ["x"]}], {}),
    ([{"key": "a", "label": "؟", "kind": "number", "min_value": 9, "max_value": 2}], {}),
    ([{"key": "a", "label": "؟"}], {"closes_on": "1405/13/01"}),
])
def test_invalid_question_setups_are_rejected(fields, form):
    with pytest.raises(ValidationError):
        bot(fields, **form)
