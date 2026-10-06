"""Support tickets: an owner writes to the Botyar team (above all when the agent can't build the kind of bot they
asked for), the team answers from the same «پشتیبانی» page, and the owner sees the reply there."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import billing
from .auth import current_user
from .db import get_db
from .models import Bot, SupportTicket, User

router = APIRouter()
PER_DAY = 5  # new tickets per owner in 24 hours: plenty for real use, a wall for floods

Kind = Literal["unsupported", "problem", "question", "idea"]


class TicketIn(BaseModel):
    kind: Kind
    text: str = Field(max_length=2000)
    bot_id: int | None = None
    context: str = Field(default="", max_length=2000)  # the agent's decline message, when it comes from the builder


class ReplyIn(BaseModel):
    reply: str = Field(default="", max_length=4000)
    status: Literal["answered", "closed"] = "answered"


def _out(t: SupportTicket, bot_name: str | None = None, username: str | None = None) -> dict:
    out = {"id": t.id, "kind": t.kind, "text": t.text, "context": t.context, "status": t.status, "reply": t.reply,
           "bot_id": t.bot_id, "bot_name": bot_name, "created_at": t.created_at.isoformat(),
           "replied_at": t.replied_at.isoformat() if t.replied_at else None, "new_reply": not t.user_seen}
    if username is not None:
        out["username"] = username
    return out


@router.post("/api/tickets")
def create(body: TicketIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    text = body.text.strip()
    if len(text) < 5:
        raise HTTPException(422, "لطفاً درخواست خود را کمی کامل‌تر بنویسید.")
    if body.bot_id is not None:
        bot = db.get(Bot, body.bot_id)
        if not bot or bot.user_id != user.id:
            raise HTTPException(404, "ربات یافت نشد")
    # the same request sent twice (a double click, the builder card after a reload) is the same ticket
    same = db.scalars(select(SupportTicket).where(SupportTicket.user_id == user.id, SupportTicket.kind == body.kind,
                                                  SupportTicket.bot_id == body.bot_id, SupportTicket.text == text)).first()
    if same:
        return _out(same)
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    recent = db.scalar(select(func.count()).select_from(SupportTicket).where(SupportTicket.user_id == user.id, SupportTicket.created_at >= since))
    if (recent or 0) >= PER_DAY:
        raise HTTPException(429, f"در هر ۲۴ ساعت حداکثر {PER_DAY} درخواست می‌توانید ثبت کنید؛ لطفاً بعداً دوباره تلاش کنید.")
    t = SupportTicket(user_id=user.id, bot_id=body.bot_id, kind=body.kind, text=text, context=body.context.strip())
    db.add(t)
    db.commit()
    return _out(t)


@router.get("/api/tickets")
def mine(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = list(db.scalars(select(SupportTicket).where(SupportTicket.user_id == user.id).order_by(SupportTicket.id.desc()).limit(100)))
    names = {b.id: b.name for b in db.scalars(select(Bot).where(Bot.user_id == user.id))}
    out = [_out(t, names.get(t.bot_id)) for t in rows]
    for t in rows:  # opening the page reads the replies (each still carries new_reply=True in this response)
        t.user_seen = True
    db.commit()
    return out


@router.get("/api/tickets/unread")
def unread(user: User = Depends(current_user), db: Session = Depends(get_db)):
    n = db.scalar(select(func.count()).select_from(SupportTicket).where(SupportTicket.user_id == user.id, SupportTicket.user_seen.is_(False)))
    return {"count": n or 0, "admin_open": _open_count(db) if billing.is_admin(user) else None}


def _open_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(SupportTicket).where(SupportTicket.status == "open")) or 0


def _admin(user: User):
    if not billing.is_admin(user):
        raise HTTPException(404, "یافت نشد")  # not 403: do not reveal that the page exists


@router.get("/api/admin/tickets")
def all_tickets(user: User = Depends(current_user), db: Session = Depends(get_db)):
    _admin(user)
    rows = list(db.scalars(select(SupportTicket).order_by(SupportTicket.status != "open", SupportTicket.id.desc()).limit(200)))
    users = {u.id: u.username for u in db.scalars(select(User).where(User.id.in_({t.user_id for t in rows})))}
    bots = {b.id: b.name for b in db.scalars(select(Bot).where(Bot.id.in_({t.bot_id for t in rows if t.bot_id})))}
    return [_out(t, bots.get(t.bot_id), users.get(t.user_id, "")) for t in rows]


@router.post("/api/admin/tickets/{tid}")
def answer(tid: int, body: ReplyIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _admin(user)
    t = db.get(SupportTicket, tid)
    if not t:
        raise HTTPException(404, "درخواست یافت نشد")
    reply = body.reply.strip()
    if body.status == "answered" and not reply:
        raise HTTPException(422, "متن پاسخ خالی است")
    if reply:
        t.reply, t.replied_at, t.user_seen = reply, datetime.now(timezone.utc), False
    t.status = body.status
    db.commit()
    return _out(t)
