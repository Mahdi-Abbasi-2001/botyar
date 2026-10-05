"""The owner's customer list: everyone who has written to a live bot, with last activity and a spreadsheet export."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import billing
from .auth import current_user
from .db import get_db
from .export import _file, _fmt, render
from .dates import jalali_str
from .models import Bot, CustomerSeen, User

router = APIRouter()
PAGE = 50
CHANNEL = {"bale": "بله", "tg": "تلگرام"}


def _bot(bot_id: int, user: User, db: Session) -> Bot:
    bot = db.get(Bot, bot_id)
    if not bot or bot.user_id != user.id:
        raise HTTPException(404, "ربات یافت نشد")
    return bot


def _row(c: CustomerSeen) -> dict:
    chan = c.key.split(":", 1)[0]
    return {"id": c.id, "name": c.name or "—", "channel": CHANNEL.get(chan, chan), "messages": c.messages,
            "first_seen": billing._aware(c.first_seen).isoformat(), "last_seen": billing._aware(c.last_seen).isoformat()}  # the chat id itself is never exposed


@router.get("/api/bots/{bot_id}/customers")
def customers(bot_id: int, q: str = "", page: int = 0, user: User = Depends(current_user), db: Session = Depends(get_db)):
    bot = _bot(bot_id, user, db)
    cond = [CustomerSeen.bot_id == bot.id]
    if q.strip():
        cond.append(CustomerSeen.name.ilike(f"%{q.strip()[:40]}%"))
    total = db.scalar(select(func.count()).select_from(CustomerSeen).where(*cond)) or 0
    rows = db.scalars(select(CustomerSeen).where(*cond).order_by(CustomerSeen.last_seen.desc()).offset(max(page, 0) * PAGE).limit(PAGE)).all()
    plan = billing.limits(db, bot.user_id)
    return {"total": total, "active_30d": billing.customers_30d(db, bot.id), "cap": plan["customers"], "plan": plan["name"],
            "page": max(page, 0), "page_size": PAGE, "items": [_row(c) for c in rows]}


@router.get("/api/bots/{bot_id}/export/customers")
def export_customers(bot_id: int, format: str = "csv", user: User = Depends(current_user), db: Session = Depends(get_db)):
    bot = _bot(bot_id, user, db)
    fmt = _fmt(format)
    rows = db.scalars(select(CustomerSeen).where(CustomerSeen.bot_id == bot.id).order_by(CustomerSeen.last_seen.desc()).limit(20000)).all()
    data, media = render(["نام", "پیام‌رسان", "اولین پیام", "آخرین فعالیت", "تعداد پیام"],
                         [[c.name or "", CHANNEL.get(c.key.split(":", 1)[0], c.key.split(":", 1)[0]),
                           billing._aware(c.first_seen).date().isoformat(), billing._aware(c.last_seen).date().isoformat(), c.messages] for c in rows], fmt, "customers")
    return _file(data, media, f"customers.{fmt}")
