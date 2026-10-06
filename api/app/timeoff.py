"""Hours the owner closes from the dashboard (Tuesday afternoon off, a staff member's leave). Appointment times and
class sessions inside them are no longer offered; bookings already made there are reported, not cancelled."""
from __future__ import annotations

import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import current_user
from .dates import jalali_str, parse_jalali
from .db import get_db
from .models import Bot, BotVersion, Record, TimeOff, User
from .spec import BotSpec

router = APIRouter()
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class TimeOffIn(BaseModel):
    block_id: str
    date: str = Field(max_length=30)  # Jalali, as the owner types it: «۱۴۰۵/۰۷/۲۰» or «۲۰ مهر»
    start: str
    end: str
    staff: str = ""
    note: str = Field(default="", max_length=100)


def _spec(bot_id: int, user: User, db: Session) -> BotSpec:
    bot = db.get(Bot, bot_id)
    if not bot or bot.user_id != user.id:
        raise HTTPException(404, "ربات یافت نشد")
    ver = db.scalars(select(BotVersion).where(BotVersion.bot_id == bot_id).order_by(BotVersion.version.desc())).first()
    if ver is None:
        raise HTTPException(409, "ربات هنوز ساخته نشده است")
    return BotSpec.model_validate(ver.spec)


def _out(t: TimeOff) -> dict:
    return {"id": t.id, "block_id": t.block_id, "date": t.date, "date_fa": jalali_str(date.fromisoformat(t.date)),
            "start": t.start, "end": t.end, "staff": t.staff, "note": t.note}


@router.get("/api/bots/{bot_id}/time-off")
def list_time_off(bot_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _spec(bot_id, user, db)
    today = date.today().isoformat()
    rows = db.scalars(select(TimeOff).where(TimeOff.bot_id == bot_id, TimeOff.date >= today).order_by(TimeOff.date, TimeOff.start))
    return [_out(t) for t in rows]


@router.post("/api/bots/{bot_id}/time-off")
def add_time_off(bot_id: int, body: TimeOffIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    spec = _spec(bot_id, user, db)
    block = next((b for b in spec.blocks if b.id == body.block_id and b.type == "booking"), None)
    if block is None:
        raise HTTPException(422, "بخش نوبت‌دهی یافت نشد")
    day = parse_jalali(body.date)
    if day is None:
        raise HTTPException(422, "تاریخ معتبر نیست؛ به شکل ۱۴۰۵/۰۷/۲۰ یا «۲۰ مهر» بنویسید.")
    if day < date.today():
        raise HTTPException(422, "این تاریخ گذشته است.")
    if not (HHMM.match(body.start) and HHMM.match(body.end)) or body.start >= body.end:
        raise HTTPException(422, "ساعت شروع باید پیش از ساعت پایان باشد (به شکل ۱۳:۰۰).")
    staff_names = block.schedule.staff if block.schedule else []
    if body.staff and body.staff not in staff_names:
        raise HTTPException(422, "همکار یافت نشد")
    t = TimeOff(bot_id=bot_id, block_id=block.id, date=day.isoformat(), start=body.start, end=body.end, staff=body.staff, note=body.note.strip())
    db.add(t)
    db.commit()
    # bookings already inside the closed hours: reported so the owner can cancel them (with a reason) one by one
    s0, e0 = body.start, body.end
    clashes = 0
    for r in db.scalars(select(Record).where(Record.bot_id == bot_id, Record.collection == block.id, Record.sandbox.is_(False))):
        d = r.data
        if d.get("date") != day.isoformat() or d.get("status") not in ("confirmed", "waitlisted", "awaiting_payment"):
            continue
        if body.staff and d.get("staff") not in ("", None, body.staff):
            continue
        slot = next((s for s in block.slots if s.id == d.get("slot")), None)
        start = d.get("time") or (slot.time if slot else None)
        if start and s0 <= start < e0:
            clashes += 1
    return {**_out(t), "clashes": clashes}


@router.delete("/api/bots/{bot_id}/time-off/{tid}")
def delete_time_off(bot_id: int, tid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _spec(bot_id, user, db)
    t = db.get(TimeOff, tid)
    if not t or t.bot_id != bot_id:
        raise HTTPException(404, "این بازه‌ی بسته یافت نشد")
    db.delete(t)
    db.commit()
    return {"ok": True}
