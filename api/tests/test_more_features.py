"""FAQ next step, link buttons, contact topics, feedback aspects and call-back, quiz shuffle/pick/pass/one attempt."""
from app.dates import TEST_NOW
from app.engine import Cycle, MemoryStore, handle, new_session
from app.spec import BotSpec


def make(*blocks, menu=None):
    blocks = list(blocks)
    return BotSpec.model_validate({"name": "ربات", "welcome": "سلام", "blocks": blocks,
                                   "menu": menu or [{"label": b.get("title", b["id"]), "block": b["id"]} for b in blocks if b["type"] != "admin_notify"]})


class Chat:
    def __init__(self, spec, store=None, cust="c1"):
        self.spec, self.store, self.s = spec, store or MemoryStore(), new_session()
        self.s["cust"] = cust

    def say(self, *texts):
        out = []
        for t in texts:
            out = handle(self.spec, self.s, t, self.store, TEST_NOW, rng=Cycle())
        return out


def btns(out):
    return [(b["text"], b["data"]) for a in out for b in a.get("buttons", [])]


def txt(out):
    return "\n".join(a.get("text", "") for a in out)


def test_faq_answer_offers_the_next_step_and_it_starts_that_block():
    spec = make({"type": "faq", "id": "faq", "title": "سؤال دارید؟", "entries": [
                    {"question": "هزینه ویزیت چقدر است؟", "answer": "۲۵۰ هزار تومان.", "then": "visit"},
                    {"question": "آدرس کجاست؟", "answer": "خیابان ولیعصر.", "then": "visit", "then_label": "نوبت بگیرید"}]},
                {"type": "booking", "id": "visit", "title": "رزرو نوبت", "slots": [{"id": "s1", "label": "شنبه ۹ صبح", "capacity": 3}]})
    c = Chat(spec)
    out = c.say("/start", "m:0", "fq:0")
    assert ("رزرو نوبت", "go:visit") in btns(out)  # the label defaults to the block's title
    assert "زمان مورد نظر را انتخاب کنید" in txt(c.say("go:visit"))
    assert ("نوبت بگیرید", "go:visit") in btns(Chat(spec).say("/start", "m:0", "fq:1"))


def test_message_link_buttons():
    spec = make({"type": "message", "id": "about", "text": "ما را دنبال کنید", "title": "شبکه‌ها",
                 "links": [{"label": "اینستاگرام", "url": "https://instagram.com/cafe"}]}, menu=[{"label": "شبکه‌ها", "block": "about"}])
    assert ("اینستاگرام", "url:https://instagram.com/cafe") in btns(Chat(spec).say("/start", "m:0"))


def test_contact_asks_the_topic_first_and_keeps_it():
    spec = make({"type": "contact", "id": "c", "title": "پیام به مدیر", "topics": ["فروش", "شکایت"]},
                {"type": "admin_notify", "id": "n", "on": "c", "text": "پیام"})
    c = Chat(spec)
    out = c.say("/start", "m:0")
    assert ("شکایت", "tp:1") in btns(out)
    out = c.say("tp:1", "سفارشم دیر رسید")
    assert c.store.find("c")[0]["topic"] == "شکایت" and any("(شکایت)" in a.get("text", "") for a in out if a["type"] == "notify_admin")


def test_feedback_aspects_and_a_call_back_for_low_scores():
    spec = make({"type": "feedback", "id": "fb", "title": "نظرسنجی", "aspects": ["کیفیت غذا", "برخورد"], "follow_up_below": 3},
                {"type": "admin_notify", "id": "n", "on": "fb", "text": "نظر"})
    c = Chat(spec)
    out = c.say("/start", "m:0")
    assert "«کیفیت غذا»" in txt(out)
    assert "«برخورد»" in txt(c.say("r:2"))
    c.say("r:1", "سرد بود")
    out = c.say("09121234567")
    row = c.store.find("fb")[0]
    assert row["ratings"] == {"کیفیت غذا": 2, "برخورد": 1} and row["rating"] == 2 and row["phone"] == "09121234567"
    assert any("امتیاز پایین" in a.get("text", "") and "09121234567" in a["text"] for a in out if a["type"] == "notify_admin")
    happy = Chat(spec, cust="c2")
    happy.say("/start", "m:0", "r:5", "r:4")
    assert "ممنون" in txt(happy.say("sk")) and "phone" not in happy.store.find("fb")[0]  # no call-back for a good score


def quiz(**kw):
    qs = [{"question": f"سؤال شماره {i}", "options": ["درست", "غلط"], "correct": 0} for i in range(1, 5)]
    return make({"type": "quiz", "id": "q", "title": "آزمون", "questions": qs, **kw})


def test_quiz_pick_shuffle_pass_mark_and_one_attempt():
    spec = quiz(pick=2, shuffle=True, pass_percent=60, one_attempt=True, show_answers=False)
    c = Chat(spec)
    out = c.say("/start", "m:0")
    assert "سؤال 1 از 2" in txt(out)
    out = c.say("qa:0", "qa:1")
    assert "نتیجه‌ی شما: 1 از 2 (50٪)" in txt(out) and "نمره‌ی قبولی را کسب نکردید" in txt(out)
    again = c.say("/start", "m:0")
    assert "قبلاً در این آزمون شرکت کرده‌اید" in txt(again) and "1 از 2" in txt(again)
    win = Chat(spec, c.store, "c2")
    win.say("/start", "m:0")
    assert "قبول شدید" in txt(win.say("qa:0", "qa:0"))


def test_a_shuffled_quiz_asks_every_question_once():
    spec = quiz(shuffle=True, show_answers=False)
    c = Chat(spec)
    seen = [txt(c.say("/start", "m:0")).split("\n")[-1]]
    for _ in range(3):
        seen.append(txt(c.say("qa:0")).split("\n")[-1])
    assert sorted(seen) == [f"سؤال شماره {i}" for i in range(1, 5)]
