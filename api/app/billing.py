"""Plans, usage limits and upgrade requests.

The limits are enforced (bots, live bots, AI requests, customers per live bot). Prices are PROPOSED numbers (see
docs/business-plan.md); they are shown as «پیشنهادی» until the founder has validated them with owners. There is no payment
gateway yet: in demo mode (settings.billing_demo) an upgrade simulates a successful payment and activates the plan at once;
otherwise an owner sends an upgrade request and an admin (ADMIN_EMAILS) activates the plan by hand."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auth import current_user
from .config import settings
from .db import get_db
from .models import Bot, BuilderRun, CustomerSeen, PlanPayment, Publication, Subscription, TgPublication, UpgradeRequest, User

router = APIRouter()
WINDOW_DAYS = 30  # "per month" = the last 30 days, so there is no calendar-month edge case

PLANS: dict[str, dict] = {
    "free": {"name": "رایگان", "price": 0, "bots": 3, "live_bots": 1, "customers": 100, "ai_requests": 30,
             "tagline": "برای امتحان و ربات‌های کوچک"},
    "basic": {"name": "پایه", "price": 149_000, "bots": 3, "live_bots": 1, "customers": 500, "ai_requests": 100,
              "tagline": "یک کسب‌وکار کوچک با مشتری‌های ثابت"},
    "pro": {"name": "حرفه‌ای", "price": 349_000, "bots": 10, "live_bots": 3, "customers": 3000, "ai_requests": 300,
            "tagline": "کسب‌وکار پرمشتری یا چند شعبه"},
    "agency": {"name": "آژانس", "price": 1_490_000, "bots": 50, "live_bots": 10, "customers": 3000, "ai_requests": 1500,
               "tagline": "برای فریلنسرها و آژانس‌هایی که ربات مشتری می‌سازند"},
}
INCLUDED = [  # every plan has every feature; plans differ only by the limits above
    "ساخت و اصلاح ربات با توضیح فارسی، با تست خودکار پیش از انتشار",
    "نوبت‌دهی، سفارش و فروشگاه، پرسش و پاسخ، فرم، آزمون، زیرمنو، پیام به مدیر، نظرسنجی",
    "پنل مدیر: ثبت‌ها، لغو و وضعیت سفارش، پیام‌ها، اطلاعیه، مشتریان، خروجی اکسل",
    "یادآوری نوبت و پرداخت آنلاین داخل بله (با کیف پول خودتان)",
]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def plan_key(db: Session, user_id: int) -> str:
    sub = db.scalars(select(Subscription).where(Subscription.user_id == user_id)).first()
    return sub.plan if sub and sub.plan in PLANS else "free"


def limits(db: Session, user_id: int) -> dict:
    return PLANS[plan_key(db, user_id)]


def is_admin(user: User) -> bool:
    return user.email.lower() in {e.strip().lower() for e in settings.admin_emails.split(",") if e.strip()}


def ai_requests_30d(db: Session, user_id: int) -> int:
    since = now_utc() - timedelta(days=WINDOW_DAYS)
    return db.scalar(select(func.count()).select_from(BuilderRun).join(Bot, Bot.id == BuilderRun.bot_id)
                     .where(Bot.user_id == user_id, BuilderRun.created_at >= since)) or 0


def customers_30d(db: Session, bot_id: int) -> int:
    since = now_utc() - timedelta(days=WINDOW_DAYS)
    return db.scalar(select(func.count()).select_from(CustomerSeen).where(CustomerSeen.bot_id == bot_id, CustomerSeen.last_seen >= since)) or 0


def _live_ids(db: Session, bot_ids: list[int]) -> set[int]:
    """Bots currently published on Bale and/or Telegram."""
    ids = bot_ids or [0]
    return {p.bot_id for p in db.scalars(select(Publication).where(Publication.bot_id.in_(ids)))} | \
        {p.bot_id for p in db.scalars(select(TgPublication).where(TgPublication.bot_id.in_(ids)))}


def usage(db: Session, user_id: int) -> dict:
    bots = db.scalars(select(Bot).where(Bot.user_id == user_id)).all()
    live = _live_ids(db, [b.id for b in bots])
    return {"bots": len(bots), "live_bots": len(live), "ai_requests": ai_requests_30d(db, user_id),
            "per_bot": [{"id": b.id, "name": b.name, "live": b.id in live, "customers": customers_30d(db, b.id)} for b in bots]}


def over(limit_name: str, plan: dict) -> HTTPException:
    msgs = {"bots": f"سقف ساخت ربات در پلن «{plan['name']}» ({plan['bots']} ربات) پر شده است. برای ربات بیشتر پلن را ارتقا دهید.",
            "live_bots": f"در پلن «{plan['name']}» فقط {plan['live_bots']} ربات می‌تواند هم‌زمان منتشر باشد. ربات دیگری را لغو انتشار کنید یا پلن را ارتقا دهید.",
            "ai_requests": f"سقف درخواست‌های ماهانه‌ی ایجنت در پلن «{plan['name']}» ({plan['ai_requests']} درخواست در ۳۰ روز) پر شده است. پلن را ارتقا دهید."}
    return HTTPException(402, msgs[limit_name])


def check_new_bot(db: Session, user: User):
    plan = limits(db, user.id)
    if db.scalar(select(func.count()).select_from(Bot).where(Bot.user_id == user.id)) >= plan["bots"]:
        raise over("bots", plan)


def check_ai_request(db: Session, user: User):
    plan = limits(db, user.id)
    if ai_requests_30d(db, user.id) >= plan["ai_requests"]:
        raise over("ai_requests", plan)


def check_publish(db: Session, user: User, bot_id: int):
    plan = limits(db, user.id)
    mine = [b.id for b in db.scalars(select(Bot).where(Bot.user_id == user.id))]
    live = _live_ids(db, mine)
    if bot_id not in live and len(live) >= plan["live_bots"]:
        raise over("live_bots", plan)


FULL_TEXT = "ظرفیت ماهانه‌ی این ربات تکمیل شده است و فعلاً مشتری جدید نمی‌پذیرد. لطفاً بعداً دوباره امتحان کنید."


def track_customer(db: Session, bot: Bot, key: str, name: str) -> bool:
    """Record this customer's activity. Returns False when a NEW customer would exceed the owner's monthly cap
    (customers who were already active in the last 30 days are never blocked)."""
    now = now_utc()
    row = db.scalars(select(CustomerSeen).where(CustomerSeen.bot_id == bot.id, CustomerSeen.key == key)).first()
    since = now - timedelta(days=WINDOW_DAYS)
    returning_active = row is not None and _aware(row.last_seen) >= since
    if not returning_active and customers_30d(db, bot.id) >= limits(db, bot.user_id)["customers"]:
        return False
    if row is None:
        db.add(CustomerSeen(bot_id=bot.id, key=key, name=name[:80], first_seen=now, last_seen=now, messages=1))
    else:
        row.last_seen, row.messages = now, (row.messages or 0) + 1
        if name:
            row.name = name[:80]
    return True


# ---------- API ----------
@router.get("/api/plans")
def list_plans():
    return {"plans": [{"key": k, **v} for k, v in PLANS.items()], "included": INCLUDED, "window_days": WINDOW_DAYS,
            "prices_proposed": True, "currency": "تومان", "billing": "ماهانه", "demo": settings.billing_demo}


@router.get("/api/me/plan")
def my_plan(user: User = Depends(current_user), db: Session = Depends(get_db)):
    key = plan_key(db, user.id)
    pending = db.scalars(select(UpgradeRequest).where(UpgradeRequest.user_id == user.id, UpgradeRequest.status == "pending")).first()
    pays = db.scalars(select(PlanPayment).where(PlanPayment.user_id == user.id).order_by(PlanPayment.id.desc()).limit(10)).all()
    return {"plan": {"key": key, **PLANS[key]}, "usage": usage(db, user.id), "pending_request": pending.plan if pending else None,
            "admin": is_admin(user), "demo": settings.billing_demo,
            "payments": [{"id": p.id, "plan": p.plan, "name": PLANS[p.plan]["name"], "amount": p.amount, "simulated": p.simulated, "at": p.created_at.isoformat()} for p in pays]}


class UpgradeIn(BaseModel):
    plan: str
    note: str = Field(default="", max_length=500)


def _set_plan(db: Session, user_id: int, plan: str, note: str):
    sub = db.scalars(select(Subscription).where(Subscription.user_id == user_id)).first()
    if sub is None:
        db.add(Subscription(user_id=user_id, plan=plan, note=note))
    else:
        sub.plan, sub.note, sub.updated_at = plan, note, now_utc()


@router.post("/api/me/upgrade")
def request_upgrade(body: UpgradeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.plan not in PLANS or body.plan == "free":
        raise HTTPException(422, "پلن نامعتبر است")
    if settings.billing_demo:
        # DEMO: no payment gateway exists, so the payment is simulated and the plan is activated at once. Nothing is charged.
        _set_plan(db, user.id, body.plan, "demo payment")
        db.add(PlanPayment(user_id=user.id, plan=body.plan, amount=PLANS[body.plan]["price"], simulated=True))
        for r in db.scalars(select(UpgradeRequest).where(UpgradeRequest.user_id == user.id, UpgradeRequest.status == "pending")):
            r.status = "approved"
        db.commit()
        return {"ok": True, "simulated": True, "plan": body.plan, "amount": PLANS[body.plan]["price"]}
    if db.scalars(select(UpgradeRequest).where(UpgradeRequest.user_id == user.id, UpgradeRequest.status == "pending")).first():
        raise HTTPException(409, "درخواست ارتقای قبلی شما هنوز در حال بررسی است.")
    db.add(UpgradeRequest(user_id=user.id, plan=body.plan, note=body.note.strip()))
    db.commit()
    return {"ok": True, "simulated": False}


@router.post("/api/me/plan/cancel")
def cancel_plan(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Back to the free plan. Bots that are already live stay live (nothing is unpublished), but new bots and publications follow the free limits."""
    _set_plan(db, user.id, "free", "cancelled by owner")
    db.commit()
    return {"ok": True, "plan": "free"}


def _admin(user: User = Depends(current_user)) -> User:
    if not is_admin(user):
        raise HTTPException(404, "یافت نشد")  # not 403: do not reveal that the page exists
    return user


@router.get("/api/admin/upgrades")
def list_upgrades(_: User = Depends(_admin), db: Session = Depends(get_db)):
    rows = db.execute(select(UpgradeRequest, User).join(User, User.id == UpgradeRequest.user_id).order_by(UpgradeRequest.id.desc()).limit(100)).all()
    return [{"id": r.id, "email": u.email, "plan": r.plan, "current": plan_key(db, u.id), "note": r.note, "status": r.status,
             "created_at": r.created_at.isoformat()} for r, u in rows]


class Decision(BaseModel):
    approve: bool


@router.post("/api/admin/upgrades/{rid}")
def decide(rid: int, body: Decision, _: User = Depends(_admin), db: Session = Depends(get_db)):
    r = db.get(UpgradeRequest, rid)
    if r is None or r.status != "pending":
        raise HTTPException(404, "درخواست یافت نشد یا قبلاً بررسی شده است")
    r.status = "approved" if body.approve else "rejected"
    if body.approve:
        _set_plan(db, r.user_id, r.plan, "approved by admin")
    db.commit()
    return {"ok": True}
