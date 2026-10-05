"""Anonymous chat between two customers of the same bot (any mix of Bale and Telegram customers).

The engine only says WHAT should happen (anon_find / anon_relay / anon_end / anon_report); this module pairs people, relays text
and keeps the safety rules:
- nobody ever sees the other person's name, id or messenger; messages are relayed as «👤 ناشناس»
- text only, at most 500 characters; links, @ids and phone numbers are NOT passed on; at most 20 messages a minute
- either person can end the chat, ask for the next partner, or report the other (the owner gets the last 8 messages as evidence,
  nothing else is kept, and the log is erased when a chat ends normally)
- the owner can ban a customer (BannedCustomer): banned customers cannot use the bot at all"""
from __future__ import annotations

import copy
import re
import time as _time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import engine
from .models import AnonPair, AnonQueue, ChatSession, CustomerSeen
from .store import SqlStore

WAIT_MINUTES = 10
LOG_KEEP = 8
RATE = 20  # messages per minute per person
LINKISH = re.compile(r"(https?://|www\.|\b(?:t\.me|ble\.ir)/|@[A-Za-z0-9_]{4,}|\b[\w-]+\.(?:com|ir|net|org|me|io)\b|(?<!\d)(?:\+?98|0)?9[\s-]?\d{2}[\s-]?\d{3}[\s-]?\d{4}(?!\d))", re.I)
_hits: dict[str, deque] = defaultdict(deque)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _active_pair(db: Session, bot_id: int, key: str) -> AnonPair | None:
    return db.scalars(select(AnonPair).where(AnonPair.bot_id == bot_id, AnonPair.active.is_(True), (AnonPair.a_key == key) | (AnonPair.b_key == key))).first()


def _partner(pair: AnonPair, key: str) -> str:
    return pair.b_key if pair.a_key == key else pair.a_key


def _set_partner_step(db: Session, bot_id: int, key: str, block_id: str, step: str):
    row = db.scalars(select(ChatSession).where(ChatSession.bot_id == bot_id, ChatSession.key == key)).first()
    if row is None:
        return
    st = copy.deepcopy(row.state)
    if step == "chat":
        st.update(block=block_id, step="chat", data={})
    elif st.get("block") == block_id:
        st.update(step="idle")
    row.state = st


def _buttons_after_end():
    return [{"text": "🔍 جستجوی شریک جدید", "data": "ac:find"}, {"text": "بازگشت به منو", "data": "/menu"}]


def _end(db: Session, bot_id: int, key: str, block_id: str, notify: bool = True) -> list[dict]:
    """Close my active pair (if any) and leave the queue. Returns the message for the partner."""
    for q in db.scalars(select(AnonQueue).where(AnonQueue.bot_id == bot_id, AnonQueue.key == key)).all():
        db.delete(q)
    pair = _active_pair(db, bot_id, key)
    out = []
    if pair is not None:
        other = _partner(pair, key)
        block_id = block_id or pair.block_id
        pair.active, pair.log = False, []
        _set_partner_step(db, bot_id, other, block_id, "idle")
        if notify:
            out.append({"type": "notify_customer", "cust": other, "text": "شریک گفتگو، گفتگو را پایان داد.", "buttons": _buttons_after_end()})
    return out


def run(db: Session, bot, spec, state: dict, key: str, actions: list[dict]) -> tuple[list[dict], list[dict]]:
    """Execute the anon_* actions of one turn. Returns (actions to deliver to THIS customer, messages for OTHER customers)."""
    mine: list[dict] = []
    others: list[dict] = []
    keep: list[dict] = []
    for a in actions:
        kind = a["type"]
        if not kind.startswith("anon_"):
            keep.append(a)
            continue
        block_id = a["block"]
        if kind == "anon_find":
            others += _end(db, bot.id, key, block_id, notify=False)
            cutoff = _now() - timedelta(minutes=WAIT_MINUTES)
            waiting = [q for q in db.scalars(select(AnonQueue).where(AnonQueue.bot_id == bot.id, AnonQueue.block_id == block_id).order_by(AnonQueue.id)).all()
                       if q.key != key and (q.created_at if q.created_at.tzinfo else q.created_at.replace(tzinfo=timezone.utc)) >= cutoff]
            if waiting:
                partner = waiting[0]
                db.delete(partner)
                db.add(AnonPair(bot_id=bot.id, block_id=block_id, a_key=partner.key, b_key=key, log=[]))
                _set_partner_step(db, bot.id, partner.key, block_id, "chat")
                hello = "✅ شریک گفتگو پیدا شد! بنویسید؛ پیام‌ها ناشناس ارسال می‌شود (لینک و شماره تلفن ارسال نمی‌شود)."
                mine.append(engine.send(hello, engine._anon_buttons()))
                others.append({"type": "notify_customer", "cust": partner.key, "text": hello, "buttons": engine._anon_buttons()})
                state["step"] = "chat"
            else:
                db.add(AnonQueue(bot_id=bot.id, block_id=block_id, key=key))
        elif kind == "anon_end":
            others += _end(db, bot.id, key, block_id)
        elif kind == "anon_report":
            pair = _active_pair(db, bot.id, key)
            if pair is not None:
                other = _partner(pair, key)
                seen = db.scalars(select(CustomerSeen).where(CustomerSeen.bot_id == bot.id, CustomerSeen.key == other)).first()
                lines = [{"from": "گزارش‌دهنده" if l["from"] == key else "طرف مقابل", "text": l["text"]} for l in (pair.log or [])]
                SqlStore(db, bot.id, sandbox=False).add(block_id, {"status": "reported", "who": "گزارش گفتگوی ناشناس", "log": lines,
                                                                   "reported_id": seen.id if seen else None, "reported_name": (seen.name if seen else "") or "—"})
                mine.append({"type": "notify_admin", "text": "🚨 یک گفتگوی ناشناس گزارش شد؛ جزئیات در بخش «ثبت‌ها» است."})
            others += _end(db, bot.id, key, block_id)
        elif kind == "anon_relay":
            pair = _active_pair(db, bot.id, key)
            text = a["text"]
            if pair is None:
                state["step"] = "idle"
                mine.append(engine.send("شما الان در گفتگو نیستید.", [{"text": "🔍 پیدا کردن شریک گفتگو", "data": "ac:find"}, {"text": "بازگشت به منو", "data": "/menu"}]))
            elif not text:
                continue
            elif LINKISH.search(text):
                mine.append(engine.send("ارسال لینک، آی‌دی و شماره تلفن در گفتگوی ناشناس مجاز نیست؛ پیام شما ارسال نشد."))
            else:
                now = _time.time()
                q = _hits[key]
                while q and now - q[0] > 60:
                    q.popleft()
                if len(q) >= RATE:
                    mine.append(engine.send("خیلی سریع پیام می‌فرستید؛ کمی صبر کنید."))
                    continue
                q.append(now)
                pair.log = ([*(pair.log or []), {"from": key, "text": text}])[-LOG_KEEP:]
                others.append({"type": "notify_customer", "cust": _partner(pair, key), "text": "👤 " + text})
    return [*keep, *mine], others


def expire_waiting(db: Session, now: datetime) -> list[dict]:
    """Drop people who waited too long for a partner; returns the messages telling them."""
    cutoff = now - timedelta(minutes=WAIT_MINUTES)
    out = []
    for q in db.scalars(select(AnonQueue)).all():
        created = q.created_at if q.created_at.tzinfo else q.created_at.replace(tzinfo=timezone.utc)
        if created < cutoff:
            _set_partner_step(db, q.bot_id, q.key, q.block_id, "idle")
            out.append((q.bot_id, {"type": "notify_customer", "cust": q.key, "text": "فعلاً کسی برای گفتگو پیدا نشد. بعداً دوباره امتحان کنید.", "buttons": _buttons_after_end()}))
            db.delete(q)
    return out
