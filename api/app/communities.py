"""Channel, group and join-gate features that need the bot inside a channel or group: forced join, post forwarding, group moderation.

Which business a group/channel belongs to is decided by the OWNER: an admin posts `/link <admin code>` in the chat (the code is the
one shown in the Publish tab, so only the owner has it). Nothing is bound without it."""
from __future__ import annotations

import logging
import re
import secrets
import time as _time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import bale, gate
from .auth import current_user
from .db import get_db
from .engine_text import fa_norm
from .models import Bot, BotVersion, ChatBinding, ForwardRule, GroupRule, GroupWarning, LinkToken, User
from .spec import BotSpec

log = logging.getLogger("botyar.communities")
LINK_TTL = timedelta(minutes=15)
MAX_BINDINGS = 10
ADMIN_STATUS = {"administrator", "creator", "owner"}
URL_RE = re.compile(r"(https?://|www\.|\b(?:t\.me|ble\.ir|telegram\.me|eitaa\.com|rubika\.ir|instagram\.com)/|@[A-Za-z0-9_]{5,}|\b[\w-]+\.(?:com|ir|net|org|me|io|info)\b)", re.I)
_admin_cache: dict[tuple[str, str], tuple[float, bool]] = {}

router = APIRouter()


def own_bot(bot_id: int, user: User, db: Session) -> Bot:
    bot = db.get(Bot, bot_id)
    if not bot or bot.user_id != user.id:
        raise HTTPException(404, "ربات یافت نشد")
    return bot


def latest_spec(bot_id: int, db: Session) -> BotSpec | None:
    ver = db.scalars(select(BotVersion).where(BotVersion.bot_id == bot_id).order_by(BotVersion.version.desc())).first()
    return BotSpec.model_validate(ver.spec) if ver else None


@router.get("/api/bots/{bot_id}/gate")
def gate_status(bot_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    own_bot(bot_id, user, db)
    spec = latest_spec(bot_id, db)
    if spec is None or spec.gate is None:
        return {"configured": False, "messengers": []}
    out = []
    for ch in bale.CHANNELS.values():
        pub = db.scalars(select(ch.pub_model).where(ch.pub_model.bot_id == bot_id)).first()
        if pub is None:
            continue
        try:
            token = bale.pub_token(ch, pub)
        except Exception:  # noqa: BLE001
            continue
        out.append({"messenger": ch.name, **gate.setup_status(ch, token, spec)})
    return {"configured": True, "channel": spec.gate.channel, "messengers": out}


# ---------- panel API: linking, forwarding, moderation ----------
def _bindings(db: Session, bot_id: int) -> list[ChatBinding]:
    return db.scalars(select(ChatBinding).where(ChatBinding.bot_id == bot_id).order_by(ChatBinding.id)).all()


def _rule_out(r: GroupRule) -> dict:
    return {"delete_links": r.delete_links, "delete_forwards": r.delete_forwards, "banned_words": r.banned_words or [],
            "max_warnings": r.max_warnings, "welcome_text": r.welcome_text, "deleted": r.deleted, "banned": r.banned}


@router.post("/api/bots/{bot_id}/link-token")
def make_link_token(bot_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    own_bot(bot_id, user, db)
    if len(_bindings(db, bot_id)) >= MAX_BINDINGS:
        raise HTTPException(409, f"حداکثر {MAX_BINDINGS} کانال و گروه می‌توانید وصل کنید.")
    code = "".join(secrets.choice("ABCDEFGHJKMNPQRSTUVWXYZ23456789") for _ in range(8))
    db.add(LinkToken(bot_id=bot_id, code=code, expires_at=datetime.now(timezone.utc) + LINK_TTL))
    db.commit()
    return {"code": code, "command": f"/link {code}", "expires_minutes": int(LINK_TTL.total_seconds() // 60)}


@router.get("/api/bots/{bot_id}/chats")
def list_chats(bot_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    own_bot(bot_id, user, db)
    binds = _bindings(db, bot_id)
    rules = {r.binding_id: r for r in db.scalars(select(GroupRule).where(GroupRule.binding_id.in_([b.id for b in binds] or [0])))}
    fwd = db.scalars(select(ForwardRule).where(ForwardRule.bot_id == bot_id).order_by(ForwardRule.id)).all()
    return {"chats": [{"id": b.id, "messenger": b.ch, "kind": b.kind, "title": b.title or "—", "rule": _rule_out(rules[b.id]) if b.id in rules else None} for b in binds],
            "forwards": [{"id": f.id, "source": f.source_id, "dest": f.dest_id, "active": f.active, "forwarded": f.forwarded, "last_error": f.last_error} for f in fwd]}


@router.delete("/api/bots/{bot_id}/chats/{binding_id}")
def unlink_chat(bot_id: int, binding_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    own_bot(bot_id, user, db)
    b = db.get(ChatBinding, binding_id)
    if b is None or b.bot_id != bot_id:
        raise HTTPException(404, "یافت نشد")
    for f in db.scalars(select(ForwardRule).where((ForwardRule.source_id == b.id) | (ForwardRule.dest_id == b.id))).all():
        db.delete(f)
    for r in db.scalars(select(GroupRule).where(GroupRule.binding_id == b.id)).all():
        db.delete(r)
    for w in db.scalars(select(GroupWarning).where(GroupWarning.binding_id == b.id)).all():
        db.delete(w)
    db.delete(b)
    db.commit()
    return {"ok": True}


class ForwardIn(BaseModel):
    source: int
    dest: int


def _reaches(db: Session, bot_id: int, start: int, goal: int) -> bool:
    """Would posts starting at `start` already reach `goal`? (used to refuse rules that would copy posts back and forth forever)"""
    seen, stack = set(), [start]
    while stack:
        cur = stack.pop()
        if cur == goal:
            return True
        if cur in seen:
            continue
        seen.add(cur)
        stack += [f.dest_id for f in db.scalars(select(ForwardRule).where(ForwardRule.bot_id == bot_id, ForwardRule.source_id == cur, ForwardRule.active.is_(True)))]
    return False


@router.post("/api/bots/{bot_id}/forwards")
def add_forward(bot_id: int, body: ForwardIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    own_bot(bot_id, user, db)
    src, dst = db.get(ChatBinding, body.source), db.get(ChatBinding, body.dest)
    if not src or not dst or src.bot_id != bot_id or dst.bot_id != bot_id:
        raise HTTPException(404, "کانال یا گروه یافت نشد")
    if src.kind != "channel":
        raise HTTPException(422, "مبدأ باید یک کانال باشد")
    if src.id == dst.id:
        raise HTTPException(422, "مبدأ و مقصد یکی است")
    if db.scalars(select(ForwardRule).where(ForwardRule.source_id == src.id, ForwardRule.dest_id == dst.id)).first():
        raise HTTPException(409, "این انتقال قبلاً تعریف شده است")
    if _reaches(db, bot_id, dst.id, src.id):
        raise HTTPException(422, "این انتقال یک حلقه می‌سازد (پست‌ها برای همیشه بین کانال‌ها می‌چرخند)")
    r = ForwardRule(bot_id=bot_id, source_id=src.id, dest_id=dst.id)
    db.add(r)
    db.commit()
    return {"id": r.id}


@router.delete("/api/bots/{bot_id}/forwards/{rid}")
def delete_forward(bot_id: int, rid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    own_bot(bot_id, user, db)
    r = db.get(ForwardRule, rid)
    if r is None or r.bot_id != bot_id:
        raise HTTPException(404, "یافت نشد")
    db.delete(r)
    db.commit()
    return {"ok": True}


class ModerationIn(BaseModel):
    delete_links: bool = True
    delete_forwards: bool = False
    banned_words: list[str] = Field(default_factory=list, max_length=50)
    max_warnings: int = Field(default=3, ge=0, le=20)
    welcome_text: str = Field(default="", max_length=500)


@router.put("/api/bots/{bot_id}/chats/{binding_id}/moderation")
def set_moderation(bot_id: int, binding_id: int, body: ModerationIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    own_bot(bot_id, user, db)
    b = db.get(ChatBinding, binding_id)
    if b is None or b.bot_id != bot_id:
        raise HTTPException(404, "یافت نشد")
    if b.kind != "group":
        raise HTTPException(422, "مدیریت پیام فقط برای گروه است")
    words = [w.strip()[:40] for w in body.banned_words if w.strip()]
    r = db.scalars(select(GroupRule).where(GroupRule.binding_id == b.id)).first()
    if r is None:
        r = GroupRule(binding_id=b.id)
        db.add(r)
    r.delete_links, r.delete_forwards, r.banned_words = body.delete_links, body.delete_forwards, words
    r.max_warnings, r.welcome_text = body.max_warnings, body.welcome_text.strip()
    db.commit()
    return _rule_out(r)


# ---------- updates from groups and channels (called by the messenger adapter) ----------
def _token_for(db: Session, ch, bot_id: int) -> str | None:
    pub = db.scalars(select(ch.pub_model).where(ch.pub_model.bot_id == bot_id)).first()
    try:
        return bale.pub_token(ch, pub) if pub else None
    except Exception:  # noqa: BLE001
        return None


def _is_admin(ch, token: str, chat_id: str, uid) -> bool:
    key = (f"{ch.name}:{chat_id}", str(uid))
    hit = _admin_cache.get(key)
    if hit and _time.time() - hit[0] < 120:
        return hit[1]
    try:
        ok = (ch.call(token, "getChatMember", {"chat_id": chat_id, "user_id": uid}) or {}).get("status") in ADMIN_STATUS
    except Exception:  # noqa: BLE001
        ok = False  # cannot tell: treat as a normal member (never exempt someone by mistake)
    _admin_cache[key] = (_time.time(), ok)
    return ok


def _say(ch, token: str, chat_id: str, text: str):
    try:
        ch.call(token, "sendMessage", {"chat_id": chat_id, "text": text[:4096]})
    except Exception as e:  # noqa: BLE001
        log.warning("group message failed: %s", e)


def handle_update(db: Session, ch, kind: str, own_pub, update: dict, token: str) -> None:
    """A message in a group/supergroup or a channel post (never a private chat). Unlinked chats are ignored."""
    is_post = "channel_post" in update
    msg = update.get("channel_post") or update.get("message")
    if not msg:
        return
    chat = msg.get("chat") or {}
    chat_id = str(chat.get("id", ""))
    if not chat_id:
        return
    text = (msg.get("text") or msg.get("caption") or "").strip()
    if text.lower().startswith("/link"):
        return _link(db, ch, own_pub, token, msg, chat, chat_id, "channel" if is_post or chat.get("type") == "channel" else "group", text)
    b = db.scalars(select(ChatBinding).where(ChatBinding.ch == ch.name, ChatBinding.chat_id == chat_id)).first()
    if b is None:
        return
    if b.kind == "channel":
        _forward(db, ch, token, b, msg)
    else:
        _moderate(db, ch, token, b, msg, text)


def _link(db, ch, own_pub, token, msg, chat, chat_id, kind, text):
    parts = text.split()
    row = db.scalars(select(LinkToken).where(LinkToken.code == (parts[1].upper() if len(parts) > 1 else "-"))).first() if len(parts) > 1 else None
    exp = row.expires_at if row and row.expires_at.tzinfo else (row.expires_at.replace(tzinfo=timezone.utc) if row else None)
    if row is None or row.used or exp < datetime.now(timezone.utc) or (own_pub is not None and own_pub.bot_id != row.bot_id):
        _say(ch, token, chat_id, "❌ کد اتصال نامعتبر یا منقضی است. در بات‌یار کد جدید بگیرید.")
        return
    sender = msg.get("from") or {}
    if kind == "group" and sender.get("id") is not None and not _is_admin(ch, token, chat_id, sender["id"]):
        _say(ch, token, chat_id, "❌ فقط مدیر گروه می‌تواند گروه را وصل کند.")
        return
    b = db.scalars(select(ChatBinding).where(ChatBinding.ch == ch.name, ChatBinding.chat_id == chat_id)).first()
    if b is not None and b.bot_id != row.bot_id:
        _say(ch, token, chat_id, "❌ این گفتگو قبلاً به ربات دیگری وصل شده است.")
        return
    if b is None:
        b = ChatBinding(bot_id=row.bot_id, ch=ch.name, chat_id=chat_id, kind=kind, title=(chat.get("title") or "")[:120])
        db.add(b)
        db.flush()
        if kind == "group":
            db.add(GroupRule(binding_id=b.id))
    row.used = True
    db.commit()
    try:  # the code must not stay visible in the chat
        ch.call(token, "deleteMessage", {"chat_id": chat_id, "message_id": msg.get("message_id")})
    except Exception:  # noqa: BLE001
        pass
    _say(ch, token, chat_id, "✅ این " + ("کانال" if kind == "channel" else "گروه") + " به ربات شما در بات‌یار وصل شد؛ تنظیمات را از پنل بات‌یار ببینید.")


def _forward(db, ch, token, src: ChatBinding, msg):
    for r in db.scalars(select(ForwardRule).where(ForwardRule.source_id == src.id, ForwardRule.active.is_(True))).all():
        dst = db.get(ChatBinding, r.dest_id)
        if dst is None:
            continue
        try:
            if dst.ch == ch.name:
                ch.call(token, "copyMessage", {"chat_id": dst.chat_id, "from_chat_id": src.chat_id, "message_id": msg.get("message_id")})
            else:  # between Bale and Telegram only the text can travel (the media would have to be downloaded and re-uploaded)
                text = (msg.get("text") or msg.get("caption") or "").strip()
                if not text:
                    r.last_error = "پست بدون متن بین بله و تلگرام منتقل نمی‌شود"
                    continue
                other = bale.CHANNELS[dst.ch]
                tok = _token_for(db, other, r.bot_id)
                if not tok:
                    r.last_error = "ربات در پیام‌رسان مقصد منتشر نشده است"
                    continue
                other.call(tok, "sendMessage", {"chat_id": dst.chat_id, "text": text[:4096]})
            r.forwarded += 1
            r.last_error = ""
        except Exception as e:  # noqa: BLE001
            r.last_error = str(e)[:190]
            log.warning("forward failed: %s", e)
    db.commit()


def _moderate(db, ch, token, b: ChatBinding, msg, text: str):
    rule = db.scalars(select(GroupRule).where(GroupRule.binding_id == b.id)).first()
    if rule is None:
        return
    chat_id = b.chat_id
    joined = msg.get("new_chat_members") or []
    if joined and rule.welcome_text:
        names = "، ".join((u.get("first_name") or "دوست عزیز") for u in joined if not u.get("is_bot"))
        if names:
            _say(ch, token, chat_id, rule.welcome_text.replace("{name}", names))
        return
    sender = msg.get("from") or {}
    uid = sender.get("id")
    if uid is None or sender.get("is_bot"):
        return
    cmd = text.split()[0].lower() if text.startswith("/") else ""
    reply = msg.get("reply_to_message") or {}
    target = (reply.get("from") or {}).get("id")
    if cmd in ("/ban", "/unban", "/warns") and _is_admin(ch, token, chat_id, uid):
        if target is None:
            _say(ch, token, chat_id, "این دستور را روی پیام فرد مورد نظر «ریپلای» کنید.")
            return
        if cmd == "/ban":
            _ban(ch, token, chat_id, target)
            rule.banned += 1
            _say(ch, token, chat_id, "🚫 کاربر حذف شد.")
        elif cmd == "/unban":
            try:
                ch.call(token, "unbanChatMember", {"chat_id": chat_id, "user_id": target, "only_if_banned": True})
                w = db.scalars(select(GroupWarning).where(GroupWarning.binding_id == b.id, GroupWarning.user_id == str(target))).first()
                if w:
                    w.count = 0
                _say(ch, token, chat_id, "✅ کاربر آزاد شد.")
            except Exception as e:  # noqa: BLE001
                _say(ch, token, chat_id, f"آزاد کردن ممکن نشد: {str(e)[:80]}")
        else:
            w = db.scalars(select(GroupWarning).where(GroupWarning.binding_id == b.id, GroupWarning.user_id == str(target))).first()
            _say(ch, token, chat_id, f"اخطارهای این کاربر: {w.count if w else 0}")
        db.commit()
        return
    reason = None
    low = fa_norm(text)
    if rule.delete_links and URL_RE.search(text):
        reason = "link"
    elif rule.delete_forwards and (msg.get("forward_date") or msg.get("forward_from") or msg.get("forward_from_chat")):
        reason = "forward"
    elif any(fa_norm(w) and fa_norm(w) in low for w in (rule.banned_words or [])):
        reason = "word"
    if reason is None or _is_admin(ch, token, chat_id, uid):  # admins are never moderated
        return
    try:
        ch.call(token, "deleteMessage", {"chat_id": chat_id, "message_id": msg.get("message_id")})
        rule.deleted += 1
    except Exception as e:  # noqa: BLE001
        log.warning("delete failed (is the bot an admin? message older than 48h?): %s", e)
    w = db.scalars(select(GroupWarning).where(GroupWarning.binding_id == b.id, GroupWarning.user_id == str(uid))).first()
    if w is None:
        w = GroupWarning(binding_id=b.id, user_id=str(uid), count=0)
        db.add(w)
    w.count += 1
    if rule.max_warnings and w.count >= rule.max_warnings:
        if _ban(ch, token, chat_id, uid):
            rule.banned += 1
            _say(ch, token, chat_id, f"🚫 {sender.get('first_name') or 'کاربر'} به‌دلیل رعایت‌نکردن قوانین گروه حذف شد.")
        w.count = 0
    db.commit()


def _ban(ch, token, chat_id, uid) -> bool:
    try:
        ch.call(token, "banChatMember", {"chat_id": chat_id, "user_id": uid})
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("ban failed: %s", e)
        return False


# ---------- delivery status for the owner's panel ----------
@router.get("/api/bots/{bot_id}/delivery")
def delivery_status(bot_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Is each messenger this bot is published on reachable right now, and what is waiting to be re-sent?"""
    from . import outbox, resilience

    own_bot(bot_id, user, db)
    names = [ch.name for ch in bale.CHANNELS.values() if db.scalars(select(ch.pub_model).where(ch.pub_model.bot_id == bot_id)).first()]
    return {"messengers": [resilience.health(n) for n in names], "outbox": outbox.stats(db, bot_id)}
