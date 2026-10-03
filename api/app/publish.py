"""Publishing a bot to Bale: status, publish/republish, unpublish and the two webhooks."""
from __future__ import annotations

import hmac

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import bale
from .auth import current_user
from .config import settings
from .db import get_db
from .models import Bot, BotVersion, ChatLink, Publication, User, VersionTests

router = APIRouter()


def _own(bot_id: int, user: User, db: Session) -> Bot:
    bot = db.get(Bot, bot_id)
    if not bot or bot.user_id != user.id:
        raise HTTPException(404, "ربات یافت نشد")
    return bot


def _latest(bot_id: int, db: Session):
    return db.scalars(select(BotVersion).where(BotVersion.bot_id == bot_id).order_by(BotVersion.version.desc())).first()


def _tests_ok(bot_id: int, version: int, db: Session) -> bool:
    """No recorded tests (template bots) counts as OK; any failing test blocks publishing."""
    t = db.scalars(select(VersionTests).where(VersionTests.bot_id == bot_id, VersionTests.version == version)).first()
    return True if t is None else all(r["passed"] for r in t.results)


def _status(bot_id: int, db: Session) -> dict:
    latest = _latest(bot_id, db)
    pub = db.scalars(select(Publication).where(Publication.bot_id == bot_id)).first()
    out = {
        "published": pub is not None,
        "latest_version": latest.version if latest else 0,
        "tests_ok": _tests_ok(bot_id, latest.version, db) if latest else False,
        "shared_bot_username": bale.shared_username(),
        "webhooks_enabled": bool(settings.public_base_url),
    }
    if pub:
        out |= {"mode": pub.mode, "version": pub.version, "code": pub.code, "admin_code": pub.admin_code,
                "bot_username": pub.bot_username or (bale.shared_username() if pub.mode == "shared" else ""),
                "admin_linked": bool(pub.admin_chat_id), "up_to_date": bool(latest and pub.version == latest.version)}
    return out


class PublishIn(BaseModel):
    mode: str  # shared | own
    token: str | None = None


@router.get("/api/bots/{bot_id}/publication")
def publication(bot_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _own(bot_id, user, db)
    return _status(bot_id, db)


@router.post("/api/bots/{bot_id}/publish")
def publish(bot_id: int, body: PublishIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _own(bot_id, user, db)
    latest = _latest(bot_id, db)
    if latest is None:
        raise HTTPException(409, "ربات هنوز ساخته نشده است")
    if not _tests_ok(bot_id, latest.version, db):
        raise HTTPException(409, "نسخه‌ی فعلی هنوز همه‌ی تست‌ها را نگذرانده؛ ابتدا با ایجنت اصلاحش کنید")
    if body.mode not in ("shared", "own"):
        raise HTTPException(400, "حالت انتشار نامعتبر است")
    if not settings.public_base_url:
        raise HTTPException(503, "آدرس عمومی سرور تنظیم نشده است")
    pub = db.scalars(select(Publication).where(Publication.bot_id == bot_id)).first()

    token_enc, username = "", ""
    if body.mode == "own":
        token = (body.token or "").strip()
        if not token and pub and pub.mode == "own":
            token = bale.decrypt(pub.token_enc)
        if not token:
            raise HTTPException(400, "توکن ربات را وارد کنید")
        try:
            username = bale.api_call(token, "getMe").get("username", "")
        except bale.BaleError:
            raise HTTPException(400, "توکن معتبر نیست؛ دوباره از @botfather بله کپی کنید")
        token_enc = bale.encrypt(token)
    elif not settings.bale_shared_bot_token:
        raise HTTPException(503, "ربات اشتراکی بات‌یار تنظیم نشده است")

    # leaving an old own-token webhook behind would keep a stale bot answering
    if pub and pub.mode == "own" and (body.mode == "shared" or token_enc != pub.token_enc):
        try:
            bale.api_call(bale.decrypt(pub.token_enc), "deleteWebhook")
        except Exception:  # noqa: BLE001
            pass

    if pub is None:
        pub = Publication(bot_id=bot_id, mode=body.mode, version=latest.version, code=bale.new_code(6),
                          admin_code=bale.new_code(8), hook_secret=bale.new_code(24) + bale.new_code(24))
        db.add(pub)
        db.flush()
    pub.mode, pub.version, pub.token_enc, pub.bot_username = body.mode, latest.version, token_enc, username
    if body.mode == "own":
        url = f"{settings.public_base_url.rstrip('/')}/api/hook/own/{pub.id}/{pub.hook_secret}"
        try:
            bale.api_call(bale.decrypt(token_enc), "setWebhook", {"url": url})
        except bale.BaleError as e:
            db.rollback()
            raise HTTPException(502, f"ثبت وبهوک در بله ناموفق بود: {e}")
    db.commit()
    return _status(bot_id, db)


@router.post("/api/bots/{bot_id}/unpublish")
def unpublish(bot_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _own(bot_id, user, db)
    pub = db.scalars(select(Publication).where(Publication.bot_id == bot_id)).first()
    if pub:
        if pub.mode == "own":
            try:
                bale.api_call(bale.decrypt(pub.token_enc), "deleteWebhook")
            except Exception:  # noqa: BLE001
                pass
        db.execute(delete(ChatLink).where(ChatLink.pub_id == pub.id))
        db.delete(pub)
        db.commit()
    return _status(bot_id, db)


# ---------- webhooks (Bale has no webhook secret header, so the secret is in the URL) ----------
@router.post("/api/hook/shared/{secret}")
async def hook_shared(secret: str, request: Request, tasks: BackgroundTasks):
    if not hmac.compare_digest(secret, bale.shared_hook_secret()):
        raise HTTPException(404)
    tasks.add_task(bale.process_update, "shared", None, await request.json())
    return {"ok": True}


@router.post("/api/hook/own/{pub_id}/{secret}")
async def hook_own(pub_id: int, secret: str, request: Request, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    pub = db.get(Publication, pub_id)
    if pub is None or pub.mode != "own" or not hmac.compare_digest(secret, pub.hook_secret):
        raise HTTPException(404)
    tasks.add_task(bale.process_update, "own", pub.id, await request.json())
    return {"ok": True}
