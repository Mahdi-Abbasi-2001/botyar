"""Publishing a bot to Bale: status, publish/republish, unpublish and the two webhooks."""
from __future__ import annotations

import hmac

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import bale, faq_index
from . import billing
from .auth import current_user
from .config import settings
from .db import get_db
from .models import Bot, BotListing, BotVersion, ChatLink, Product, Publication, StaffLink, User, VersionTests
from .spec import BotSpec

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


def sample_catalog(bot_id: int, db: Session) -> bool:
    """True while the bot's product table holds only the demo products the agent invented at build time:
    real customers would see (and order) products that don't exist."""
    flags = list(db.scalars(select(Product.is_sample).where(Product.bot_id == bot_id)))
    return bool(flags) and all(flags)


SAMPLE_MSG = ("محصولات این ربات هنوز نمونه‌اند و بات‌یار آن‌ها را برای امتحان ساخته است؛ مشتریان واقعی همین محصولات ساختگی را می‌بینند. "
              "ابتدا فهرست واقعی محصولات را در بخش «محصولات» وارد کنید.")


def _digest_on(db: Session, bot_id: int) -> bool:
    from .outreach import digest_enabled  # outreach imports this module's neighbours; import late
    return digest_enabled(db, bot_id)


def check_samples(bot_id: int, allow: bool, db: Session):
    if sample_catalog(bot_id, db) and not allow:
        raise HTTPException(409, SAMPLE_MSG)


def content_blocks(bot_id: int, db: Session) -> list[dict]:
    """The blocks that hand out content behind a channel join: each gets its own link (so a post or a story can point straight at it)."""
    latest = _latest(bot_id, db)
    if latest is None:
        return []
    spec = BotSpec.model_validate(latest.spec)
    out = []
    for b in spec.blocks:
        if b.type == "message" and b.join:
            label = next((m.label for m in spec.menu if m.block == b.id), b.id)
            out.append({"id": b.id, "title": label, "channels": [c.channel for c in b.join]})
    return out


def _status(bot_id: int, db: Session) -> dict:
    latest = _latest(bot_id, db)
    pub = db.scalars(select(Publication).where(Publication.bot_id == bot_id)).first()
    out = {
        "published": pub is not None,
        "latest_version": latest.version if latest else 0,
        "tests_ok": _tests_ok(bot_id, latest.version, db) if latest else False,
        "shared_bot_username": bale.shared_username(),
        "webhooks_enabled": bool(settings.public_base_url),
        "listed": not bale._hidden(db, bot_id),
        "sample_products": sample_catalog(bot_id, db),
        "daily_summary": _digest_on(db, bot_id),
        "contents": content_blocks(bot_id, db),
    }
    if pub:
        out |= {"mode": pub.mode, "version": pub.version, "code": pub.code, "admin_code": pub.admin_code,
                "bot_username": pub.bot_username or (bale.shared_username() if pub.mode == "shared" else ""),
                "admin_linked": bool(pub.admin_chat_id), "up_to_date": bool(latest and pub.version == latest.version)}
    return out


def _staff_names(bot_id: int, db: Session) -> list[str]:
    latest = _latest(bot_id, db)
    if latest is None:
        return []
    names: list[str] = []
    for b in BotSpec.model_validate(latest.spec).blocks:
        for n in (b.schedule.staff if b.type == "booking" and b.schedule else []):
            if n not in names:
                names.append(n)
    return names


@router.get("/api/bots/{bot_id}/staff")
def staff_links(bot_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Each staff member of the bot's appointment calendars, with the code they send («/staff CODE») to get their bookings."""
    _own(bot_id, user, db)
    out = []
    for name in _staff_names(bot_id, db):
        link = db.scalars(select(StaffLink).where(StaffLink.bot_id == bot_id, StaffLink.name == name)).first()
        if link is None:
            link = StaffLink(bot_id=bot_id, name=name, code="S" + bale.new_code(7), messenger="", chat_id="")
            db.add(link)
            db.commit()
        out.append({"name": name, "code": link.code, "linked": bool(link.chat_id), "messenger": link.messenger})
    return out


class StaffResetIn(BaseModel):
    name: str


@router.post("/api/bots/{bot_id}/staff/reset")
def staff_reset(bot_id: int, body: StaffResetIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Unlink a staff member's chat (e.g. they left) and give them a fresh code."""
    _own(bot_id, user, db)
    link = db.scalars(select(StaffLink).where(StaffLink.bot_id == bot_id, StaffLink.name == body.name)).first()
    if link is None:
        raise HTTPException(404, "همکار یافت نشد")
    link.code, link.messenger, link.chat_id = "S" + bale.new_code(7), "", ""
    db.commit()
    return staff_links(bot_id, user, db)


class PublishIn(BaseModel):
    mode: str  # shared | own
    token: str | None = None
    allow_samples: bool = False  # the owner ticked «publish with the demo products, only to try it»


@router.get("/api/bots/{bot_id}/publication")
def publication(bot_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _own(bot_id, user, db)
    return _status(bot_id, db)


@router.post("/api/bots/{bot_id}/publish")
def publish(bot_id: int, body: PublishIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _own(bot_id, user, db)
    billing.check_publish(db, user, bot_id)
    latest = _latest(bot_id, db)
    if latest is None:
        raise HTTPException(409, "ربات هنوز ساخته نشده است")
    if not _tests_ok(bot_id, latest.version, db):
        raise HTTPException(409, "همه‌ی تست‌های نسخه‌ی فعلی هنوز موفق نشده‌اند؛ ابتدا ربات را در «گفت‌وگوی ساخت» اصلاح کنید")
    check_samples(bot_id, body.allow_samples, db)
    if body.mode not in ("shared", "own"):
        raise HTTPException(400, "حالت انتشار نامعتبر است")
    if not settings.public_base_url:
        raise HTTPException(503, "آدرس عمومی سرور تنظیم نشده است")
    pub = db.scalars(select(Publication).where(Publication.bot_id == bot_id)).first()
    try:  # a failed first indexing is retried here, before any customer can use the FAQ (cheap no-op when already indexed)
        faq_index.ensure(db, bot_id, BotSpec.model_validate(latest.spec))
    except Exception:  # noqa: BLE001
        db.rollback()

    token_enc, username = "", ""
    if body.mode == "own":
        token = (body.token or "").strip()
        if not token and pub and pub.mode == "own":
            token = bale.decrypt(pub.token_enc)
        if not token:
            raise HTTPException(400, "توکن ربات را وارد کنید")
        try:
            username = bale.api_call(token, "getMe").get("username", "")
        except (bale.TransientError, bale.UncertainError):  # an outage must never be reported as «your token is wrong»
            raise HTTPException(503, "اتصال به بله برقرار نشد؛ ممکن است بله یا اینترنت در دسترس نباشد. چند دقیقه بعد دوباره تلاش کنید.")
        except bale.BaleError:
            raise HTTPException(400, "توکن معتبر نیست؛ آن را دوباره از @botfather در بله کپی کنید")
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
        except bale.TransientError:
            db.rollback()
            raise HTTPException(503, "اتصال به بله برقرار نشد؛ ممکن است بله یا اینترنت در دسترس نباشد. چند دقیقه بعد دوباره تلاش کنید.")
        except bale.BaleError as e:
            db.rollback()
            raise HTTPException(502, f"اتصال ربات به بله ناموفق بود: {e}")
    db.commit()
    return _status(bot_id, db)


class ListingIn(BaseModel):
    listed: bool


@router.put("/api/bots/{bot_id}/listing")
def set_listing(bot_id: int, body: ListingIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Show or hide the bot in the shared bots' directory (Bale and Telegram). Its link keeps working either way."""
    _own(bot_id, user, db)
    row = db.scalars(select(BotListing).where(BotListing.bot_id == bot_id)).first()
    if row is None:
        row = BotListing(bot_id=bot_id)
        db.add(row)
    row.hidden = not body.listed
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
async def _json(request: Request) -> dict:
    try:
        data = await request.json()
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "bad json")
    if not isinstance(data, dict):
        raise HTTPException(400, "bad json")
    return data



@router.post("/api/hook/shared/{secret}")
async def hook_shared(secret: str, request: Request, tasks: BackgroundTasks):
    if not hmac.compare_digest(secret, bale.shared_hook_secret()):
        raise HTTPException(404)
    tasks.add_task(bale.process_update, "shared", None, await _json(request))
    return {"ok": True}


@router.post("/api/hook/own/{pub_id}/{secret}")
async def hook_own(pub_id: int, secret: str, request: Request, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    pub = db.get(Publication, pub_id)
    if pub is None or pub.mode != "own" or not hmac.compare_digest(secret, pub.hook_secret):
        raise HTTPException(404)
    tasks.add_task(bale.process_update, "own", pub.id, await _json(request))
    return {"ok": True}
