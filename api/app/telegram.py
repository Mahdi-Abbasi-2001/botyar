"""Telegram channel: the same bots as on Bale, answered by the same engine (bale.Channel).

Telegram is unreachable from Iranian servers (verified from the Liara container: "No route to host"), so every Bot API
call and every incoming update goes through a small reverse proxy outside Iran (relay/main.ts on Deno Deploy):

    Liara ──► {relay}/bot<token>/<method> ──► api.telegram.org          (header x-relay-key)
    Telegram ──► {relay}/hook/<path> ──► Liara /api/tghook/<path>      (the path carries our secret)

No online payments here: Telegram's payment providers don't serve Iran, so Telegram bots take orders without the
pay button."""
from __future__ import annotations

import hashlib
import hmac
import logging

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import bale, faq_index
from .auth import current_user
from .config import settings
from .db import get_db
from .models import Publication, TgChatLink, TgPublication, User
from .publish import _json, _latest, _own, _tests_ok
from .spec import BotSpec

log = logging.getLogger("botyar.telegram")
router = APIRouter()


def enabled() -> bool:
    return bool(settings.telegram_relay_url and settings.telegram_relay_key)


def api_call(token: str, method: str, payload: dict | None = None, timeout: float = 15):
    if not enabled():
        raise bale.BaleError("Telegram relay is not configured")
    try:
        r = httpx.post(f"{settings.telegram_relay_url.rstrip('/')}/bot{token}/{method}", json=payload or {},
                       headers={"x-relay-key": settings.telegram_relay_key}, timeout=timeout + 5)
    except httpx.HTTPError as e:
        raise bale.BaleError(f"relay unreachable: {type(e).__name__}")
    try:
        d = r.json()
    except Exception:
        raise bale.BaleError(f"HTTP {r.status_code}")
    if not d.get("ok"):
        raise bale.BaleError(d.get("description") or f"HTTP {r.status_code}")
    return d.get("result")


TELEGRAM = bale.Channel("tg", lambda *a, **k: api_call(*a, **k), TgPublication, TgChatLink,
                        lambda: settings.telegram_shared_bot_token, payments=False)
bale.CHANNELS["tg"] = TELEGRAM


def shared_hook_secret() -> str:
    return hmac.new(settings.jwt_secret.encode(), b"tg-shared-hook", hashlib.sha256).hexdigest()[:32]


def hook_url(path: str) -> str:
    """Where Telegram should POST updates: the relay, which forwards them to /api/tghook/<path> on this server."""
    return f"{settings.telegram_relay_url.rstrip('/')}/hook/{path}"


_username_cache: dict[str, str] = {}


def shared_username() -> str:
    t = settings.telegram_shared_bot_token
    if not (t and enabled()):
        return ""
    if t not in _username_cache:
        try:
            _username_cache[t] = api_call(t, "getMe").get("username", "")
        except Exception as e:  # noqa: BLE001
            log.warning("telegram getMe failed: %s", e)
            return ""
    return _username_cache[t]


def ensure_shared_webhook():
    """Register the shared Telegram bot's webhook (production only, like the Bale one)."""
    if not (settings.telegram_shared_bot_token and settings.public_base_url and enabled()):
        return
    try:
        api_call(settings.telegram_shared_bot_token, "setWebhook",
                 {"url": hook_url(f"shared/{shared_hook_secret()}"), "allowed_updates": ["message", "callback_query"]})
        log.info("telegram shared webhook registered")
    except Exception as e:  # noqa: BLE001
        log.warning("telegram setWebhook failed: %s", e)


# ---------- publishing ----------
def _status(bot_id: int, db: Session) -> dict:
    latest = _latest(bot_id, db)
    pub = db.scalars(select(TgPublication).where(TgPublication.bot_id == bot_id)).first()
    out = {
        "enabled": enabled() and bool(settings.public_base_url),
        "published": pub is not None,
        "latest_version": latest.version if latest else 0,
        "tests_ok": _tests_ok(bot_id, latest.version, db) if latest else False,
        "shared_bot_username": shared_username() if settings.telegram_shared_bot_token else "",
        "listed": not bale._hidden(db, bot_id),
    }
    if pub:
        out |= {"mode": pub.mode, "version": pub.version, "code": pub.code, "admin_code": pub.admin_code,
                "bot_username": pub.bot_username or (out["shared_bot_username"] if pub.mode == "shared" else ""),
                "admin_linked": bool(pub.admin_chat_id), "up_to_date": bool(latest and pub.version == latest.version)}
    return out


class TgPublishIn(BaseModel):
    mode: str  # shared | own
    token: str | None = None


@router.get("/api/bots/{bot_id}/telegram")
def tg_publication(bot_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _own(bot_id, user, db)
    return _status(bot_id, db)


def _new_code(db: Session, bot_id: int) -> str:
    """Reuse the bot's Bale code when it is free here, so customers have ONE code for both messengers."""
    bale_pub = db.scalars(select(Publication).where(Publication.bot_id == bot_id)).first()
    if bale_pub and not db.scalars(select(TgPublication).where(TgPublication.code == bale_pub.code)).first():
        return bale_pub.code
    while True:
        code = bale.new_code(6)
        taken = db.scalars(select(TgPublication).where(TgPublication.code == code)).first() or \
            db.scalars(select(Publication).where(Publication.code == code)).first()
        if not taken:
            return code


@router.post("/api/bots/{bot_id}/telegram/publish")
def tg_publish(bot_id: int, body: TgPublishIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _own(bot_id, user, db)
    if not (enabled() and settings.public_base_url):
        raise HTTPException(503, "اتصال به تلگرام روی این سرور فعال نیست")
    latest = _latest(bot_id, db)
    if latest is None:
        raise HTTPException(409, "ربات هنوز ساخته نشده است")
    if not _tests_ok(bot_id, latest.version, db):
        raise HTTPException(409, "نسخه‌ی فعلی هنوز همه‌ی تست‌ها را نگذرانده؛ ابتدا با ایجنت اصلاحش کنید")
    if body.mode not in ("shared", "own"):
        raise HTTPException(400, "حالت انتشار نامعتبر است")
    pub = db.scalars(select(TgPublication).where(TgPublication.bot_id == bot_id)).first()
    try:
        faq_index.ensure(db, bot_id, BotSpec.model_validate(latest.spec))
    except Exception:  # noqa: BLE001
        db.rollback()

    token_enc, username = "", ""
    if body.mode == "own":
        token = (body.token or "").strip()
        if not token and pub and pub.mode == "own":
            token = bale.decrypt(pub.token_enc)
        if not token:
            raise HTTPException(400, "توکن ربات تلگرام را وارد کنید")
        try:
            username = api_call(token, "getMe").get("username", "")
        except bale.BaleError as e:
            if "relay" in str(e):
                raise HTTPException(502, "اتصال به تلگرام برقرار نشد؛ چند دقیقه بعد دوباره تلاش کنید")
            raise HTTPException(400, "توکن معتبر نیست؛ دوباره از @BotFather تلگرام کپی کنید")
        token_enc = bale.encrypt(token)
    elif not settings.telegram_shared_bot_token:
        raise HTTPException(503, "ربات اشتراکی تلگرام بات‌یار تنظیم نشده است")

    if pub and pub.mode == "own" and (body.mode == "shared" or token_enc != pub.token_enc):
        try:  # a stale own-token webhook would keep an old bot answering
            api_call(bale.decrypt(pub.token_enc), "deleteWebhook")
        except Exception:  # noqa: BLE001
            pass

    if pub is None:
        pub = TgPublication(bot_id=bot_id, mode=body.mode, version=latest.version, code=_new_code(db, bot_id),
                            admin_code=bale.new_code(8), hook_secret=bale.new_code(24) + bale.new_code(24))
        db.add(pub)
        db.flush()
    pub.mode, pub.version, pub.token_enc, pub.bot_username = body.mode, latest.version, token_enc, username
    if body.mode == "own":
        try:
            api_call(bale.decrypt(token_enc), "setWebhook",
                     {"url": hook_url(f"own/{pub.id}/{pub.hook_secret}"), "allowed_updates": ["message", "callback_query"]})
        except bale.BaleError as e:
            db.rollback()
            raise HTTPException(502, f"ثبت وبهوک در تلگرام ناموفق بود: {e}")
    db.commit()
    return _status(bot_id, db)


@router.post("/api/bots/{bot_id}/telegram/unpublish")
def tg_unpublish(bot_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _own(bot_id, user, db)
    pub = db.scalars(select(TgPublication).where(TgPublication.bot_id == bot_id)).first()
    if pub:
        if pub.mode == "own":
            try:
                api_call(bale.decrypt(pub.token_enc), "deleteWebhook")
            except Exception:  # noqa: BLE001
                pass
        db.execute(delete(TgChatLink).where(TgChatLink.pub_id == pub.id))
        db.delete(pub)
        db.commit()
    return _status(bot_id, db)


# ---------- webhooks (reached only through the relay; the secret is in the path) ----------
@router.post("/api/tghook/shared/{secret}")
async def tg_hook_shared(secret: str, request: Request, tasks: BackgroundTasks):
    if not hmac.compare_digest(secret, shared_hook_secret()):
        raise HTTPException(404)
    tasks.add_task(bale.process_update, "shared", None, await _json(request), TELEGRAM)
    return {"ok": True}


@router.post("/api/tghook/own/{pub_id}/{secret}")
async def tg_hook_own(pub_id: int, secret: str, request: Request, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    pub = db.get(TgPublication, pub_id)
    if pub is None or pub.mode != "own" or not hmac.compare_digest(secret, pub.hook_secret):
        raise HTTPException(404)
    tasks.add_task(bale.process_update, "own", pub.id, await _json(request), TELEGRAM)
    return {"ok": True}
