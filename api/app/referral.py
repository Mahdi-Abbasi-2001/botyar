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
from .models import Bot, CustomerSeen, Record, ReferralCode, ReferralJoin, User

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
    return db.scalar(select(func.count()).select_from(ReferralJoin).where(ReferralJoin.bot_id == bot_id, ReferralJoin.referrer_key == key,
                                                                           ReferralJoin.confirmed.is_not(False))) or 0


def rewards(block, n: int) -> str:
    """What reaching exactly n invites earns: the goal's reward and code, or a tier's."""
    if block is None:
        return ""
    for goal, text, code in [(block.goal, block.reward_text, block.reward_code), *((t.goal, t.reward_text, t.reward_code) for t in block.tiers)]:
        if n == goal:
            return f"\nبه هدف رسیدید! 🎁\n{text}" + (f"\nکد تخفیف شما: {code}" if code else "")
    return ""


def next_goal(block, n: int) -> int:
    return next((g for g in [block.goal, *(t.goal for t in block.tiers)] if g > n), 0)


def _counted(db: Session, bot_id: int, referrer: str, block, ordered: bool = False) -> list[dict]:
    n = count_for(db, bot_id, referrer)
    goal = next_goal(block, n - 1) if block is not None else 0
    head = "🎉 دوستی که دعوت کرده بودید اولین سفارش یا نوبتش را ثبت کرد!" if ordered else "🎉 یک نفر با لینک اختصاصی شما وارد شد!"
    text = f"{head} دعوت‌های موفق: {n}" + (f" از {goal}" if goal else "") + rewards(block, n)
    return [{"type": "notify_customer", "cust": referrer, "text": text}]


def convert(db: Session, bot_id: int, ref: ReferralCode, invited_key: str, block=None) -> list[dict]:
    """Record the invite and return notify_customer actions for the referrer. Call only when the invited customer is brand new.
    With count_after="order" the invite waits (unconfirmed) until the friend's first order or booking (see confirm_pending)."""
    if ref.bot_id != bot_id or ref.key == invited_key:
        return []
    if db.scalars(select(ReferralJoin).where(ReferralJoin.bot_id == bot_id, ReferralJoin.invited_key == invited_key)).first():
        return []
    pending = block is not None and block.count_after == "order"
    db.add(ReferralJoin(bot_id=bot_id, referrer_key=ref.key, invited_key=invited_key, confirmed=not pending))
    db.flush()
    if pending:
        return [{"type": "notify_customer", "cust": ref.key, "text": "👋 یک نفر با لینک اختصاصی شما وارد شد. وقتی اولین سفارش یا نوبتش را ثبت کند، دعوت برای شما حساب می‌شود."}]
    return _counted(db, bot_id, ref.key, block)


DONE = {"confirmed", "new", "preparing", "ready", "done", "transfer_sent"}  # a real booking or order (not cancelled, not unpaid)


def confirm_pending(db: Session, bot_id: int, invited_key: str, spec, block) -> list[dict]:
    """After a turn: a friend whose invite was waiting has now booked or ordered → the invite counts."""
    if block is None or block.count_after != "order":
        return []
    join = db.scalars(select(ReferralJoin).where(ReferralJoin.bot_id == bot_id, ReferralJoin.invited_key == invited_key,
                                                 ReferralJoin.confirmed.is_(False))).first()
    if join is None:
        return []
    ids = [b.id for b in spec.blocks if b.type in ("booking", "catalog_order")]
    rows = db.scalars(select(Record).where(Record.bot_id == bot_id, Record.sandbox.is_(False), Record.collection.in_(ids or [""]))).all()
    if not any(r.data.get("_cust") == invited_key and r.data.get("status") in DONE for r in rows):
        return []
    join.confirmed = True
    db.flush()
    return _counted(db, bot_id, join.referrer_key, block, ordered=True)


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
