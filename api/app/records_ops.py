"""Owner actions on records from the dashboard: cancel a booking/order, move an order along
new -> preparing -> ready -> done. The rules live in engine.cancel_record / engine.set_order_status (shared with the
customer flow); this module only authorises, takes the per-bot lock, saves, and delivers the customer messages."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import bale, engine
from .auth import current_user
from .dates import now_tehran
from .db import get_db
from .models import Bot, BotVersion, Record, User
from .spec import BotSpec
from .store import SqlStore

router = APIRouter()


class RecordAction(BaseModel):
    action: Literal["cancel", "status", "confirm_payment"]  # confirm_payment: a card-to-card order whose money the owner saw
    status: str | None = None  # orders: preparing | ready | done; bookings: no_show (for action="status")
    reason: str = Field(default="", max_length=300)  # shown to the customer on cancel


@router.patch("/api/bots/{bot_id}/records/{record_id}")
def act_on_record(bot_id: int, record_id: int, body: RecordAction, user: User = Depends(current_user), db: Session = Depends(get_db)):
    bot = db.get(Bot, bot_id)
    if not bot or bot.user_id != user.id:
        raise HTTPException(404, "ربات یافت نشد")
    rec = db.get(Record, record_id)
    if not rec or rec.bot_id != bot_id:
        raise HTTPException(404, "ثبت یافت نشد")
    ver = db.scalars(select(BotVersion).where(BotVersion.bot_id == bot_id).order_by(BotVersion.version.desc())).first()
    spec = BotSpec.model_validate(ver.spec)
    block = next((b for b in spec.blocks if b.id == rec.collection and b.type in ("booking", "catalog_order", "faq", "form")), None)  # contact threads use the inbox endpoints
    if block is None:
        raise HTTPException(409, "بخش مربوط به این ثبت دیگر در ربات نیست")

    store = SqlStore(db, bot_id, sandbox=rec.sandbox)
    now = now_tehran()
    with bale._locks[bot_id]:  # same lock as customers' bookings: an owner action must not interleave with a capacity check
        row = store.find(rec.collection, id=rec.id)[0]
        status_now = row.get("status")
        promoted = None
        try:
            if body.action == "cancel" and block.type == "faq":
                raise ValueError("سؤال‌ها لغو نمی‌شوند؛ پاسخ را به پرسش‌های متداول ربات اضافه کنید یا «رسیدگی شد» را بزنید.")
            if block.type == "form":  # applications/requests: the owner's decision (with an optional note for the customer)
                if body.action != "status" or not body.status:
                    raise ValueError("برای فرم فقط وضعیت بررسی قابل ثبت است.")
                actions = engine.set_form_status(store, now, block, row, body.status, body.reason)
            elif body.action == "confirm_payment":
                if block.type != "catalog_order":
                    raise ValueError("تأیید واریز فقط برای سفارش‌هاست.")
                actions = engine.confirm_transfer(store, now, block, row)
            elif body.action == "cancel":
                if status_now in ("cancelled", "done"):
                    raise ValueError("این ثبت قبلاً بسته یا لغو شده است.")
                actions, promoted = engine.cancel_record(spec, store, now, block, row, by="owner", reason=body.reason)
            elif block.type == "faq":
                if body.status != "handled" or status_now != "unanswered":
                    raise ValueError("سؤال‌ها را فقط می‌توان «رسیدگی شد» کرد.")
                store.update(rec.collection, rec.id, status="handled", _handled_at=now.isoformat())
                actions = []
            else:
                if not body.status:
                    raise ValueError("وضعیت جدید را مشخص کنید.")
                if block.type == "booking":
                    if body.status != "no_show":
                        raise ValueError("برای نوبت فقط «حاضر نشد» قابل ثبت است.")
                    actions = engine.mark_no_show(store, now, block, row)
                else:
                    actions = engine.set_order_status(store, now, block, row, body.status)
        except ValueError as e:
            db.rollback()
            raise HTTPException(409, str(e))
        db.commit()

    sent = 0 if rec.sandbox else bale.send_customer_actions(db, bot_id, actions)  # simulator customers (sim:…) have no chat
    wanted = sum(a["type"] == "notify_customer" for a in actions)
    new_status = store.find(rec.collection, id=rec.id)[0]["status"]
    return {"id": rec.id, "status": new_status, "customer_messages": {"wanted": wanted, "sent": sent, "sandbox": rec.sandbox},
            "refund_needed": bool(row.get("paid")) and body.action == "cancel",
            "promoted": {"id": promoted["id"], "name": promoted.get("name")} if promoted else None}


# ---------- inbox for "talk to the owner" blocks ----------
class InboxReply(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


def _threads(db: Session, bot_id: int, sandbox: bool, only: str | None = None):
    rows = db.scalars(select(Record).where(Record.bot_id == bot_id, Record.sandbox == sandbox).order_by(Record.id)).all()
    out: dict[str, dict] = {}
    for r in rows:
        d = r.data
        if "thread" not in d or d.get("from") not in ("customer", "owner"):
            continue
        key = f"{r.collection}:{d['thread']}"
        if only and key != only:
            continue
        t = out.setdefault(key, {"thread": d["thread"], "collection": r.collection, "who": d.get("who", "مشتری"), "cust": d.get("_cust"), "messages": [], "unanswered": False, "topic": ""})
        t["topic"] = d.get("topic") or t["topic"]  # the latest topic the customer chose (contact `topics`)
        if d["from"] == "customer":
            t["who"] = d.get("who", t["who"])
        t["messages"].append({"id": r.id, "from": d["from"], "text": d.get("text", ""), "at": r.created_at.isoformat()})
        t["unanswered"] = d["from"] == "customer"
    return out


@router.get("/api/bots/{bot_id}/inbox")
def inbox(bot_id: int, sandbox: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    bot = db.get(Bot, bot_id)
    if not bot or bot.user_id != user.id:
        raise HTTPException(404, "ربات یافت نشد")
    threads = list(_threads(db, bot_id, sandbox).values())
    for t in threads:
        t.pop("cust")
    threads.sort(key=lambda t: t["messages"][-1]["id"], reverse=True)
    return threads[:200]


@router.post("/api/bots/{bot_id}/inbox/{collection}/{thread}/reply")
def inbox_reply(bot_id: int, collection: str, thread: str, body: InboxReply, sandbox: bool = False,
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    bot = db.get(Bot, bot_id)
    if not bot or bot.user_id != user.id:
        raise HTTPException(404, "ربات یافت نشد")
    text = body.text.strip()
    if not text:
        raise HTTPException(422, "متن پاسخ خالی است")
    with bale._locks[bot_id]:
        t = _threads(db, bot_id, sandbox, only=f"{collection}:{thread}").get(f"{collection}:{thread}")
        if t is None:
            raise HTTPException(404, "گفت‌وگو یافت نشد")
        store = SqlStore(db, bot_id, sandbox=sandbox)
        row = store.add(collection, {"text": text, "from": "owner", "thread": thread, "who": t["who"], "_cust": t["cust"], "_at": now_tehran().isoformat()})
        db.commit()
    actions = [{"type": "notify_customer", "cust": t["cust"], "text": f"✉️ پاسخ مدیر:\n{text}"}] if t["cust"] else []
    sent = 0 if sandbox else bale.send_customer_actions(db, bot_id, actions)
    return {"id": row["id"], "delivered": sent, "wanted": len(actions), "sandbox": sandbox}


# ---------- answering a FAQ question the bot could not answer ----------
class FaqAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=1500)
    add_to_faq: bool = True  # also teach the bot: the question and answer become a new FAQ entry (a new version)
    question: str = Field(default="", max_length=200)  # the question as it should appear in the FAQ (default: as the customer wrote it)


def add_faq_entry(db: Session, bot_id: int, block_id: str, question: str, answer: str) -> tuple[int | None, str]:
    """Save a new version with one more FAQ entry, after re-running the current version's tests against it.
    Returns (new version, "") or (None, why not). A live bot moves to the new version with it."""
    from threading import Thread

    from . import faq_index, testing
    from .db import SessionLocal
    from .models import BuilderRun, Publication, TgPublication, VersionFixture, VersionTests
    from .spec import FaqEntry

    if db.scalar(select(BuilderRun).where(BuilderRun.bot_id == bot_id, BuilderRun.status == "running")):
        return None, "ربات همین حالا در حال ساخت است؛ پس از پایان ساخت دوباره امتحان کنید."
    latest = db.scalars(select(BotVersion).where(BotVersion.bot_id == bot_id).order_by(BotVersion.version.desc())).first()
    spec = BotSpec.model_validate(latest.spec).model_dump()
    block = next((b for b in spec["blocks"] if b["id"] == block_id and b["type"] == "faq"), None)
    if block is None:
        return None, "این بخش پرسش‌های متداول دیگر در ربات نیست."
    if len(block["entries"]) >= 40:
        return None, "پرسش‌های متداول این بخش به سقف ۴۰ سؤال رسیده است."
    q = " ".join(question.split())
    if any(" ".join(e["question"].split()) == q for e in block["entries"]):
        return None, "این سؤال همین حالا در پرسش‌های متداول هست."
    try:
        block["entries"].append(FaqEntry(question=q, answer=answer.strip()).model_dump())
        new_spec = BotSpec.model_validate(spec)
    except ValueError as e:
        return None, f"افزودن ممکن نشد: {e}"
    tests = db.scalars(select(VersionTests).where(VersionTests.bot_id == bot_id, VersionTests.version == latest.version)).first()
    fixture = db.scalars(select(VersionFixture).where(VersionFixture.bot_id == bot_id, VersionFixture.version == latest.version)).first()
    results = []
    if tests is not None:
        results = testing.run_plan(new_spec, [testing.TestScenario.model_validate(s) for s in tests.scenarios], fixture.catalog if fixture else None)
        if not all(r["passed"] for r in results):
            return None, "با این سؤال، یکی از تست‌های ربات دیگر درست کار نمی‌کند (احتمالاً سؤال با سؤال دیگری اشتباه گرفته می‌شود). آن را در «گفت‌وگوی ساخت» اضافه کنید."
    v = latest.version + 1
    db.add(BotVersion(bot_id=bot_id, version=v, spec=new_spec.model_dump(), note=f"سؤال «{q}» از «ثبت‌ها» به پرسش‌های متداول افزوده شد"))
    if tests is not None:
        db.add(VersionTests(bot_id=bot_id, version=v, scenarios=tests.scenarios, results=results))
    if fixture is not None:
        db.add(VersionFixture(bot_id=bot_id, version=v, catalog=fixture.catalog))
    for model in (Publication, TgPublication):  # a live bot that runs the latest version keeps doing so
        for pub in db.scalars(select(model).where(model.bot_id == bot_id, model.version == latest.version)):
            pub.version = v
    db.commit()

    def index():  # the embedding index catches up in the background; until then the bot matches by words
        with SessionLocal() as s:
            try:
                faq_index.ensure(s, bot_id, new_spec)
            except Exception:  # noqa: BLE001
                s.rollback()
    Thread(target=index, daemon=True).start()
    return v, ""


@router.post("/api/bots/{bot_id}/records/{record_id}/answer")
def answer_question(bot_id: int, record_id: int, body: FaqAnswer, user: User = Depends(current_user), db: Session = Depends(get_db)):
    bot = db.get(Bot, bot_id)
    if not bot or bot.user_id != user.id:
        raise HTTPException(404, "ربات یافت نشد")
    rec = db.get(Record, record_id)
    if not rec or rec.bot_id != bot_id or rec.data.get("status") != "unanswered" or "question" not in rec.data:
        raise HTTPException(404, "سؤال بی‌پاسخی با این شماره یافت نشد")
    answer = body.answer.strip()
    if not answer:
        raise HTTPException(422, "متن پاسخ خالی است")
    asked = rec.data["question"]
    version, why = None, ""
    if body.add_to_faq:
        with bale._locks[bot_id]:
            version, why = add_faq_entry(db, bot_id, rec.collection, body.question.strip() or asked, answer)
    rec.data = {**rec.data, "status": "handled", "answer": answer, "_handled_at": now_tehran().isoformat()}
    db.commit()
    cust = rec.data.get("_cust")
    actions = [{"type": "notify_customer", "cust": cust, "text": f"✉️ پاسخ سؤال شما:\n«{asked}»\n\n{answer}"}] if cust else []
    sent = 0 if rec.sandbox else bale.send_customer_actions(db, bot_id, actions)
    return {"status": "handled", "customer_messages": {"wanted": len(actions), "sent": sent, "sandbox": rec.sandbox},
            "added_version": version, "not_added": why}


# ---------- files customers sent for a form question ----------
@router.get("/api/bots/{bot_id}/records/{record_id}/files/{key}")
def record_file(bot_id: int, record_id: int, key: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Fetch the file from the messenger that received it (Bale keeps the file; Botyar stores only its id)."""
    import httpx
    from fastapi import Response

    from .config import settings
    from .models import Publication

    bot = db.get(Bot, bot_id)
    if not bot or bot.user_id != user.id:
        raise HTTPException(404, "ربات یافت نشد")
    rec = db.get(Record, record_id)
    meta = ((rec.data.get("_files") or {}).get(key) if rec and rec.bot_id == bot_id else None)
    if not meta:
        raise HTTPException(404, "فایل یافت نشد")
    if rec.sandbox:
        raise HTTPException(409, "این فایل در شبیه‌ساز فرستاده شده و فایل واقعی ندارد")
    if not str(rec.data.get("_cust", "")).startswith("bale:"):
        raise HTTPException(409, "فایل‌های تلگرام فقط در چت مدیر ارسال می‌شوند")
    pub = db.scalars(select(Publication).where(Publication.bot_id == bot_id)).first()
    token = bale.decrypt(pub.token_enc) if pub and pub.mode == "own" else settings.bale_shared_bot_token
    try:
        path = bale.api_call(token, "getFile", {"file_id": meta["id"]})["file_path"]
        r = httpx.get(f"https://tapi.bale.ai/file/bot{token}/{path}", timeout=60)
        r.raise_for_status()
    except Exception:  # noqa: BLE001
        raise HTTPException(502, "دریافت فایل از بله ممکن نشد؛ اگر ربات را از اشتراکی به اختصاصی (یا برعکس) برده‌اید، فایل‌های قبلی در دسترس نیستند")
    name = meta.get("name") or "file"
    from urllib.parse import quote
    return Response(r.content, media_type="application/octet-stream",
                    headers={"Content-Disposition": f"attachment; filename=\"file\"; filename*=UTF-8''{quote(name)}"})


# ---------- saved replies (inbox) ----------
class SavedReplyIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


def _mine(bot_id: int, user: User, db: Session) -> Bot:
    bot = db.get(Bot, bot_id)
    if not bot or bot.user_id != user.id:
        raise HTTPException(404, "ربات یافت نشد")
    return bot


@router.get("/api/bots/{bot_id}/inbox/replies")
def saved_replies(bot_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from .models import SavedReply
    _mine(bot_id, user, db)
    return [{"id": r.id, "text": r.text} for r in db.scalars(select(SavedReply).where(SavedReply.bot_id == bot_id).order_by(SavedReply.id))]


@router.post("/api/bots/{bot_id}/inbox/replies")
def add_saved_reply(bot_id: int, body: SavedReplyIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from .models import SavedReply
    _mine(bot_id, user, db)
    text = body.text.strip()
    if not text:
        raise HTTPException(422, "متن پاسخ خالی است")
    if db.scalar(select(func.count()).select_from(SavedReply).where(SavedReply.bot_id == bot_id)) >= 30:
        raise HTTPException(409, "حداکثر ۳۰ پاسخ آماده می‌توانید داشته باشید")
    r = SavedReply(bot_id=bot_id, text=text)
    db.add(r)
    db.commit()
    return {"id": r.id, "text": r.text}


@router.delete("/api/bots/{bot_id}/inbox/replies/{reply_id}")
def delete_saved_reply(bot_id: int, reply_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from .models import SavedReply
    _mine(bot_id, user, db)
    r = db.get(SavedReply, reply_id)
    if not r or r.bot_id != bot_id:
        raise HTTPException(404, "پاسخ آماده یافت نشد")
    db.delete(r)
    db.commit()
    return {"ok": True}


# ---------- feedback over time ----------
@router.get("/api/bots/{bot_id}/feedback/stats")
def feedback_stats(bot_id: int, sandbox: bool = False, weeks: int = 12, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Per feedback block: the average rating per week (Saturday to Friday, newest last), overall, and per aspect."""
    from datetime import timedelta

    from .dates import jalali_str, persian_weekday
    _mine(bot_id, user, db)
    ver = db.scalars(select(BotVersion).where(BotVersion.bot_id == bot_id).order_by(BotVersion.version.desc())).first()
    blocks = [b for b in BotSpec.model_validate(ver.spec).blocks if b.type == "feedback"] if ver else []
    weeks = max(1, min(weeks, 52))
    today = now_tehran().date()
    this_sat = today - timedelta(days=persian_weekday(today))
    starts = [this_sat - timedelta(weeks=k) for k in range(weeks - 1, -1, -1)]
    out = []
    for b in blocks:
        rows = db.scalars(select(Record).where(Record.bot_id == bot_id, Record.collection == b.id, Record.sandbox == sandbox)).all()
        rated = [r for r in rows if isinstance(r.data.get("rating"), int)]

        def day(r):  # the Tehran date it was given (the record's own timestamp; created_at as a fallback, read as UTC)
            from datetime import datetime, timezone
            try:
                return datetime.fromisoformat(r.data["_at"]).date()
            except (KeyError, ValueError, TypeError):
                c = r.created_at if r.created_at.tzinfo else r.created_at.replace(tzinfo=timezone.utc)
                return c.astimezone(now_tehran().tzinfo).date()

        series = []
        for s in starts:
            vals = [r.data["rating"] for r in rated if s <= day(r) < s + timedelta(days=7)]
            series.append({"week": jalali_str(s), "count": len(vals), "avg": round(sum(vals) / len(vals), 2) if vals else None})
        aspects = {}
        for a in b.aspects:
            vals = [r.data["ratings"][a] for r in rated if isinstance(r.data.get("ratings"), dict) and a in r.data["ratings"]]
            aspects[a] = round(sum(vals) / len(vals), 2) if vals else None
        out.append({"block": b.id, "title": b.title, "count": len(rated),
                    "avg": round(sum(r.data["rating"] for r in rated) / len(rated), 2) if rated else None, "weeks": series, "aspects": aspects})
    return out
