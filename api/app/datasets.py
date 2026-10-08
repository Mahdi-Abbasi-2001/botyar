"""Lists the owner fills in as TABLES instead of typing them into chat: a menu with prices, quiz questions, class sessions, FAQ entries, services.
The rows are checked here, written into the conversation as exact Persian lines (so the model designs around them), and — after the model has
designed the bot — copied into the spec EXACTLY, so no price, time or answer can be lost or changed on the way."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .engine_text import fa_digits, norm
from .spec import jalali_date

KINDS = ("menu_items", "quiz_questions", "sessions", "faq_entries", "services")
MAX_ROWS = {"menu_items": 40, "quiz_questions": 20, "sessions": 20, "faq_entries": 40, "services": 20}
WEEKDAYS = {"شنبه": 0, "یکشنبه": 1, "دوشنبه": 2, "سه‌شنبه": 3, "سه شنبه": 3, "چهارشنبه": 4, "چهار شنبه": 4, "پنجشنبه": 5, "پنج‌شنبه": 5, "پنج شنبه": 5, "جمعه": 6}
WEEKDAY_NAMES = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]


def _money(v) -> int:
    """«۷۰۰۰۰», «70,000», «۷۰ هزار», «۱.۲ میلیون» -> toman."""
    from .catalog import parse_number

    n = parse_number(str(v))
    if n is None:
        raise ValueError("مبلغ معتبر نیست")
    return n


def _num(v) -> int:
    s = norm(str(v)).replace(",", "").replace("٬", "").replace(" ", "")
    if not re.fullmatch(r"\d+", s):
        raise ValueError("عدد معتبر نیست")
    return int(s)


class MenuRow(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    price: int = Field(ge=0)
    options: str = Field(default="", max_length=300)  # «سایز: معمولی، بزرگ (+۳۰٬۰۰۰)؛ شیر: معمولی، بادام»

    @field_validator("name", "options", mode="before")
    @classmethod
    def _strip(cls, v):
        return (v or "").strip()

    @field_validator("price", mode="before")
    @classmethod
    def _price(cls, v):
        return _money(v)

    def groups(self) -> list[dict]:
        """«سایز: معمولی، بزرگ (+30000)؛ شیر: معمولی، بادام» -> option groups with the added price per choice."""
        out = []
        for part in re.split(r"[؛;\n]+", self.options):
            if ":" not in part and "：" not in part:
                continue
            name, rest = re.split(r"[:：]", part, maxsplit=1)
            choices, prices = [], []
            for c in re.split(r"[،,]", rest):
                c = c.strip()
                if not c:
                    continue
                m = re.search(r"\(\s*\+?\s*([^)]*?)\s*(?:تومان)?\s*\)", c)
                prices.append(_money(m.group(1)) if m else 0)
                choices.append(re.sub(r"\(.*?\)", "", c).strip())
            if name.strip() and len(choices) >= 2:
                out.append({"name": name.strip(), "choices": choices, "prices": prices if any(prices) else []})
        return out


class QuizRow(BaseModel):
    question: str = Field(min_length=3, max_length=300)
    options: list[str] = Field(min_length=2, max_length=5)
    correct: int = Field(ge=1)  # 1-based as the owner sees it

    @field_validator("options", mode="before")
    @classmethod
    def _opts(cls, v):
        return [str(o).strip() for o in (v or []) if str(o).strip()]

    @field_validator("correct", mode="before")
    @classmethod
    def _correct(cls, v):
        return _num(v)

    @model_validator(mode="after")
    def _in_range(self):
        if self.correct > len(self.options):
            raise ValueError("شمارهٔ گزینهٔ درست از تعداد گزینه‌ها بیشتر است")
        if len(set(self.options)) != len(self.options):
            raise ValueError("گزینه‌های یک سؤال نباید تکراری باشند")
        return self


class SessionRow(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    when: str  # a weekday («پنجشنبه») = every week, or a Jalali date («۱۴۰۵/۰۷/۲۲») = one session
    time: str  # HH:MM
    capacity: int = Field(ge=1, le=500)
    price: int = Field(default=0, ge=0)

    @field_validator("capacity", mode="before")
    @classmethod
    def _cap(cls, v):
        return _num(v)

    @field_validator("price", mode="before")
    @classmethod
    def _price(cls, v):
        return 0 if v in ("", None) else _money(v)

    @model_validator(mode="after")
    def _ok(self):
        self.when, self.time = self.when.strip(), norm(self.time).strip()
        if not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", self.time):
            raise ValueError("ساعت را به شکل ۱۶:۳۰ بنویسید")
        self.time = f"{int(self.time.split(':')[0]):02d}:{self.time.split(':')[1]}"
        if self.when not in WEEKDAYS and jalali_date(norm(self.when)) is None:
            raise ValueError("روز هفته (مثل پنجشنبه) یا تاریخ شمسی (مثل ۱۴۰۵/۰۷/۲۲) بنویسید")
        return self

    def is_weekly(self) -> bool:
        return self.when in WEEKDAYS


class FaqRow(BaseModel):
    question: str = Field(min_length=3, max_length=200)
    answer: str = Field(min_length=1, max_length=1500)


class ServiceRow(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    duration_minutes: int = Field(ge=10, le=480)
    price: int = Field(default=0, ge=0)

    @field_validator("duration_minutes", mode="before")
    @classmethod
    def _dur(cls, v):
        return _num(v)

    @field_validator("price", mode="before")
    @classmethod
    def _price(cls, v):
        return 0 if v in ("", None) else _money(v)


ROW = {"menu_items": MenuRow, "quiz_questions": QuizRow, "sessions": SessionRow, "faq_entries": FaqRow, "services": ServiceRow}
TITLE = {"menu_items": "منو", "quiz_questions": "سؤال‌های آزمون", "sessions": "جلسه‌ها", "faq_entries": "پرسش‌های متداول", "services": "خدمت‌ها"}


class Parsed(BaseModel):
    kind: Literal["menu_items", "quiz_questions", "sessions", "faq_entries", "services"]
    rows: list


def parse(raw: dict[str, list[dict]] | None) -> dict[str, list[BaseModel]]:
    """Validate the rows the panel sent; raises ValueError with a Persian message naming the table and the row."""
    out: dict[str, list[BaseModel]] = {}
    for kind, rows in (raw or {}).items():
        if kind not in KINDS:
            raise ValueError("نوع داده نامعتبر است")
        if not rows:
            continue
        if len(rows) > MAX_ROWS[kind]:
            raise ValueError(f"«{TITLE[kind]}» حداکثر {fa_digits(str(MAX_ROWS[kind]))} ردیف دارد")
        parsed = []
        for i, r in enumerate(rows, 1):
            try:
                parsed.append(ROW[kind].model_validate(r))
            except Exception as e:  # noqa: BLE001 - pydantic errors carry the field; show the row
                first = getattr(e, "errors", lambda: [{"msg": str(e)}])()[0]
                raise ValueError(f"«{TITLE[kind]}»، ردیف {fa_digits(str(i))}: {str(first.get('msg', e)).removeprefix('Value error, ')}") from e
        out[kind] = parsed
    return out


def _toman(n: int) -> str:
    return fa_digits(f"{n:,}") + " تومان"


def to_text(data: dict[str, list[BaseModel]]) -> str:
    """The rows as exact Persian lines: this is what the model reads (and what the chat history shows) as the owner's answer."""
    parts = []
    for kind, rows in data.items():
        lines = []
        for r in rows:
            if kind == "menu_items":
                lines.append(f"- {r.name}: {_toman(r.price)}" + (f" (گزینه‌ها: {r.options})" if r.options else ""))
            elif kind == "quiz_questions":
                lines.append(f"- {r.question} | " + " / ".join(r.options) + f" | پاسخ درست: گزینه‌ی {fa_digits(str(r.correct))} ({r.options[r.correct - 1]})")
            elif kind == "sessions":
                lines.append(f"- {r.label}: {r.when} ساعت {r.time}، ظرفیت {fa_digits(str(r.capacity))}" + (f"، {_toman(r.price)}" if r.price else ""))
            elif kind == "faq_entries":
                lines.append(f"- {r.question} ← {r.answer}")
            elif kind == "services":
                lines.append(f"- {r.name}: {fa_digits(str(r.duration_minutes))} دقیقه" + (f"، {_toman(r.price)}" if r.price else ""))
        parts.append(f"{TITLE[kind]} ({fa_digits(str(len(rows)))} مورد):\n" + "\n".join(lines))
    return "\n\n".join(parts)


def _first(spec: dict, kind_block: str, pred=lambda b: True):
    return next((b for b in spec.get("blocks", []) if b.get("type") == kind_block and pred(b)), None)


def apply(spec: dict, data: dict[str, list[BaseModel]]) -> dict:
    """Copy the owner's rows into the designed spec exactly. Raises ValueError (sent back to the model) when the design has no block to hold a table."""
    spec = {**spec, "blocks": [dict(b) for b in spec.get("blocks", [])]}
    for kind, rows in data.items():
        if kind == "menu_items":
            blk = _first(spec, "catalog_order")
            if blk is None:
                raise ValueError("the owner filled in a MENU table: the bot needs a catalog_order block (source inline) to hold it")
            blk["source"] = "inline"
            blk["items"] = [{"id": f"i{n}", "name": r.name, "price": r.price, "options": r.groups()} for n, r in enumerate(rows, 1)]
        elif kind == "quiz_questions":
            blk = _first(spec, "quiz", lambda b: not b.get("personality"))
            if blk is None:
                raise ValueError("the owner filled in QUIZ QUESTIONS: the bot needs a right/wrong quiz block to hold them")
            blk["questions"] = [{"question": r.question, "options": r.options, "correct": r.correct - 1, "outcomes": [], "media": "none"} for r in rows]
            blk["pick"] = min(blk.get("pick") or 0, len(rows))
        elif kind == "sessions":
            blk = _first(spec, "booking", lambda b: not b.get("schedule"))
            if blk is None:
                raise ValueError("the owner filled in SESSIONS: the bot needs a booking block with fixed slots (no schedule) to hold them")
            slots = []
            for n, r in enumerate(rows, 1):
                s = {"id": f"s{n}", "label": r.label, "capacity": r.capacity, "price": r.price, "time": r.time}
                if r.is_weekly():
                    s["weekday"] = WEEKDAYS[r.when]
                    s["label"] = f"{r.label}، {r.when} ساعت {fa_digits(r.time)}" if r.when not in r.label else r.label
                else:
                    s["on"] = norm(r.when)
                slots.append(s)
            blk["slots"] = slots
        elif kind == "faq_entries":
            blk = _first(spec, "faq")
            if blk is None:
                raise ValueError("the owner filled in FAQ entries: the bot needs a faq block to hold them")
            blk["entries"] = [{"question": r.question, "answer": r.answer, "alternates": [], "category": "", "media": "none", "then": "", "then_label": ""} for r in rows]
        elif kind == "services":
            blk = _first(spec, "booking", lambda b: b.get("schedule"))
            if blk is None:
                raise ValueError("the owner filled in SERVICES: the bot needs a booking block with a `schedule` to hold them")
            sch = dict(blk["schedule"])
            sch["services"] = [{"id": f"v{n}", "name": r.name, "duration_minutes": r.duration_minutes, "price": r.price, "staff": []} for n, r in enumerate(rows, 1)]
            blk["schedule"] = sch
    return spec
