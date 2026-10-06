"""Forms: the owner's decision sent to the customer, file/résumé questions, lead scoring.
FAQ: alternate phrasings, categories, a photo or map with an answer."""
import pytest
from pydantic import ValidationError

from app.dates import TEST_NOW
from app.engine import MemoryStore, handle, new_session, set_form_status
from app.faq_index import entry_hash
from app.faq_match import LexicalMatcher
from app.spec import BotSpec, FaqEntry


class Chat:
    def __init__(self, spec, store=None, cust="bale:1"):
        self.spec, self.store, self.s = spec, store or MemoryStore(), new_session()
        self.s["cust"], self.s["test"] = cust, True

    def say(self, *texts):
        out = []
        for t in texts:
            out = handle(self.spec, self.s, t, self.store, TEST_NOW)
        return out


def txt(out):
    return "\n".join(a.get("text", "") for a in out)


def btns(out):
    return [(b["text"], b["data"]) for a in out for b in a.get("buttons", [])]


def job_form(**block):
    return BotSpec.model_validate({"name": "استخدام", "welcome": "سلام", "menu": [{"label": "درخواست همکاری", "block": "job"}],
                                   "blocks": [{"type": "form", "id": "job", "title": "درخواست همکاری", "fields": [
                                       {"key": "name", "label": "نام شما؟"},
                                       {"key": "cv", "label": "رزومه‌ی خود را بفرستید", "kind": "file"}], **block},
                                       {"type": "admin_notify", "id": "n", "on": "job", "text": "درخواست تازه"}]})


# ---------- files ----------
def test_a_resume_is_taken_as_a_file_and_forwarded_to_the_owner():
    c = Chat(job_form())
    out = c.say("/start", "m:0", "مریم")
    assert "PDF، Word یا عکس" in txt(out)
    assert "از 📎" in txt(c.say("رزومه دارم"))                            # typing is not a file
    assert "فقط فایل PDF" in txt(c.say("file:AAA|1200|virus.exe"))
    assert "۱۰ مگابایت" in txt(c.say(f"file:AAA|{11 * 1024 * 1024}|cv.pdf"))
    out = c.say("file:BQAD123|52000|رزومه مریم.pdf")
    rec = c.store.find("job")[0]
    assert rec["cv"] == "📎 رزومه مریم.pdf" and rec["_files"]["cv"] == {"id": "BQAD123", "name": "رزومه مریم.pdf", "size": 52000}
    doc = next(a for a in out if a.get("document"))
    assert doc["type"] == "notify_admin" and doc["document"] == "BQAD123" and "رزومه" in doc["text"]


def test_a_photo_is_accepted_for_a_file_question_and_sent_as_a_photo():
    c = Chat(job_form())
    out = c.say("/start", "m:0", "مریم", "photo:PHOTO1")
    assert c.store.find("job")[0]["_files"]["cv"]["id"] == "PHOTO1"
    assert any(a.get("photo") == "PHOTO1" for a in out)


def test_files_are_refused_where_no_file_was_asked_for():
    c = Chat(job_form())
    c.say("/start", "m:0")
    assert "پیام متنی" in txt(c.say("file:X|1|a.pdf"))                    # the name question is still waiting
    assert c.store.find("job") == []


def test_file_questions_are_for_forms_only():
    with pytest.raises(ValidationError, match="only for form"):
        BotSpec.model_validate({"name": "x", "welcome": "س", "menu": [{"label": "ر", "block": "b"}],
                                "blocks": [{"type": "booking", "id": "b", "title": "ر", "slots": [{"id": "s", "label": "ص", "capacity": 1}],
                                            "fields": [{"key": "cv", "label": "فایل", "kind": "file"}]}]})


# ---------- the owner's decision ----------
def test_review_forms_start_as_received_and_the_customer_hears_the_decision():
    spec = job_form(review=True)
    c = Chat(spec)
    c.say("/start", "m:0", "مریم", "file:F|10|cv.pdf")
    rec = c.store.find("job")[0]
    assert rec["status"] == "received"
    out = set_form_status(c.store, TEST_NOW, spec.block("job"), rec, "reviewing")
    assert out[0]["cust"] == "bale:1" and "در حال بررسی" in out[0]["text"] and "شماره‌ی 1" in out[0]["text"]
    out = set_form_status(c.store, TEST_NOW, spec.block("job"), c.store.find("job")[0], "accepted", "لطفاً شنبه ساعت ۱۰ برای مصاحبه بیایید.")
    assert "پذیرفته شد" in out[0]["text"] and "مصاحبه" in out[0]["text"]
    rec = c.store.find("job")[0]
    assert rec["status"] == "accepted" and rec["owner_note"].startswith("لطفاً")
    with pytest.raises(ValueError):                                         # a decision is final
        set_form_status(c.store, TEST_NOW, spec.block("job"), rec, "rejected")


def test_no_decisions_on_a_plain_form():
    spec = job_form()
    c = Chat(spec)
    c.say("/start", "m:0", "مریم", "file:F|10|cv.pdf")
    assert "status" not in c.store.find("job")[0]
    with pytest.raises(ValueError):
        set_form_status(c.store, TEST_NOW, spec.block("job"), c.store.find("job")[0], "accepted")


# ---------- lead scoring ----------
def lead_form(hot=0):
    return BotSpec.model_validate({"name": "فروش", "welcome": "سلام", "menu": [{"label": "مشاوره", "block": "lead"}],
                                   "blocks": [{"type": "form", "id": "lead", "title": "درخواست مشاوره", "hot_score": hot, "fields": [
                                       {"key": "name", "label": "نام؟"},
                                       {"key": "budget", "label": "بودجه؟", "kind": "choice", "choices": ["کم", "متوسط", "زیاد"], "scores": [0, 5, 10]},
                                       {"key": "when", "label": "کی؟", "kind": "multi", "choices": ["این هفته", "این ماه"], "scores": [5, 2]}]},
                                       {"type": "admin_notify", "id": "n", "on": "lead", "text": "مشتری تازه"}]})


def test_lead_score_adds_up_and_hot_leads_are_flagged():
    c = Chat(lead_form(hot=12))
    out = c.say("/start", "m:0", "رضا", "زیاد", "mt:0", "mt:1", "mt:done")
    assert c.store.find("lead")[0]["score"] == 17
    assert any(a["type"] == "notify_admin" and "🔥 مشتری داغ (امتیاز 17)" in a["text"] for a in out)
    out = c.say("/start", "m:0", "سارا", "کم", "mt:1", "mt:done")
    assert c.store.find("lead")[1]["score"] == 2
    assert not any("🔥" in a.get("text", "") for a in out)


def test_scores_must_match_choices():
    with pytest.raises(ValidationError, match="scores"):
        BotSpec.model_validate({"name": "x", "welcome": "س", "menu": [{"label": "ف", "block": "f"}],
                                "blocks": [{"type": "form", "id": "f", "title": "ف", "fields": [
                                    {"key": "a", "label": "؟", "kind": "choice", "choices": ["۱", "۲"], "scores": [1]}]}]})
    with pytest.raises(ValidationError, match="hot_score"):
        BotSpec.model_validate({"name": "x", "welcome": "س", "menu": [{"label": "ف", "block": "f"}],
                                "blocks": [{"type": "form", "id": "f", "title": "ف", "hot_score": 5, "fields": [{"key": "a", "label": "؟"}]}]})


# ---------- FAQ ----------
def faq(entries):
    return BotSpec.model_validate({"name": "کافه", "welcome": "سلام", "menu": [{"label": "سؤالات", "block": "q"}],
                                   "blocks": [{"type": "faq", "id": "q", "title": "پرسش‌ها", "entries": entries}]})


def test_alternate_phrasings_match_without_ai():
    plain = FaqEntry(question="ساعت کاری کافه چیست؟", answer="۸ تا ۲۲")
    alt = FaqEntry(question="ساعت کاری کافه چیست؟", answer="۸ تا ۲۲", alternates=["کی بازید", "تا چند باز هستید"])
    other = FaqEntry(question="پارکینگ دارید؟", answer="بله")
    m = LexicalMatcher()
    assert m.rank("q", [plain, other], "تا چند باز هستید")[0][1] < 0.4
    assert m.rank("q", [alt, other], "تا چند باز هستید")[0] == (0, 1.0)
    assert entry_hash(plain) == entry_hash(FaqEntry(question=plain.question, answer=plain.answer))  # old indexes stay valid
    assert entry_hash(alt) != entry_hash(plain)                                                      # new phrasings re-index


def test_categories_group_the_question_list():
    entries = [{"question": f"سؤال ارسال {i}؟", "answer": "پاسخ", "category": "ارسال"} for i in range(5)]
    entries += [{"question": f"سؤال پرداخت {i}؟", "answer": "پاسخ", "category": "پرداخت"} for i in range(3)]
    entries += [{"question": "ساعت کاری؟", "answer": "۸ تا ۲۲"}]
    c = Chat(faq(entries))
    out = c.say("/start", "m:0", "fl")
    assert [t for t, _ in btns(out)] == ["ارسال", "پرداخت", "سایر سؤال‌ها", "بازگشت"]
    out = c.say("fk:1")
    assert [d for _, d in btns(out)] == ["fq:5", "fq:6", "fq:7", "fl"] and "پرداخت — صفحه 1 از 1" in txt(out)
    out = c.say("fk:2")
    assert [d for _, d in btns(out)] == ["fq:8", "fl"]


def test_no_category_step_without_categories():
    c = Chat(faq([{"question": f"سؤال {i}؟", "answer": "پ"} for i in range(9)]))
    out = c.say("/start", "m:0", "fl")
    assert "فهرست سؤال‌ها — صفحه 1 از 2" in txt(out) and ("بعدی ›", "fp:1") in btns(out)


def test_an_answer_can_carry_a_photo_and_a_map():
    c = Chat(faq([{"question": "آدرس کافه کجاست؟", "answer": "خیابان ولیعصر، پلاک ۱۰", "media": "image",
                   "location": {"latitude": 35.7, "longitude": 51.4}}, {"question": "پارکینگ دارید؟", "answer": "بله"}]))
    out = c.say("/start", "m:0", "fq:0")
    assert out[0]["text"] == "خیابان ولیعصر، پلاک ۱۰"
    assert out[1] == {"type": "media", "block": "q#0", "kind": "image"}
    assert out[2]["type"] == "location" and out[2]["latitude"] == 35.7
    assert ("👍 مفید بود", "fh1") in btns(out[3:])
    out = c.say("fq:1")
    assert len(out) == 1 and ("👍 مفید بود", "fh1") in btns(out)          # a plain answer is unchanged
