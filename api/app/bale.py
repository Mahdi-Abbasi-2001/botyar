"""Bale adapter: thin HTTP client + the glue that feeds Bale updates to the deterministic engine.

Facts from docs.bale.ai (verified 2026-10-04): Telegram-style Bot API at tapi.bale.ai; no webhook secret
(so our webhook URLs carry an unguessable secret); callback_data max 64 bytes; answerCallbackQuery is
mandatory after a button press; webhook ports 443/88; /start parameters are not documented."""
from __future__ import annotations

import copy

import base64
import hashlib
import hmac
import logging
import re
import secrets
import threading
from collections import defaultdict

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import engine
from .config import settings
from .db import SessionLocal
from .models import BotVersion, ChatLink, ChatSession, Publication
from .spec import BotSpec
from .store import SqlStore

log = logging.getLogger("botyar.bale")
API = "https://tapi.bale.ai"
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O/1/I confusion


class BaleError(Exception):
    pass


def api_call(token: str, method: str, payload: dict | None = None, timeout: float = 15):
    r = httpx.post(f"{API}/bot{token}/{method}", json=payload or {}, timeout=timeout)
    try:
        d = r.json()
    except Exception:
        raise BaleError(f"HTTP {r.status_code}")
    if not d.get("ok"):
        raise BaleError(d.get("description") or f"HTTP {r.status_code}")
    return d.get("result")


# ---------- secrets ----------
def _fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(settings.jwt_secret.encode()).digest()))


def encrypt(s: str) -> str:
    return _fernet().encrypt(s.encode()).decode()


def decrypt(s: str) -> str:
    try:
        return _fernet().decrypt(s.encode()).decode()
    except InvalidToken:
        raise BaleError("token cannot be decrypted (JWT_SECRET changed?)")


def new_code(n: int) -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(n))


def shared_hook_secret() -> str:
    return hmac.new(settings.jwt_secret.encode(), b"bale-shared-hook", hashlib.sha256).hexdigest()[:32]


_username_cache: dict[str, str] = {}


def shared_username() -> str:
    t = settings.bale_shared_bot_token
    if not t:
        return ""
    if t not in _username_cache:
        try:
            _username_cache[t] = api_call(t, "getMe").get("username", "")
        except Exception as e:  # noqa: BLE001
            log.warning("getMe failed: %s", e)
            return ""
    return _username_cache[t]


def ensure_shared_webhook():
    """Register the shared bot's webhook. Only when PUBLIC_BASE_URL is set (production), never from local dev."""
    if not (settings.bale_shared_bot_token and settings.public_base_url):
        return
    url = f"{settings.public_base_url.rstrip('/')}/api/hook/shared/{shared_hook_secret()}"
    try:
        api_call(settings.bale_shared_bot_token, "setWebhook", {"url": url})
        log.info("shared webhook registered")
    except Exception as e:  # noqa: BLE001
        log.warning("setWebhook failed: %s", e)


# ---------- sending ----------
def to_markup(buttons: list[dict], cb: dict) -> dict:
    """One button per row. callback_data over 64 bytes (long Persian labels) is replaced by a short token."""
    rows = []
    for b in buttons:
        data = b["data"]
        if len(data.encode()) > 64:
            key = f"~{len(cb)}"
            cb[key] = data
            data = key
        rows.append([{"text": engine.fa_digits(b["text"]), "callback_data": data}])
    return {"inline_keyboard": rows}


def deliver(token: str, chat_id: str, actions: list[dict], session: dict, admin_chat_id: str = "", edit_message_id: int | None = None):
    cb: dict = {}
    for n, a in enumerate(actions):
        try:
            if a["type"] == "send" and n == 0 and a.get("edit") and edit_message_id:
                # in-place navigation (e.g. next page): edit the clicked message; fall back to a new message if Bale refuses
                payload = {"chat_id": chat_id, "message_id": edit_message_id, "text": engine.fa_digits(a["text"])[:4096] or "…"}
                if a.get("buttons"):
                    payload["reply_markup"] = to_markup(a["buttons"], cb)
                try:
                    api_call(token, "editMessageText", payload)
                    continue
                except Exception as e:  # noqa: BLE001
                    log.warning("edit failed, sending a new message: %s", e)
                    payload.pop("message_id")
                    api_call(token, "sendMessage", payload)
                    continue
            if a["type"] == "send":
                payload = {"chat_id": chat_id, "text": engine.fa_digits(a["text"])[:4096] or "…"}
                if a.get("buttons"):
                    payload["reply_markup"] = to_markup(a["buttons"], cb)
                api_call(token, "sendMessage", payload)
            elif a["type"] == "notify_admin" and admin_chat_id:
                api_call(token, "sendMessage", {"chat_id": admin_chat_id, "text": ("🔔 " + a["text"])[:4096]})
        except Exception as e:  # noqa: BLE001
            log.warning("send failed: %s", e)
    session["_cb"] = cb


def say(token: str, chat_id: str, text: str):
    try:
        api_call(token, "sendMessage", {"chat_id": chat_id, "text": text})
    except Exception as e:  # noqa: BLE001
        log.warning("send failed: %s", e)


# ---------- update handling ----------
_locks: dict[int, threading.Lock] = defaultdict(threading.Lock)  # serialise a bot's bookings (capacity checks)
_seen: dict[str, int] = {}


def process_update(kind: str, pub_id: int | None, update: dict):
    db = SessionLocal()
    try:
        _process(db, kind, pub_id, update)
    except Exception:  # noqa: BLE001
        log.exception("update failed")
        db.rollback()
    finally:
        db.close()


def _process(db: Session, kind: str, pub_id: int | None, update: dict):
    key = f"{kind}:{pub_id}"
    uid = update.get("update_id")
    if isinstance(uid, int):
        if uid <= _seen.get(key, -1):
            return  # Bale retried a delivery we already handled
        _seen[key] = uid

    own_pub = db.get(Publication, pub_id) if kind == "own" else None
    if kind == "own" and own_pub is None:
        return
    token = settings.bale_shared_bot_token if kind == "shared" else decrypt(own_pub.token_enc)

    cq, msg = update.get("callback_query"), update.get("message")
    if cq:
        chat = (cq.get("message") or {}).get("chat", {}).get("id") or (cq.get("from") or {}).get("id")
        text, cq_id = cq.get("data") or "", cq.get("id")
    elif msg:
        if (msg.get("chat") or {}).get("type", "private") != "private":
            return
        chat, text, cq_id = msg["chat"]["id"], msg.get("text"), None
    else:
        return
    if chat is None:
        return
    chat_id = str(chat)
    clicked_message_id = ((cq or {}).get("message") or {}).get("message_id") if cq else None
    if cq_id:  # mandatory per Bale docs
        try:
            api_call(token, "answerCallbackQuery", {"callback_query_id": cq_id})
        except Exception as e:  # noqa: BLE001
            log.warning("answerCallbackQuery failed: %s", e)
    if not text:
        say(token, chat_id, "لطفاً فقط پیام متنی بفرستید یا از دکمه‌ها استفاده کنید.")
        return
    t = engine.norm(text)

    # owner links their chat to receive notifications
    if t.startswith("/admin"):
        code = t[6:].strip().upper()
        q = select(Publication).where(Publication.admin_code == code)
        target = db.scalars(q).first() if code else None
        if target is None or (own_pub is not None and target.id != own_pub.id):
            say(token, chat_id, "کد مدیر نامعتبر است. کد را از صفحه‌ی «انتشار» در بات‌یار کپی کنید: /admin CODE")
        else:
            target.admin_chat_id = chat_id
            db.commit()
            say(token, chat_id, "✅ انجام شد. از این به بعد ثبت‌های جدید همین‌جا برای شما ارسال می‌شود.")
        return

    pub = own_pub
    welcome_now = False
    if kind == "shared":
        cand = t[6:].strip() if t.startswith("/start") else t
        link = db.scalars(select(ChatLink).where(ChatLink.chat_id == chat_id)).first()
        if t == "/switch":
            if link:
                db.delete(link)
                db.commit()
            say(token, chat_id, "کد رباتِ مورد نظر را بفرستید.")
            return
        found = None
        if re.fullmatch(r"[A-Za-z0-9]{4,12}", cand or ""):
            found = db.scalars(select(Publication).where(Publication.code == cand.upper(), Publication.mode == "shared")).first()
        if found:
            if link:
                link.pub_id = found.id
            else:
                db.add(ChatLink(chat_id=chat_id, pub_id=found.id))
            db.commit()
            pub, welcome_now = found, True
        elif link:
            pub = db.get(Publication, link.pub_id)
        if pub is None:
            say(token, chat_id, "سلام! 👋 برای شروع، «کد ربات» را بفرستید (صاحب کسب‌وکار آن را به شما می‌دهد).")
            return

    ver = db.scalars(select(BotVersion).where(BotVersion.bot_id == pub.bot_id, BotVersion.version == pub.version)).first()
    if ver is None:
        say(token, chat_id, "این ربات فعلاً در دسترس نیست.")
        return
    spec = BotSpec.model_validate(ver.spec)
    skey = f"bale:{chat_id}"
    with _locks[pub.bot_id]:
        row = db.scalars(select(ChatSession).where(ChatSession.bot_id == pub.bot_id, ChatSession.key == skey)).first()
        if row is None:
            row = ChatSession(bot_id=pub.bot_id, key=skey, state=engine.new_session())
            db.add(row)
        state = copy.deepcopy(row.state)  # a shallow copy would hide in-place edits from SQLAlchemy's change detection
        if t.startswith("~"):
            t = state.get("_cb", {}).get(t, t)
        if welcome_now:
            state, t = engine.new_session(), "/start"
        elif kind == "shared" and t.startswith("/start"):
            t = "/start"
        actions = engine.handle(spec, state, t, SqlStore(db, pub.bot_id, sandbox=False))
        deliver(token, chat_id, actions, state, pub.admin_chat_id, clicked_message_id)
        row.state = state
        db.commit()
