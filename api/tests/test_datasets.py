"""Tables filled in the build chat: validation, exact injection into the designed spec, the API and the importer."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import datasets, main  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.spec import BotSpec  # noqa: E402

MENU = [{"name": "اسپرسو", "price": "۷۰ هزار", "options": ""},
        {"name": "لاته", "price": "95000", "options": "سایز: معمولی، بزرگ (+۳۰٬۰۰۰)؛ شیر: معمولی، بادام"}]
QUIZ = [{"question": "پایتخت ایران کجاست؟", "options": ["تهران", "شیراز", "یزد"], "correct": "1"}]
SESSIONS = [{"label": "یوگا", "when": "یکشنبه", "time": "۱۸:۰۰", "capacity": "12", "price": ""},
            {"label": "جلسه‌ی ویژه", "when": "۱۴۰۵/۰۷/۲۲", "time": "10:00", "capacity": "6", "price": "۳۰۰ هزار"}]


def base(*blocks):
    return {"name": "x", "welcome": "سلام", "menu": [{"label": "m", "block": blocks[0]["id"]}], "blocks": list(blocks)}


def test_money_options_and_numbers_are_understood():
    t = datasets.parse({"menu_items": MENU})["menu_items"]
    assert [r.price for r in t] == [70000, 95000]
    assert t[1].groups() == [{"name": "سایز", "choices": ["معمولی", "بزرگ"], "prices": [0, 30000]}, {"name": "شیر", "choices": ["معمولی", "بادام"], "prices": []}]
    text = datasets.to_text(datasets.parse({"menu_items": MENU, "sessions": SESSIONS}))
    assert "اسپرسو: ۷۰,۰۰۰ تومان" in text and "جلسه‌ها (۲ مورد)" in text and "۱۴۰۵/۰۷/۲۲" in text


@pytest.mark.parametrize("kind,rows,needle", [
    ("menu_items", [{"name": "x", "price": "abc"}], "ردیف ۱"),
    ("quiz_questions", [{"question": "سؤال شماره یک", "options": ["a", "b"], "correct": "3"}], "گزینه"),
    ("sessions", [{"label": "x", "when": "پس‌فردا", "time": "10:00", "capacity": "5"}], "روز هفته"),
    ("sessions", [{"label": "x", "when": "شنبه", "time": "25:99", "capacity": "5"}], "ساعت"),
    ("faq_entries", [{"question": "ab", "answer": "x"}], "ردیف ۱"),
    ("nope", [{"a": 1}], "نامعتبر"),
])
def test_bad_rows_are_refused_with_a_message_naming_the_row(kind, rows, needle):
    with pytest.raises(ValueError) as e:
        datasets.parse({kind: rows})
    assert needle in str(e.value)


def test_rows_are_copied_into_the_designed_spec_exactly():
    data = datasets.parse({"menu_items": MENU, "quiz_questions": QUIZ, "sessions": SESSIONS,
                           "faq_entries": [{"question": "آدرس کجاست؟", "answer": "ولیعصر ۱۲"}], "services": [{"name": "کوتاهی", "duration_minutes": "45", "price": "۲۰۰ هزار"}]})
    designed = base({"type": "catalog_order", "id": "o", "title": "منو", "source": "table", "items": []},
                    {"type": "quiz", "id": "q", "title": "آزمون", "questions": [{"question": "نمونه‌ی من", "options": ["الف", "ب"]}], "pick": 50},
                    {"type": "booking", "id": "b", "title": "کلاس", "slots": [{"id": "x", "label": "نمونه", "capacity": 1}]},
                    {"type": "faq", "id": "f", "title": "سؤال", "entries": []},
                    {"type": "booking", "id": "a", "title": "نوبت", "schedule": {"days": [{"weekday": 0, "start": "09:00", "end": "17:00"}], "duration_minutes": 30}})
    spec = BotSpec.model_validate(datasets.apply(designed, data))
    shop, quiz, cls, faq, appt = spec.blocks
    assert shop.source == "inline" and [(i.name, i.price) for i in shop.items] == [("اسپرسو", 70000), ("لاته", 95000)] and shop.items[1].options[0].prices == [0, 30000]
    assert quiz.questions[0].correct == 0 and quiz.questions[0].options == ["تهران", "شیراز", "یزد"] and quiz.pick == 1
    assert [(s.weekday, s.on, s.time, s.capacity, s.price) for s in cls.slots] == [(1, None, "18:00", 12, 0), (None, "1405/07/22", "10:00", 6, 300000)]
    assert faq.entries[0].answer == "ولیعصر ۱۲"
    assert appt.schedule.services[0].duration_minutes == 45 and appt.schedule.services[0].price == 200000


def test_a_design_without_a_block_for_the_table_is_sent_back_to_the_model():
    data = datasets.parse({"quiz_questions": QUIZ})
    with pytest.raises(ValueError, match="QUIZ"):
        datasets.apply(base({"type": "message", "id": "m", "text": "سلام"}), data)


@pytest.fixture()
def client(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    seen = {}
    monkeypatch.setattr(main, "run_builder", lambda run_id, bot_id, text, tables=None: seen.update(text=text, tables=tables))
    with TestClient(app) as c:
        tok = c.post("/api/auth/register", json={"username": "ds_owner", "password": "123456"}).json()["token"]
        H = {"Authorization": f"Bearer {tok}"}
        bot = c.post("/api/bots/draft", headers=H).json()["id"]
        yield c, H, bot, seen


def test_the_builder_api_validates_tables_and_writes_them_into_the_message(client):
    c, H, bot, seen = client
    bad = c.post(f"/api/bots/{bot}/builder", headers=H, json={"text": "", "datasets": {"menu_items": [{"name": "x", "price": "abc"}]}})
    assert bad.status_code == 422 and "ردیف ۱" in bad.json()["detail"]
    ok = c.post(f"/api/bots/{bot}/builder", headers=H, json={"text": "پاسخ‌ها", "datasets": {"menu_items": MENU}})
    assert ok.status_code == 200
    assert "پاسخ‌ها" in seen["text"] and "لاته: ۹۵,۰۰۰ تومان" in seen["text"] and set(seen["tables"]) == {"menu_items"}
    assert c.post(f"/api/bots/{bot}/builder", headers=H, json={"text": ""}).status_code in (409, 422)   # nothing to say


def test_import_reads_columns_by_position_for_sessions_faq_and_services_and_quiz_tables_without_a_model(client):
    c, H, bot, _ = client
    post = lambda kind, text: c.post(f"/api/bots/{bot}/datasets/import", headers=H, data={"kind": kind, "text": text})
    r = post("sessions", "یوگا\tیکشنبه\t18:00\t12\t\nسفال\t1405/07/22\t10:00\t6\t300000").json()
    assert r["rows"][1] == {"label": "سفال", "when": "1405/07/22", "time": "10:00", "capacity": "6", "price": "300000"}
    assert post("faq_entries", "آدرس؟\tولیعصر").json()["rows"][0]["answer"] == "ولیعصر"
    assert post("services", "کوتاهی\t45\t200000").json()["rows"][0]["duration_minutes"] == "45"
    q = post("quiz_questions", "سؤال,گزینه ۱,گزینه ۲,گزینه ۳,پاسخ\nپایتخت ایران؟,تهران,شیراز,یزد,1\n").json()
    assert q["rows"] == [{"question": "پایتخت ایران؟", "options": ["تهران", "شیراز", "یزد"], "correct": 1}]
    assert c.post(f"/api/bots/{bot}/datasets/import", headers=H, data={"kind": "nope", "text": "x"}).status_code == 422
    other = c.post("/api/auth/register", json={"username": "ds_other", "password": "123456"}).json()["token"]
    assert c.post(f"/api/bots/{bot}/datasets/import", headers={"Authorization": f"Bearer {other}"}, data={"kind": "faq_entries", "text": "a\tb"}).status_code == 404
