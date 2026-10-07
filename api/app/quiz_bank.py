"""Quiz question bank API: the owner builds a large question set the way a store owner builds a product list.
Questions are added one by one, imported from a pasted table / CSV / Excel (plain code reads recognised columns), from free text,
photos or PDF pages (a model extracts them), or generated from a topic (a model writes them; the owner reviews before saving).
While a quiz has rows in its bank, they replace the questions written in the spec."""
from __future__ import annotations

import base64
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import llm
from .auth import current_user
from .catalog import MAX_FILE, MAX_IMAGES, _decode, _own, checked_image, parse_delimited, parse_xlsx, pdf_to_images
from .config import settings
from .db import get_db
from .models import Bot, BotVersion, LlmCall, QuizQuestionRow, User

log = logging.getLogger("botyar.quiz")
router = APIRouter()
MAX_Q, DAILY_AI, STEPS = 500, 30, ["quiz_import", "quiz_vision", "quiz_generate"]


class QIn(BaseModel):
    question: str = Field(min_length=3, max_length=300)
    options: list[str] = Field(min_length=2, max_length=5)
    correct: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _ok(self):
        self.question = self.question.strip()
        self.options = [o.strip()[:60] for o in self.options if o and o.strip()]
        if len(self.options) < 2:
            raise ValueError("هر سؤال حداقل دو گزینه لازم دارد")
        if len(set(self.options)) != len(self.options):
            raise ValueError("گزینه‌های یک سؤال نباید تکراری باشند")
        if self.correct >= len(self.options):
            raise ValueError("شماره‌ی گزینه‌ی درست معتبر نیست")
        return self


# ---------- blocks and rows ----------
def quiz_blocks(bot_id: int, db: Session) -> list[dict]:
    v = db.scalars(select(BotVersion).where(BotVersion.bot_id == bot_id).order_by(BotVersion.version.desc())).first()
    if v is None:
        return []
    return [{"id": b["id"], "title": b.get("title", b["id"]), "inline": b.get("questions", [])}
            for b in v.spec["blocks"] if b["type"] == "quiz" and not b.get("personality")]


def _block(bot_id: int, block: str | None, db: Session) -> dict:
    blocks = quiz_blocks(bot_id, db)
    if not blocks:
        raise HTTPException(409, "این ربات آزمون ندارد")
    if block is None:
        return blocks[0]
    found = next((b for b in blocks if b["id"] == block), None)
    if found is None:
        raise HTTPException(404, "آزمون یافت نشد")
    return found


def _rows(bot_id: int, block_id: str, db: Session) -> list[QuizQuestionRow]:
    return list(db.scalars(select(QuizQuestionRow).where(QuizQuestionRow.bot_id == bot_id, QuizQuestionRow.block_id == block_id)
                           .order_by(QuizQuestionRow.position, QuizQuestionRow.id)))


def _out(r: QuizQuestionRow) -> dict:
    return {"id": r.id, "question": r.question, "options": r.options, "correct": r.correct}


@router.get("/api/bots/{bot_id}/quiz")
def get_quiz(bot_id: int, block: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _own(bot_id, user, db)
    blocks = quiz_blocks(bot_id, db)
    if not blocks:
        return {"blocks": [], "block": None, "total": 0, "questions": [], "source": "inline"}
    b = _block(bot_id, block, db)
    rows = _rows(bot_id, b["id"], db)
    pub = [{"id": x["id"], "title": x["title"]} for x in blocks]
    if rows:
        return {"blocks": pub, "block": b["id"], "total": len(rows), "questions": [_out(r) for r in rows[:300]], "source": "bank"}
    inline = [{"id": None, "question": q["question"], "options": q["options"], "correct": q.get("correct", 0)} for q in b["inline"]]
    return {"blocks": pub, "block": b["id"], "total": len(inline), "questions": inline, "source": "inline"}


# ---------- reading a table ----------
_LETTERS = {"a": 0, "b": 1, "c": 2, "d": 3, "e": 4, "الف": 0, "ب": 1, "ج": 2, "د": 3, "ه": 4}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩ي", "01234567890123456789ی")).strip().lower())


def _header_roles(header: list[str]):
    q, opts, ans = None, [], None
    for i, h in enumerate(header):
        t = _norm(h)
        if q is None and re.search(r"سوال|سؤال|question|پرسش|صورت", t):
            q = i
        elif ans is None and re.search(r"پاسخ|جواب|صحیح|درست|answer|correct|key", t):
            ans = i
        elif re.search(r"گزینه|option|choice|^[a-e]$|^(الف|ب|ج|د)$|^\d$", t):
            opts.append(i)
    return q, opts, ans


def _answer_index(raw: str, options: list[str]) -> int | None:
    t = _norm(raw)
    if t in _LETTERS:
        return _LETTERS[t]
    if re.fullmatch(r"[1-5]", t):
        return int(t) - 1
    for i, o in enumerate(options):
        if _norm(o) == t and t:
            return i
    return None


def questions_from_rows(rows: list[list[str]]) -> tuple[list[dict], list[str]] | None:
    """Recognised columns (question / options / answer) -> questions; None when the header is not understood (a model then reads the text)."""
    if len(rows) < 2:
        return None
    q, opts, ans = _header_roles(rows[0])
    if q is None or len(opts) < 2 or ans is None:
        return None
    out, warnings = [], []
    for n, r in enumerate(rows[1:], 2):
        get = lambda i: (r[i].strip() if i < len(r) else "")
        options = [get(i) for i in opts if get(i)]
        idx = _answer_index(get(ans), options) if options else None
        if not get(q) or len(options) < 2:
            warnings.append(f"سطر {n}: سؤال یا گزینه‌ها ناقص است و رد شد.")
        elif idx is None or idx >= len(options):
            warnings.append(f"سطر {n}: گزینه‌ی درست مشخص نیست و رد شد.")
        else:
            out.append({"question": get(q), "options": options[:5], "correct": idx})
    return out, warnings


# ---------- the model: free text, photos, topic ----------
class QOut(BaseModel):
    question: str
    options: list[str]
    correct: int  # 0-based index of the right option


class Extracted(BaseModel):
    questions: list[QOut]
    warnings: list[str]


IMPORT_PROMPT = """You extract multiple-choice quiz questions from text or pages written by a quiz owner (usually Persian).
Rules: copy each question and option exactly as written, never invent a question that is not in the source; 2 to 5 options per question; `correct` is the 0-based index of the right option.
If the source marks the right answer (a letter, a number, a star, «پاسخ: …») use it. If it does not and the answer is certain general knowledge, give it; otherwise skip that question and add a Persian warning naming it.
Skip anything that is not a question. `warnings`: short Persian sentences about what you skipped or were unsure of."""

GENERATE_PROMPT = """You write multiple-choice quiz questions in standard written Persian for a quiz owner.
Write exactly the requested number of questions about the topic. Each has 4 options with exactly ONE right answer (`correct` = its 0-based index) and three plausible wrong options; options short (under 60 characters), distinct and unambiguous.
Only well-established, verifiable facts: no opinions, no trick questions, no questions that depend on today's date. Vary the position of the right answer. Questions must be different from each other and from the EXISTING list.
If the topic is too vague or cannot support that many reliable questions, write fewer and say so in `warnings` (Persian)."""


def _ai_today(user: User, db: Session) -> int:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    return db.scalar(select(func.count()).select_from(LlmCall).join(Bot, Bot.id == LlmCall.bot_id).where(
        Bot.user_id == user.id, LlmCall.step.in_(STEPS), LlmCall.created_at >= since)) or 0


def _guard(user: User, db: Session):
    if _ai_today(user, db) >= DAILY_AI:
        raise HTTPException(429, "سقف روزانه‌ی واردسازی و تولید سؤال پر شده است")
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    if (db.scalar(select(func.count()).select_from(LlmCall).where(LlmCall.step.in_(STEPS), LlmCall.created_at >= since)) or 0) >= settings.global_daily_imports:
        raise HTTPException(503, "ظرفیت امروز تکمیل شده است؛ فردا دوباره تلاش کنید")


def _clean(items: list[QOut], warnings: list[str], existing: set[str] | None = None) -> tuple[list[dict], list[str]]:
    out, seen = [], set(existing or ())
    for i, q in enumerate(items, 1):
        try:
            ok = QIn(question=q.question, options=q.options, correct=q.correct)
        except Exception:  # noqa: BLE001 - one malformed question never spoils the rest
            warnings.append(f"سؤال {i} ناقص یا نامعتبر بود و رد شد.")
            continue
        key = _norm(ok.question)
        if key in seen:
            warnings.append(f"سؤال تکراری رد شد: «{ok.question[:40]}»")
            continue
        seen.add(key)
        out.append(ok.model_dump())
    return out[:MAX_Q], warnings


def _existing(bot_id: int, b: dict, db: Session) -> set[str]:
    rows = _rows(bot_id, b["id"], db)
    return {_norm(r.question) for r in rows} if rows else {_norm(q["question"]) for q in b["inline"]}


@router.post("/api/bots/{bot_id}/quiz/preview")
async def preview(bot_id: int, files: list[UploadFile] = File(default=[]), text: str = Form(""), block: str | None = Form(None),
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    _own(bot_id, user, db)
    b = _block(bot_id, block, db)
    if not files and not text.strip():
        raise HTTPException(400, "یک فایل انتخاب کنید یا سؤال‌ها را جای‌گذاری کنید")
    images: list[tuple[bytes, str]] = []
    rows: list[list[str]] | None = None
    raw_text = text
    for f in files:
        data = await f.read()
        if len(data) > MAX_FILE:
            raise HTTPException(413, "حجم فایل بیش از حد مجاز است")
        name = (f.filename or "").lower()
        if name.endswith(".pdf") or f.content_type == "application/pdf":
            images += [(im, "image/png") for im in pdf_to_images(data)]
        elif (f.content_type or "").startswith("image/") or name.endswith((".png", ".jpg", ".jpeg", ".webp")):
            images.append(checked_image(data))
        else:
            try:
                rows = parse_xlsx(data) if name.endswith((".xlsx", ".xlsm")) else parse_delimited(_decode(data))
            except Exception:  # noqa: BLE001
                raise HTTPException(422, "فایل خوانده نشد؛ فرمت CSV، Excel (xlsx) یا یک عکس را امتحان کنید")
            raw_text = "\n".join("\t".join(r) for r in rows)
    if rows is None and not images and raw_text.strip():
        rows = parse_delimited(raw_text)
    existing = _existing(bot_id, b, db)
    parsed = questions_from_rows(rows) if (rows and not images) else None
    if parsed is not None:  # recognised columns: plain code, no model call
        kind = "table"
        questions, warnings = _clean([QOut(**q) for q in parsed[0]], list(parsed[1]), existing)
    elif images:
        _guard(user, db)
        kind = "vision"
        parts: list[dict] = [{"type": "input_text", "text": "Extract the quiz questions from these pages."}]
        for data, mime in images[:MAX_IMAGES]:
            parts.append({"type": "input_image", "image_url": f"data:{mime};base64,{base64.b64encode(data).decode()}"})
        try:
            ex = llm.call(db, bot_id=bot_id, run_id=0, step="quiz_vision", instructions=IMPORT_PROMPT, input=[{"role": "user", "content": parts}],
                          schema=Extracted, effort="low", max_out=16000)
        except Exception:  # noqa: BLE001
            log.exception("quiz vision import failed")
            raise HTTPException(502, "خواندن تصویر ناموفق بود؛ چند لحظه بعد دوباره تلاش کنید")
        questions, warnings = _clean(ex.questions, list(ex.warnings), existing)
    else:  # free text, or a table whose columns were not recognised: a model reads it
        _guard(user, db)
        kind = "text"
        try:
            ex = llm.call(db, bot_id=bot_id, run_id=0, step="quiz_import", instructions=IMPORT_PROMPT, input=raw_text[:60000], schema=Extracted, effort="low", max_out=16000)
        except Exception:  # noqa: BLE001
            log.exception("quiz import failed")
            raise HTTPException(502, "خواندن سؤال‌ها ناموفق بود؛ چند لحظه بعد دوباره تلاش کنید")
        questions, warnings = _clean(ex.questions, list(ex.warnings), existing)
    if not questions:
        warnings.append("سؤالی پیدا نشد.")
    return {"kind": kind, "total": len(questions), "questions": questions, "warnings": warnings}


class GenerateIn(BaseModel):
    topic: str = Field(min_length=3, max_length=200)
    count: int = Field(default=10, ge=1, le=30)
    block: str | None = None


@router.post("/api/bots/{bot_id}/quiz/generate")
def generate(bot_id: int, body: GenerateIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _own(bot_id, user, db)
    b = _block(bot_id, body.block, db)
    _guard(user, db)
    have = [r.question for r in _rows(bot_id, b["id"], db)] or [q["question"] for q in b["inline"]]
    prompt = f"TOPIC: {body.topic}\nNUMBER OF QUESTIONS: {body.count}\nEXISTING QUESTIONS (do not repeat):\n" + "\n".join(have[-60:])
    try:
        ex = llm.call(db, bot_id=bot_id, run_id=0, step="quiz_generate", instructions=GENERATE_PROMPT, input=prompt, schema=Extracted, effort="low", max_out=12000)
    except Exception:  # noqa: BLE001
        log.exception("quiz generation failed")
        raise HTTPException(502, "تولید سؤال ناموفق بود؛ چند لحظه بعد دوباره تلاش کنید")
    questions, warnings = _clean(ex.questions, list(ex.warnings), _existing(bot_id, b, db))
    return {"kind": "generated", "total": len(questions), "questions": questions, "warnings": warnings}


# ---------- saving ----------
class CommitIn(BaseModel):
    block: str | None = None
    mode: Literal["replace", "append"] = "append"
    questions: list[QIn] = Field(max_length=MAX_Q)


@router.post("/api/bots/{bot_id}/quiz/commit")
def commit(bot_id: int, body: CommitIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _own(bot_id, user, db)
    b = _block(bot_id, body.block, db)
    if not body.questions:
        raise HTTPException(400, "سؤالی برای ذخیره وجود ندارد")
    existing = _rows(bot_id, b["id"], db)
    if body.mode == "replace":
        db.execute(delete(QuizQuestionRow).where(QuizQuestionRow.bot_id == bot_id, QuizQuestionRow.block_id == b["id"]))
        start = 0
    else:
        if not existing:  # the first addition moves the spec's own questions into the bank so none is lost
            for i, q in enumerate(b["inline"]):
                db.add(QuizQuestionRow(bot_id=bot_id, block_id=b["id"], question=q["question"], options=q["options"], correct=q.get("correct", 0), position=i))
            start = len(b["inline"])
        else:
            start = max(r.position for r in existing) + 1
        if start + len(body.questions) > MAX_Q:
            raise HTTPException(422, f"هر آزمون حداکثر {MAX_Q} سؤال دارد")
    for i, q in enumerate(body.questions):
        db.add(QuizQuestionRow(bot_id=bot_id, block_id=b["id"], question=q.question, options=q.options, correct=q.correct, position=start + i))
    db.commit()
    return {"ok": True, "saved": len(body.questions)}


@router.patch("/api/bots/{bot_id}/quiz/questions/{qid}")
def edit_question(bot_id: int, qid: int, body: QIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _own(bot_id, user, db)
    r = db.get(QuizQuestionRow, qid)
    if not r or r.bot_id != bot_id:
        raise HTTPException(404, "سؤال یافت نشد")
    r.question, r.options, r.correct = body.question, body.options, body.correct
    db.commit()
    return _out(r)


@router.delete("/api/bots/{bot_id}/quiz/questions/{qid}")
def delete_question(bot_id: int, qid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _own(bot_id, user, db)
    r = db.get(QuizQuestionRow, qid)
    if not r or r.bot_id != bot_id:
        raise HTTPException(404, "سؤال یافت نشد")
    db.delete(r)
    db.commit()
    return {"ok": True}


@router.delete("/api/bots/{bot_id}/quiz")
def clear_bank(bot_id: int, block: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Back to the questions written in the bot itself."""
    _own(bot_id, user, db)
    b = _block(bot_id, block, db)
    db.execute(delete(QuizQuestionRow).where(QuizQuestionRow.bot_id == bot_id, QuizQuestionRow.block_id == b["id"]))
    db.commit()
    return {"ok": True}
