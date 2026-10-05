"""{field_key} placeholders in confirmation texts."""
import pytest
from pydantic import ValidationError

from app.engine import MemoryStore, handle, new_session
from app.spec import BotSpec


def spec(done="خوش آمدی {name}!", key="name"):
    return BotSpec.model_validate({"name": "x", "welcome": "سلام", "menu": [{"label": "شروع", "block": "f"}],
                                   "blocks": [{"type": "form", "id": "f", "title": "t", "done_text": done,
                                               "fields": [{"key": key, "label": "اسمت چیست؟", "kind": "text"}]}]})


def run(sp, *texts):
    s, st = new_session(), MemoryStore()
    out = None
    for t in ["/start", "m:0", *texts]:
        out = handle(sp, s, t, st)
    return out


def test_name_is_echoed_back():
    assert run(spec(), "سارا")[0]["text"] == "خوش آمدی سارا!"


def test_unknown_placeholder_is_rejected_at_build_time():
    with pytest.raises(ValidationError):
        spec(done="سلام {nam}")


def test_braces_in_the_customers_answer_are_not_interpreted():
    assert run(spec(), "{name}")[0]["text"] == "خوش آمدی {name}!"


def test_booking_and_order_confirmations_can_use_fields_too():
    sp = BotSpec.model_validate({"name": "x", "welcome": "س", "menu": [{"label": "ثبت", "block": "b"}],
        "blocks": [{"type": "booking", "id": "b", "title": "t", "confirm_text": "{name} عزیز، {slot_label} ثبت شد.",
                    "slots": [{"id": "a", "label": "الف", "capacity": 2}]}]})
    s, st = new_session(), MemoryStore()
    handle(sp, s, "/start", st)
    out = handle(sp, s, "m:0", st)
    pick = [b["data"] for a in out for b in a.get("buttons", [])][0]
    for t in [pick, "علی", "09121234567"]:
        out = handle(sp, s, t, st)
    assert out[0]["text"] == "علی عزیز، الف ثبت شد."
    with pytest.raises(ValidationError):
        BotSpec.model_validate({"name": "x", "welcome": "س", "menu": [{"label": "ثبت", "block": "b"}],
            "blocks": [{"type": "booking", "id": "b", "title": "t", "confirm_text": "{zzz}", "slots": [{"id": "a", "label": "الف", "capacity": 2}]}]})


def test_id_placeholder_is_the_tracking_number():
    sp = spec(done="مشکل ثبت شد. شماره پیگیری: {id}")
    s, st = new_session(), MemoryStore()
    for t in ["/start", "m:0", "الف"]:
        handle(sp, s, t, st)
    s2 = new_session()
    out = None
    for t in ["/start", "m:0", "ب"]:
        out = handle(sp, s2, t, st)
    assert out[0]["text"] == "مشکل ثبت شد. شماره پیگیری: 2"
