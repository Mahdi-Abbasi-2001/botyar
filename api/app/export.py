"""Data export (CSV / XLSX) for products and records, so an owner is never locked in.
CSV is UTF-8 with a BOM (Excel then reads Persian correctly) and is re-importable through the catalog importer.
XLSX keeps phone numbers as text (Excel drops the leading zero of 0912… when it opens a CSV)."""
from __future__ import annotations

import csv
import io
from datetime import timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import current_user
from .db import get_db
from .models import Bot, BotVersion, Product, Record, User

router = APIRouter()
TEHRAN = ZoneInfo("Asia/Tehran")
CSV_TYPE = "text/csv; charset=utf-8"
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

KEY_LABEL = {"question": "سؤال", "note": "یادداشت", "time": "ساعت", "staff": "کارمند", "date": "تاریخ (میلادی)", "name": "نام", "phone": "موبایل", "status": "وضعیت", "slot_label": "زمان", "items": "اقلام", "total": "جمع (تومان)"}
STATUS_LABEL = {"confirmed": "تأیید شده", "waitlisted": "لیست انتظار", "new": "جدید", "preparing": "در حال آماده‌سازی", "ready": "آماده", "done": "تحویل شد", "cancelled": "لغو شده", "unanswered": "بدون پاسخ", "handled": "رسیدگی شد"}


def safe(v):
    """Neutralise spreadsheet formula injection: customers type these values, owners open them in Excel."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return v


def render(headers: list[str], rows: list[list], fmt: str, sheet: str = "data") -> tuple[bytes, str]:
    if fmt == "xlsx":
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = sheet[:31] or "data"
        ws.sheet_view.rightToLeft = True
        ws.append([safe(h) for h in headers])
        for r in rows:
            ws.append([safe(c) if isinstance(c, str) else c for c in r])  # strings stay text: 09123456789 keeps its zero
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue(), XLSX_TYPE
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([safe(h) for h in headers])
    for r in rows:
        w.writerow(["" if c is None else safe(c) for c in r])
    return ("﻿" + buf.getvalue()).encode("utf-8"), CSV_TYPE


def _own(bot_id: int, user: User, db: Session) -> Bot:
    bot = db.get(Bot, bot_id)
    if not bot or bot.user_id != user.id:
        raise HTTPException(404, "ربات یافت نشد")
    return bot


def _fmt(fmt: str) -> str:
    if fmt not in ("csv", "xlsx"):
        raise HTTPException(400, "فرمت باید csv یا xlsx باشد")
    return fmt


def _file(data: bytes, media: str, name: str) -> Response:
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})


@router.get("/api/bots/{bot_id}/export/products")
def export_products(bot_id: int, format: str = "csv", block: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _own(bot_id, user, db)
    fmt = _fmt(format)
    q = select(Product).where(Product.bot_id == bot_id).order_by(Product.block_id, Product.position, Product.id)
    if block:
        q = q.where(Product.block_id == block)
    prods = list(db.scalars(q))
    if not prods:
        raise HTTPException(404, "محصولی برای خروجی گرفتن نیست")
    groups: list[str] = []
    for p in prods:
        for o in p.options or []:
            if o["name"] not in groups:
                groups.append(o["name"])
    headers = ["نام", "دسته", "قیمت (تومان)", "موجودی", *groups, "توضیحات"]
    rows = []
    for p in prods:
        opt = {o["name"]: " / ".join(o["choices"]) for o in (p.options or [])}
        rows.append([p.name, p.category, p.price, p.stock if p.stock is not None else "", *[opt.get(g, "") for g in groups], p.description])
    data, media = render(headers, rows, fmt, "products")
    return _file(data, media, f"botyar-products-{bot_id}.{fmt}")


def _describe(v) -> str:
    """Records hold lists/dicts (order lines, options); turn them into one readable Persian cell."""
    if isinstance(v, list):
        parts = []
        for it in v:
            if isinstance(it, dict) and "name" in it:
                opts = " ".join(str(x) for x in (it.get("options") or {}).values())
                parts.append(f"{it['name']}{(' ' + opts) if opts else ''}{(' × ' + str(it['qty'])) if it.get('qty') else ''}")
            else:
                parts.append(str(it))
        return "؛ ".join(parts)
    if isinstance(v, dict):
        return "، ".join(f"{k}: {x}" for k, x in v.items())
    return v


@router.get("/api/bots/{bot_id}/export/records")
def export_records(bot_id: int, format: str = "csv", sandbox: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _own(bot_id, user, db)
    fmt = _fmt(format)
    rows_db = list(db.scalars(select(Record).where(Record.bot_id == bot_id, Record.sandbox == sandbox).order_by(Record.id)))
    if not rows_db:
        raise HTTPException(404, "ثبتی برای خروجی گرفتن نیست")
    ver = db.scalars(select(BotVersion).where(BotVersion.bot_id == bot_id).order_by(BotVersion.version.desc())).first()
    blocks = {b["id"]: b for b in (ver.spec["blocks"] if ver else [])}
    labels = dict(KEY_LABEL)
    for b in blocks.values():
        for f in b.get("fields", []):
            labels.setdefault(f["key"], f["label"])
    cols: list[str] = []
    for r in rows_db:
        for k in r.data:
            if not k.startswith("_") and k != "slot" and k not in cols:
                cols.append(k)
    headers = ["شناسه", "تاریخ", "بخش", *[labels.get(k, k) for k in cols]]
    out = []
    for r in rows_db:
        when = r.created_at.replace(tzinfo=timezone.utc).astimezone(TEHRAN).strftime("%Y-%m-%d %H:%M") if r.created_at else ""
        cells = []
        for k in cols:
            v = _describe(r.data.get(k, ""))
            cells.append(STATUS_LABEL.get(v, v) if k == "status" else v)
        out.append([r.id, when, blocks.get(r.collection, {}).get("title", r.collection), *cells])
    data, media = render(headers, out, fmt, "records")
    return _file(data, media, f"botyar-records-{bot_id}.{fmt}")
