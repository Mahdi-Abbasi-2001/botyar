"""Messages that could not be sent because the messenger was unreachable are kept and retried (see resilience.py for what counts as
"unreachable"). Only plain text messages are queued: edits, files and invoices are tied to a moment that has passed."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import OutboxMessage
from .resilience import BaleError, TransientError, UncertainError

log = logging.getLogger("botyar.outbox")
QUEUEABLE = {"sendMessage"}
MAX_ATTEMPTS = 5
GIVE_UP = timedelta(minutes=30)
BACKOFF_MIN = (1, 2, 4, 8, 15)
PENDING_CAP = 500  # per bot: a long outage must not fill the database


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _enqueue(db: Session, ch, payload: dict, bot_id: int, error: str) -> bool:
    pending = db.scalar(select(func.count()).select_from(OutboxMessage).where(OutboxMessage.bot_id == bot_id, OutboxMessage.status == "pending")) or 0
    if pending >= PENDING_CAP:
        return False
    now = datetime.now(timezone.utc)
    db.add(OutboxMessage(bot_id=bot_id, ch=ch.name, chat_id=str(payload.get("chat_id", "")), payload=payload, next_try=now + timedelta(minutes=BACKOFF_MIN[0]), last_error=error[:200]))
    db.flush()
    return True


def send(ch, token: str, method: str, payload: dict, bot_id: int | None, db: Session | None = None) -> bool:
    """Send now; if the messenger is unreachable queue the message instead. True = delivered, False = queued. Other errors propagate.
    Pass the caller's `db` when it has an open transaction (the row then commits with it; a second session would block on SQLite)."""
    try:
        ch.call(token, method, payload)
        return True
    except TransientError as e:
        if bot_id is None or method not in QUEUEABLE or len(json.dumps(payload, ensure_ascii=False)) > 20_000:
            raise
        if db is not None:
            queued = _enqueue(db, ch, payload, bot_id, str(e))
        else:
            with SessionLocal() as own:
                queued = _enqueue(own, ch, payload, bot_id, str(e))
                own.commit()
        if not queued:
            raise
        log.warning("message queued for later (%s)", e)
        return False


def process(db: Session, now: datetime | None = None) -> dict:
    """Retry due messages. Order per chat is kept; once a messenger fails in this round its other messages wait for the next round."""
    from . import bale, communities  # lazy: bale imports this module

    now = now or datetime.now(timezone.utc)
    out = {"sent": 0, "failed": 0, "retry": 0}
    rows = db.scalars(select(OutboxMessage).where(OutboxMessage.status == "pending", OutboxMessage.next_try <= now).order_by(OutboxMessage.id).limit(100)).all()
    blocked_chats: set[tuple] = set()
    down: set[str] = set()
    for r in rows:
        key = (r.bot_id, r.ch, r.chat_id)
        if key in blocked_chats or r.ch in down:
            continue
        ch = bale.CHANNELS.get(r.ch)
        token = communities._token_for(db, ch, r.bot_id) if ch else None
        if not token:
            r.status, r.last_error, r.done_at = "failed", "ربات دیگر روی این پیام‌رسان منتشر نیست", now
            out["failed"] += 1
            db.commit()
            continue
        try:
            ch.call(token, "sendMessage", r.payload)
            r.status, r.done_at, r.last_error = "sent", now, ""
            out["sent"] += 1
        except TransientError as e:
            r.attempts += 1
            r.last_error = str(e)[:200]
            if r.attempts >= MAX_ATTEMPTS or now - _aware(r.created_at) > GIVE_UP:
                r.status, r.done_at = "failed", now
                out["failed"] += 1
            else:
                r.next_try = now + timedelta(minutes=BACKOFF_MIN[min(r.attempts, len(BACKOFF_MIN) - 1)])
                out["retry"] += 1
            blocked_chats.add(key)
            down.add(r.ch)  # the messenger is still unreachable: do not hammer it with the rest of the queue
        except (UncertainError, BaleError) as e:  # a "no" or an unknown outcome: never resend
            r.status, r.last_error, r.done_at = "failed", str(e)[:200], now
            out["failed"] += 1
        db.commit()
    return out


def stats(db: Session, bot_id: int) -> dict:
    day = datetime.now(timezone.utc) - timedelta(hours=24)
    rows = db.execute(select(OutboxMessage.status, func.count()).where(OutboxMessage.bot_id == bot_id, OutboxMessage.created_at >= day).group_by(OutboxMessage.status)).all()
    d = {s: n for s, n in rows}
    pending = db.scalar(select(func.count()).select_from(OutboxMessage).where(OutboxMessage.bot_id == bot_id, OutboxMessage.status == "pending")) or 0
    return {"pending": pending, "sent_24h": d.get("sent", 0), "failed_24h": d.get("failed", 0)}


def purge(db: Session, now: datetime | None = None) -> int:
    """Forget finished entries after 3 days so the table stays small."""
    now = now or datetime.now(timezone.utc)
    n = 0
    for r in db.scalars(select(OutboxMessage).where(OutboxMessage.status != "pending", OutboxMessage.done_at < now - timedelta(days=3))).all():
        db.delete(r)
        n += 1
    db.commit()
    return n
