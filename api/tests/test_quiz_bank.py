"""The quiz question bank: import (table / text / generated), commit, edit, and the engine using the bank instead of the spec's questions."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import io  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import llm, quiz_bank  # noqa: E402
from app.dates import TEST_NOW  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.engine import MemoryStore, handle, new_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Bot, BotVersion, User  # noqa: E402
from app.spec import BotSpec  # noqa: E402

SPEC = {"name": "q", "welcome": "سلام", "menu": [{"label": "آزمون", "block": "q"}],
        "blocks": [{"type": "quiz", "id": "q", "title": "آزمون", "pick": 3, "show_answers": False,
                    "questions": [{"question": "پایتخت ایران کجاست؟", "options": ["تهران", "شیراز"], "correct": 0}]}]}


@pytest.fixture()
def world():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        tok = c.post("/api/auth/register", json={"username": "quiz_owner", "password": "123456"}).json()["token"]
        H = {"Authorization": f"Bearer {tok}"}
        with SessionLocal() as db:
            uid = db.query(User).filter(User.username == "quiz_owner").one().id
            bot = Bot(user_id=uid, name="q")
            db.add(bot)
            db.flush()
            db.add(BotVersion(bot_id=bot.id, version=1, spec=SPEC, note=""))
            db.commit()
            bid = bot.id
        yield c, H, bid


CSV = "سؤال,گزینه ۱,گزینه ۲,گزینه ۳,گزینه ۴,پاسخ\nبزرگ‌ترین سیاره؟,زمین,مشتری,مریخ,زهره,2\nپایتخت فرانسه؟,پاریس,رم,برلین,مادرید,الف\nناقص,فقط یکی,,,,1\n"


def upload(c, H, bid, text=None, files=None):
    return c.post(f"/api/bots/{bid}/quiz/preview", headers=H, data={"text": text or ""}, files=files or None)


def test_a_table_with_recognised_columns_needs_no_model_and_skips_bad_rows(world):
    c, H, bid = world
    r = upload(c, H, bid, CSV).json()
    assert r["kind"] == "table" and r["total"] == 2
    assert r["questions"][0] == {"question": "بزرگ‌ترین سیاره؟", "options": ["زمین", "مشتری", "مریخ", "زهره"], "correct": 1}
    assert r["questions"][1]["correct"] == 0                      # «الف» = the first option
    assert any("سطر 4" in w for w in r["warnings"])               # the incomplete row is reported, not saved


def test_commit_moves_the_specs_questions_into_the_bank_and_the_bot_uses_it(world):
    c, H, bid = world
    assert c.get(f"/api/bots/{bid}/quiz", headers=H).json()["source"] == "inline"
    qs = upload(c, H, bid, CSV).json()["questions"]
    assert c.post(f"/api/bots/{bid}/quiz/commit", headers=H, json={"mode": "append", "questions": qs}).json()["saved"] == 2
    got = c.get(f"/api/bots/{bid}/quiz", headers=H).json()
    assert got["source"] == "bank" and got["total"] == 3 and got["questions"][0]["question"] == "پایتخت ایران کجاست؟"
    # the same questions again are recognised as duplicates
    assert upload(c, H, bid, CSV).json()["total"] == 0
    # the simulator now asks bank questions (3 of 3)
    out = c.post(f"/api/bots/{bid}/simulate", headers=H, json={"session_id": "s1", "text": "m:0"}).json()["actions"]
    assert "سؤال 1 از 3" in "\n".join(a.get("text", "") for a in out)


def test_edit_delete_and_back_to_the_spec(world):
    c, H, bid = world
    qs = upload(c, H, bid, CSV).json()["questions"]
    c.post(f"/api/bots/{bid}/quiz/commit", headers=H, json={"mode": "append", "questions": qs})
    rows = c.get(f"/api/bots/{bid}/quiz", headers=H).json()["questions"]
    new = {"question": "پایتخت ایتالیا؟", "options": ["رم", "میلان"], "correct": 0}
    assert c.patch(f"/api/bots/{bid}/quiz/questions/{rows[1]['id']}", headers=H, json=new).json()["question"] == "پایتخت ایتالیا؟"
    assert c.patch(f"/api/bots/{bid}/quiz/questions/{rows[1]['id']}", headers=H, json={**new, "correct": 5}).status_code == 422
    assert c.delete(f"/api/bots/{bid}/quiz/questions/{rows[2]['id']}", headers=H).json()["ok"]
    assert c.get(f"/api/bots/{bid}/quiz", headers=H).json()["total"] == 2
    assert c.delete(f"/api/bots/{bid}/quiz", headers=H).json()["ok"]
    assert c.get(f"/api/bots/{bid}/quiz", headers=H).json()["source"] == "inline"


def test_another_owner_cannot_touch_the_bank(world):
    c, H, bid = world
    tok2 = c.post("/api/auth/register", json={"username": "someone_else", "password": "123456"}).json()["token"]
    H2 = {"Authorization": f"Bearer {tok2}"}
    assert c.get(f"/api/bots/{bid}/quiz", headers=H2).status_code == 404
    assert c.post(f"/api/bots/{bid}/quiz/commit", headers=H2, json={"mode": "append", "questions": [{"question": "سؤال؟؟", "options": ["a", "b"], "correct": 0}]}).status_code == 404


def test_free_text_and_generated_questions_go_through_the_model_and_are_cleaned(world, monkeypatch):
    c, H, bid = world

    def fake(db, **kw):
        good = quiz_bank.QOut(question="کدام سیاره حلقه دارد؟", options=["زحل", "عطارد"], correct=0)
        bad = quiz_bank.QOut(question="گزینه‌ی بیرون از محدوده", options=["الف", "ب"], correct=7)
        dup = quiz_bank.QOut(question="پایتخت ایران کجاست؟", options=["تهران", "شیراز"], correct=0)
        return quiz_bank.Extracted(questions=[good, bad, dup], warnings=["یک سؤال مبهم بود"])

    monkeypatch.setattr(llm, "call", fake)
    r = upload(c, H, bid, "سؤال‌هایی که نوشته‌ام بدون جدول").json()
    assert r["kind"] == "text" and r["total"] == 1 and r["questions"][0]["question"].startswith("کدام سیاره")
    assert any("نامعتبر" in w for w in r["warnings"]) and any("تکراری" in w for w in r["warnings"]) and "یک سؤال مبهم بود" in r["warnings"]
    g = c.post(f"/api/bots/{bid}/quiz/generate", headers=H, json={"topic": "منظومه‌ی شمسی", "count": 5}).json()
    assert g["kind"] == "generated" and g["total"] == 1


def test_the_engine_uses_a_bank_and_pick_can_exceed_the_specs_own_questions():
    spec = BotSpec.model_validate(SPEC)
    st = MemoryStore()
    st.bank["q"] = [{"question": f"سؤال شماره {i}", "options": ["الف", "ب"], "correct": 0} for i in range(10)]
    s = new_session()
    s["cust"] = "bale:1"
    out = handle(spec, s, "m:0", st, TEST_NOW)
    assert "سؤال 1 از 3" in "\n".join(a.get("text", "") for a in out) and "سؤال شماره" in "\n".join(a.get("text", "") for a in out)
    for _ in range(3):
        out = handle(spec, s, "qa:0", st, TEST_NOW)
    assert "3 از 3" in "\n".join(a.get("text", "") for a in out)
