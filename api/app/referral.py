"""Invite links. Each customer has a personal code; the link is the bot's own link plus that code
(ble.ir/<bot>?start=<code>, t.me/<bot>?start=<code>). A person who arrives through it as a brand-new customer is counted once
for the referrer, who is told. Self-invites and customers who already used the bot never count."""
from __future__ import annotations

import re
import secrets
import string

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auth import current_user
from .db import get_db
from .models import Bot, CustomerSeen, ReferralCode, ReferralJoin, User

router = APIRouter()
PAYLOAD = re.compile(r"r[a-z0-9]{7}")
_ALPHA = string.ascii_lowercase + string.digits
HOST = {"bale": "https://ble.ir/", "tg": "https://t.me/"}


def code_for(db: Session, bot_id: int, key: str) -> str:
    row = db.scalars(select(ReferralCode).where(ReferralCode.bot_id == bot_id, ReferralCode.key == key)).first()
    if row:
        return row.code
    for _ in range(8):
        code = "r" + "".join(secrets.choice(_ALPHA) for _ in range(7))
        if not db.scalars(select(ReferralCode).where(ReferralCode.code == code)).first():
            db.add(ReferralCode(bot_id=bot_id, key=key, code=code))
            db.flush()
            return code
    raise RuntimeError("could not allocate a referral code")


def resolve(db: Session, payload: str) -> ReferralCode | None:
    return db.scalars(select(ReferralCode).where(ReferralCode.code == payload)).first() if PAYLOAD.fullmatch(payload or "") else None


def link(ch_name: str, username: str, code: str) -> str:
    return f"{HOST.get(ch_name, HOST['bale'])}{username}?start={code}" if username else ""


def count_for(db: Session, bot_id: int, key: str) -> int:
    return db.scalar(select(func.count()).select_from(ReferralJoin).where(ReferralJoin.bot_id == bot_id, ReferralJoin.referrer_key == key)) or 0


def convert(db: Session, bot_id: int, ref: ReferralCode, invited_key: str, goal: int | None) -> list[dict]:
    """Record the invite and return notify_customer actions for the referrer. Call only when the invited customer is brand new."""
    if ref.bot_id != bot_id or ref.key == invited_key:
        return []
    if db.scalars(select(ReferralJoin).where(ReferralJoin.bot_id == bot_id, ReferralJoin.invited_key == invited_key)).first():
        return []
    db.add(ReferralJoin(bot_id=bot_id, referrer_key=ref.key, invited_key=invited_key))
    db.flush()
    n = count_for(db, bot_id, ref.key)
    text = f"🎉 یک نفر با لینک اختصاصی شما وارد شد! دعوت‌های موفق: {n}" + (f" از {goal}" if goal else "")
    if goal and n == goal:
        text += "\nبه هدف رسیدید! 🎁"
    return [{"type": "notify_customer", "cust": ref.key, "text": text}]


@router.get("/api/bots/{bot_id}/referrals")
def leaderboard(bot_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    bot = db.get(Bot, bot_id)
    if not bot or bot.user_id != user.id:
        raise HTTPException(404, "ربات یافت نشد")
    total = db.scalar(select(func.count()).select_from(ReferralJoin).where(ReferralJoin.bot_id == bot_id)) or 0
    rows = db.execute(select(ReferralJoin.referrer_key, func.count()).where(ReferralJoin.bot_id == bot_id)
                      .group_by(ReferralJoin.referrer_key).order_by(func.count().desc()).limit(10)).all()
    names = {c.key: c.name for c in db.scalars(select(CustomerSeen).where(CustomerSeen.bot_id == bot_id, CustomerSeen.key.in_([r[0] for r in rows] or [""])))}
    return {"total": total, "top": [{"name": names.get(k) or "—", "invited": n} for k, n in rows]}  # keys (chat ids) are never returned
