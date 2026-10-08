"""Filling a build-chat table from a file, a photo or pasted text. The same readers as the Products and Questions tabs (Excel/CSV/pasted tables are
read by code, photos/PDF/free text by the model), but they work before the bot exists: the rows come back to the table card for the owner to check."""
from __future__ import annotations

import base64
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from . import llm
from .auth import current_user
from .catalog import (MAX_FILE, MAX_IMAGES, _decode, _own, checked_image, clean_options, convert, extract_from_images, map_columns, parse_delimited,
                      parse_xlsx, pdf_to_images)
from .datasets import KINDS, MAX_ROWS
from .db import get_db
from .models import User
from .quiz_bank import IMPORT_PROMPT, Extracted as QuestionsExtracted, QOut, _clean, _guard, questions_from_rows

log = logging.getLogger("botyar.datasets")
router = APIRouter()

# the order of the cells when plain text is pasted for a kind that has no reader of its own
COLUMNS = {
    "sessions": ["label", "when", "time", "capacity", "price"],
    "faq_entries": ["question", "answer"],
    "services": ["name", "duration_minutes", "price"],
}


def _options_text(options: list[dict]) -> str:
    return "؛ ".join(f"{o['name']}: " + "، ".join(c + (f" (+{o['prices'][i]:,})" if o.get("prices") and i < len(o["prices"]) and o["prices"][i] else "")
                                                  for i, c in enumerate(o["choices"])) for o in options if o.get("choices"))


@router.post("/api/bots/{bot_id}/datasets/import")
async def import_rows(bot_id: int, kind: str = Form(...), text: str = Form(""), files: list[UploadFile] = File(default=[]),
                      user: User = Depends(current_user), db: Session = Depends(get_db)):
    _own(bot_id, user, db)
    if kind not in KINDS:
        raise HTTPException(422, "نوع داده نامعتبر است")
    if not files and not text.strip():
        raise HTTPException(400, "یک فایل انتخاب کنید یا جدول را جای‌گذاری کنید")
    images: list[tuple[bytes, str]] = []
    rows: list[list[str]] | None = None
    raw = text
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
            raw = "\n".join("\t".join(r) for r in rows)
    if rows is None and not images and raw.strip():
        rows = parse_delimited(raw)
    warnings: list[str] = []
    out: list[dict] = []

    if kind == "menu_items":
        if images:
            _guard(user, db)
            try:
                ex = extract_from_images(db, bot_id, images[:MAX_IMAGES])
            except Exception:  # noqa: BLE001
                log.exception("menu vision import failed")
                raise HTTPException(502, "خواندن تصویر ناموفق بود؛ چند لحظه بعد دوباره تلاش کنید")
            products, warnings = [p.model_dump() for p in ex.products], list(ex.warnings)
            for p in products:
                p["options"] = clean_options(p["options"])
        else:
            if not rows or len(rows) < 2:
                raise HTTPException(422, "جدول باید یک سطر عنوان و حداقل یک سطر محصول داشته باشد")
            _guard(user, db)
            try:
                products, warnings = convert(rows, map_columns(db, bot_id, rows))
            except HTTPException:
                raise
            except Exception:  # noqa: BLE001
                log.exception("menu column mapping failed")
                raise HTTPException(502, "تشخیص ستون‌ها ناموفق بود؛ چند لحظه بعد دوباره تلاش کنید")
        out = [{"name": p["name"], "price": p["price"], "options": _options_text(p.get("options", []))} for p in products][:MAX_ROWS[kind]]

    elif kind == "quiz_questions":
        parsed = questions_from_rows(rows) if (rows and not images) else None
        if parsed is not None:
            qs, warnings = _clean([QOut(**q) for q in parsed[0]], list(parsed[1]))
        else:
            _guard(user, db)
            try:
                if images:
                    parts: list[dict] = [{"type": "input_text", "text": "Extract the quiz questions from these pages."}]
                    for data, mime in images[:MAX_IMAGES]:
                        parts.append({"type": "input_image", "image_url": f"data:{mime};base64,{base64.b64encode(data).decode()}"})
                    ex = llm.call(db, bot_id=bot_id, run_id=0, step="quiz_vision", instructions=IMPORT_PROMPT, input=[{"role": "user", "content": parts}],
                                  schema=QuestionsExtracted, effort="low", max_out=16000)
                else:
                    ex = llm.call(db, bot_id=bot_id, run_id=0, step="quiz_import", instructions=IMPORT_PROMPT, input=raw[:60000], schema=QuestionsExtracted, effort="low", max_out=16000)
            except Exception:  # noqa: BLE001
                log.exception("quiz import failed")
                raise HTTPException(502, "خواندن سؤال‌ها ناموفق بود؛ چند لحظه بعد دوباره تلاش کنید")
            qs, warnings = _clean(ex.questions, list(ex.warnings))
        out = [{"question": q["question"], "options": q["options"][:4], "correct": q["correct"] + 1} for q in qs if q["correct"] < 4][:MAX_ROWS[kind]]
        if len(out) < len(qs):
            warnings.append("سؤال‌هایی که گزینهٔ درستشان گزینهٔ پنجم بود یا بیش از ۴ گزینه داشتند ساده‌سازی یا کنار گذاشته شدند.")

    else:  # sessions, FAQ, services: columns by position, no model involved
        if images:
            raise HTTPException(422, "برای این جدول فقط متن یا فایل Excel/CSV را بفرستید")
        cols = COLUMNS[kind]
        for r in rows or []:
            if any(c.strip() for c in r):
                out.append({k: (r[i].strip() if i < len(r) else "") for i, k in enumerate(cols)})
        out = out[:MAX_ROWS[kind]]
        warnings.append("ستون‌ها به ترتیب خوانده شدند: " + "، ".join({"label": "عنوان", "when": "روز یا تاریخ", "time": "ساعت", "capacity": "ظرفیت", "price": "قیمت",
                                                                    "question": "سؤال", "answer": "پاسخ", "name": "نام", "duration_minutes": "مدت (دقیقه)"}[k] for k in cols))
    if not out:
        warnings.append("ردیفی پیدا نشد.")
    return {"rows": out, "warnings": warnings}
