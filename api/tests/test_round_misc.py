"""Contact out-of-hours reply; automatic feedback requests; message open-now, contact card and album; quiz pass code,
personality results and question photos; referral tiers and codes; anonymous chat rooms; sub-menu back; conditional notices."""
from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from app.dates import TEHRAN, TEST_NOW
from app.engine import MemoryStore, feedback_requests, handle, new_session, open_status
from app.spec import BotSpec, WorkDay

SAT = TEST_NOW  # Saturday 12:00 Tehran


class Chat:
    def __init__(self, spec, store=None, cust="bale:1", now=SAT):
        self.spec, self.store, self.now, self.s = spec, store or MemoryStore(), now, new_session()
        self.s["cust"], self.s["test"] = cust, True

    def say(self, *texts):
        out = []
        for t in texts:
            out = handle(self.spec, self.s, t, self.store, self.now)
        return out


def txt(out):
    return "\n".join(a.get("text", "") for a in out)


def btns(out):
    return [(b["text"], b["data"]) for a in out for b in a.get("buttons", [])]


def spec_of(*blocks, menu=None):
    blocks = list(blocks)
    return BotSpec.model_validate({"name": "x", "welcome": "سلام", "menu": menu or [{"label": "الف", "block": blocks[0]["id"]}], "blocks": blocks})


HOURS = [{"weekday": d, "start": "09:00", "end": "17:00"} for d in range(0, 6)]  # Saturday to Thursday


# ---------- contact ----------
def test_out_of_hours_reply_once_per_visit():
    sp = spec_of({"type": "contact", "id": "c", "title": "پیام", "hours": HOURS})
    night = datetime(2026, 10, 3, 22, 0, tzinfo=TEHRAN)
    c = Chat(sp, now=night)
    out = c.say("/start", "m:0", "سلام، سفارشم کجاست؟")
    assert "خارج از ساعت پاسخ‌گویی" in txt(out) and "ساعت پاسخ‌گویی: شنبه" in txt(out)
    assert "خارج از ساعت" not in txt(c.say("یه سؤال دیگه"))                    # not after every message
    day = Chat(sp)
    assert "خارج از ساعت" not in txt(day.say("/start", "m:0", "سلام"))


# ---------- message ----------
def test_open_status_now_and_next_opening():
    days = [WorkDay(**h) for h in HOURS]
    assert open_status(days, SAT) == "🟢 الان باز هستیم (تا ۱۷:۰۰)"
    assert open_status(days, SAT.replace(hour=7)) == "🔴 الان بسته‌ایم؛ امروز از ساعت ۰۹:۰۰ باز هستیم."
    assert open_status(days, SAT.replace(hour=20)) == "🔴 الان بسته‌ایم؛ فردا از ساعت ۰۹:۰۰ باز هستیم."
    thursday_night = (SAT + timedelta(days=5)).replace(hour=20)                 # closed all Friday → Saturday, named
    assert open_status(days, thursday_night) == "🔴 الان بسته‌ایم؛ شنبه از ساعت ۰۹:۰۰ باز هستیم."


def test_message_with_hours_contact_card_and_album():
    sp = spec_of({"type": "message", "id": "m", "text": "تماس با ما", "hours": HOURS, "contact": {"phone": "۰۹۱۲ ۱۲۳ ۴۵۶۷", "name": "کافه"},
                  "media": "album", "album_size": 3})
    out = Chat(sp).say("/start", "m:0")
    assert "تماس با ما\n\n🟢 الان باز هستیم" in out[0]["text"]
    assert [a["block"] for a in out if a["type"] == "media"] == ["m@1", "m@2", "m@3"]
    assert next(a for a in out if a["type"] == "contact") == {"type": "contact", "phone": "09121234567", "name": "کافه"}
    with pytest.raises(ValidationError, match="album_size"):
        spec_of({"type": "message", "id": "m", "text": "t", "media": "album"})


# ---------- sub-menu back ----------
def test_nested_sub_menu_goes_back_to_its_parent():
    sp = spec_of({"type": "menu", "id": "top", "title": "خدمات", "items": [{"label": "مو", "block": "hair"}, {"label": "درباره", "block": "about"}]},
                 {"type": "menu", "id": "hair", "title": "خدمات مو", "items": [{"label": "رنگ", "block": "color"}]},
                 {"type": "message", "id": "color", "text": "رنگ مو ۵۰۰ هزار"},
                 {"type": "message", "id": "about", "text": "ما"})
    c = Chat(sp)
    out = c.say("/start", "m:0")
    assert ("‹ بازگشت", "s:up") not in btns(out)                                # the top sub-menu: only «بازگشت به منو»
    out = c.say("s:0")
    assert out[0]["text"] == "خدمات مو" and ("‹ بازگشت", "s:up") in btns(out)
    out = c.say("s:0")                                                         # a message inside keeps the back button
    assert "۵۰۰" in txt(out) and ("‹ بازگشت", "s:up") in btns(out)
    out = c.say("s:up")
    assert out[0]["text"] == "خدمات" and ("‹ بازگشت", "s:up") not in btns(out)


# ---------- conditional notices ----------
def test_notices_only_for_big_orders_and_low_ratings():
    sp = spec_of({"type": "catalog_order", "id": "o", "title": "منو", "items": [{"id": "a", "name": "کیک", "price": 100000}, {"id": "b", "name": "کیک بزرگ", "price": 600000}],
                  "fields": [{"key": "name", "label": "نام؟"}]},
                 {"type": "feedback", "id": "f", "title": "نظر"},
                 {"type": "admin_notify", "id": "big", "on": "o", "text": "سفارش بزرگ", "min_total": 500000},
                 {"type": "admin_notify", "id": "low", "on": "f", "text": "نارضایتی", "max_rating": 2},
                 menu=[{"label": "سفارش", "block": "o"}, {"label": "نظر", "block": "f"}])
    c = Chat(sp)
    assert not any(a["type"] == "notify_admin" for a in c.say("/start", "m:0", "i:a", "checkout", "مریم"))
    assert any(a["type"] == "notify_admin" for a in c.say("/start", "m:0", "i:b", "checkout", "مریم"))
    assert not any(a["type"] == "notify_admin" for a in c.say("/start", "m:1", "r:4", "sk"))
    assert any(a["type"] == "notify_admin" for a in c.say("/start", "m:1", "r:2", "sk"))


# ---------- automatic feedback request ----------
def salon():
    return spec_of({"type": "booking", "id": "b", "title": "نوبت", "slots": [{"id": "s", "label": "کوتاهی مو", "capacity": 5}],
                    "fields": [{"key": "name", "label": "نام؟"}]},
                   {"type": "feedback", "id": "f", "title": "نظر", "after": "b", "after_hours": 2},
                   {"type": "catalog_order", "id": "o", "title": "منو", "items": [{"id": "a", "name": "کیک", "price": 1}], "fields": [{"key": "name", "label": "نام؟"}]},
                   {"type": "feedback", "id": "f2", "title": "نظر سفارش", "after": "o", "after_hours": 1},
                   menu=[{"label": "نوبت", "block": "b"}, {"label": "سفارش", "block": "o"}])


def test_feedback_is_requested_once_after_the_appointment_and_the_star_tap_rates():
    sp, st = salon(), MemoryStore()
    start = SAT.replace(hour=10)
    st.add("b", {"name": "مریم", "slot": "s", "slot_label": "کوتاهی مو", "date": start.date().isoformat(), "time": "10:00", "status": "confirmed", "_cust": "bale:1"})
    st.add("b", {"name": "رضا", "slot": "s", "slot_label": "کوتاهی مو", "date": start.date().isoformat(), "time": "10:00", "status": "cancelled", "_cust": "bale:2"})
    assert feedback_requests(sp, st, start + timedelta(hours=1)) == []           # too early
    out = feedback_requests(sp, st, start + timedelta(hours=2, minutes=1))
    assert len(out) == 1 and out[0]["cust"] == "bale:1" and "«کوتاهی مو»" in out[0]["text"]
    assert [b["data"] for b in out[0]["buttons"]] == ["fbr:1:1:5", "fbr:1:1:4", "fbr:1:1:3", "fbr:1:1:2", "fbr:1:1:1"]
    assert feedback_requests(sp, st, start + timedelta(hours=3)) == []           # once
    c = Chat(sp, st)
    out = c.say("fbr:1:1:2")
    assert "نظر یا پیشنهادی" in txt(out)
    c.say("کمی دیر شد")
    rec = st.find("f")[0]
    assert rec["rating"] == 2 and rec["about"] == "کوتاهی مو" and rec["comment"] == "کمی دیر شد"
    assert "قبلاً ثبت شده" in txt(c.say("fbr:1:1:5"))                           # the same request can't rate twice
    assert "قبلاً" not in txt(Chat(sp, st, cust="bale:9").say("fbr:1:1:5")) and len(st.find("f")) == 1  # nor someone else


def test_orders_are_asked_after_delivery_and_old_ones_never():
    sp, st = salon(), MemoryStore()
    st.add("o", {"name": "م", "items": [], "total": 1, "status": "done", "_done_at": SAT.isoformat(), "_cust": "bale:1"})
    st.add("o", {"name": "ق", "items": [], "total": 1, "status": "done", "_done_at": (SAT - timedelta(days=10)).isoformat(), "_cust": "bale:2"})
    st.add("o", {"name": "ن", "items": [], "total": 1, "status": "ready", "_cust": "bale:3"})
    out = feedback_requests(sp, st, SAT + timedelta(hours=1, minutes=5))
    assert [a["cust"] for a in out] == ["bale:1"] and "«سفارش 1»" in out[0]["text"]


def test_feedback_after_must_point_to_a_booking_or_order():
    with pytest.raises(ValidationError, match="after"):
        spec_of({"type": "feedback", "id": "f", "title": "نظر", "after": "f"})


# ---------- quiz ----------
QS = [{"question": "پایتخت ایران؟", "options": ["تهران", "شیراز"], "correct": 0}, {"question": "۲+۲؟", "options": ["۳", "۴"], "correct": 1}]
SHOP = {"type": "catalog_order", "id": "o", "title": "منو", "items": [{"id": "a", "name": "کیک", "price": 1}], "discount_codes": [{"code": "QUIZ20", "percent": 20}]}


def test_passing_a_quiz_gives_the_discount_code():
    sp = spec_of({"type": "quiz", "id": "q", "title": "آزمون", "questions": QS, "pass_percent": 100, "pass_code": "QUIZ20"}, SHOP)
    assert "QUIZ20" in txt(Chat(sp).say("/start", "m:0", "qa:0", "qa:1"))
    assert "QUIZ20" not in txt(Chat(sp, cust="bale:2").say("/start", "m:0", "qa:1", "qa:1"))
    with pytest.raises(ValidationError, match="discount_codes"):
        spec_of({"type": "quiz", "id": "q", "title": "آزمون", "questions": QS, "pass_percent": 50, "pass_code": "NOPE"}, SHOP)


def test_personality_quiz_picks_the_most_chosen_outcome():
    sp = spec_of({"type": "quiz", "id": "q", "title": "کدام قهوه؟",
                  "personality": [{"id": "esp", "title": "اسپرسو", "text": "قوی و سریع"}, {"id": "lat", "title": "لاته", "text": "آرام و شیری"}],
                  "questions": [{"question": "صبح‌ها؟", "options": ["عجله دارم", "آرام"], "outcomes": ["esp", "lat"]},
                                {"question": "شیرینی؟", "options": ["کم", "زیاد"], "outcomes": ["esp", "lat"]},
                                {"question": "حجم؟", "options": ["کم", "زیاد"], "outcomes": ["esp", "lat"]}]})
    c = Chat(sp)
    out = c.say("/start", "m:0", "qa:1", "qa:0", "qa:1")
    assert "نتیجه‌ی شما: لاته" in txt(out) and "آرام و شیری" in txt(out) and "درست" not in txt(out)
    assert c.store.find("q")[0]["result"] == "لاته"
    with pytest.raises(ValidationError, match="outcomes"):
        spec_of({"type": "quiz", "id": "q", "title": "x", "personality": [{"id": "a", "title": "A", "text": "a"}, {"id": "b", "title": "B", "text": "b"}],
                 "questions": [{"question": "سؤال؟", "options": ["۱", "۲"]}]})


def test_a_question_photo_comes_before_its_buttons():
    sp = spec_of({"type": "quiz", "id": "q", "title": "آزمون", "questions": [{**QS[0], "media": "image"}, QS[1]]})
    out = Chat(sp).say("/start", "m:0")
    assert out[1] == {"type": "media", "block": "q~1", "kind": "image"} and out[2]["buttons"]


# ---------- referral ----------
def test_referral_tiers_and_codes_in_the_invite_screen():
    sp = spec_of({"type": "referral", "id": "r", "title": "دعوت", "goal": 3, "reward_text": "یک قهوه", "reward_code": "QUIZ20",
                  "tiers": [{"goal": 10, "reward_text": "یک کیک"}]}, SHOP)
    c = Chat(sp)
    c.s["ref"] = {"link": "https://ble.ir/x?start=rabc", "count": 1}
    out = c.say("/start", "m:0")
    assert "1 از 3" in txt(out) and "جایزه‌های بعدی: 3 دعوت، 10 دعوت" in txt(out) and "QUIZ20" not in txt(out)
    c.s["ref"]["count"] = 4
    out = c.say("m:0")
    assert "4 از 10" in txt(out) and "یک قهوه" in txt(out) and "QUIZ20" in txt(out) and "یک کیک" not in txt(out)
    with pytest.raises(ValidationError, match="tiers"):
        spec_of({"type": "referral", "id": "r", "title": "دعوت", "goal": 5, "tiers": [{"goal": 3, "reward_text": "x"}]})


# ---------- anonymous chat rooms ----------
def test_anon_topics_need_a_room_and_carry_it_in_the_search():
    sp = spec_of({"type": "anon_chat", "id": "a", "title": "گپ", "topics": ["درس", "سرگرمی"], "max_minutes": 30})
    c = Chat(sp)
    out = c.say("/start", "m:0")
    assert [d for _, d in btns(out)] == ["ac:find:0", "ac:find:1", "/menu"]
    assert "موضوع گفت‌وگو" in txt(c.say("ac:find"))
    out = c.say("ac:find:1")
    assert {"type": "anon_find", "block": "a", "topic": "سرگرمی"} in out and "در «سرگرمی»" in txt(out)
