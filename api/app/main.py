import copy
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import engine as bot_engine
from . import faq_index
from . import billing
from .auth import check_password, current_user, hash_password, make_token
from .config import settings
from .db import Base, engine, get_db
from .models import Bot, BotVersion, ChatSession, Record, User
from .spec import BotSpec
from .store import SqlStore
from .templates import TEMPLATES, load_template


INTERRUPTED = {"message": "ساخت بر اثر راه‌اندازی دوباره‌ی سرور متوقف شد. لطفاً درخواستتان را دوباره بفرستید."}
RUN_TIMEOUT_MIN = 6  # a normal run takes well under a minute


def _fail_interrupted_runs(older_than_min: int = 0):
    """A restart kills background threads and leaves runs 'running' forever; that would lock the bot out of the agent."""
    from datetime import datetime, timedelta, timezone

    from .db import SessionLocal

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=older_than_min)
    with SessionLocal() as db:
        for r in db.scalars(select(BuilderRun).where(BuilderRun.status == "running")):
            created = r.created_at if r.created_at.tzinfo else r.created_at.replace(tzinfo=timezone.utc)
            if created <= cutoff:
                r.status, r.result = "failed", INTERRUPTED
        db.commit()


@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    _fail_interrupted_runs()
    import threading

    from .bale import ensure_shared_webhook

    threading.Thread(target=ensure_shared_webhook, daemon=True).start()  # no-op unless PUBLIC_BASE_URL is set
    from .telegram import ensure_shared_webhook as ensure_tg_webhook

    threading.Thread(target=ensure_tg_webhook, daemon=True).start()  # no-op unless the Telegram relay is configured too
    if settings.public_base_url:  # production only: tests and local dev must not send reminders
        from .outreach import start_scheduler

        start_scheduler()
    yield


_prod = bool(settings.public_base_url)  # production: do not publish the API schema / interactive docs
app = FastAPI(title="Botyar", lifespan=lifespan, docs_url=None if _prod else "/docs", redoc_url=None if _prod else "/redoc",
              openapi_url=None if _prod else "/openapi.json")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"ok": True}


# ---------- auth ----------
class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


_reg_hits: dict[str, list[float]] = {}


def client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    return xff.split(",")[-1].strip() if xff else (request.client.host if request.client else "?")  # rightmost = added by our proxy


@app.post("/api/auth/register")
def register(body: Credentials, request: Request, db: Session = Depends(get_db)):
    import time

    ip, now_ = client_ip(request), time.time()
    hits = [t for t in _reg_hits.get(ip, []) if now_ - t < 3600]
    if len(hits) >= settings.register_per_ip_hour:
        raise HTTPException(429, "تعداد ثبت‌نام از این شبکه زیاد بوده؛ کمی بعد دوباره تلاش کنید")
    _reg_hits[ip] = hits + [now_]
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "این ایمیل قبلاً ثبت شده است")
    user = User(email=email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    return {"token": make_token(user.id), "email": user.email}


@app.post("/api/auth/login")
def login(body: Credentials, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not check_password(body.password, user.password_hash):
        raise HTTPException(401, "ایمیل یا رمز عبور اشتباه است")
    return {"token": make_token(user.id), "email": user.email}


@app.get("/api/me")
def me(user: User = Depends(current_user)):
    return {"email": user.email}


# ---------- bots ----------
def own_bot(bot_id: int, user: User, db: Session) -> Bot:
    bot = db.get(Bot, bot_id)
    if not bot or bot.user_id != user.id:
        raise HTTPException(404, "ربات یافت نشد")
    return bot


def latest_version(bot_id: int, db: Session) -> BotVersion:
    return db.scalars(select(BotVersion).where(BotVersion.bot_id == bot_id).order_by(BotVersion.version.desc())).first()


def bot_out(bot: Bot, db: Session):
    v = latest_version(bot.id, db)
    return {"id": bot.id, "name": bot.name, "version": v.version if v else 0, "spec": v.spec if v else None}


class NewBot(BaseModel):
    template: str


@app.get("/api/templates")
def templates():
    return [{"key": k, "name": v["name"]} for k, v in TEMPLATES.items()]


@app.get("/api/bots")
def list_bots(user: User = Depends(current_user), db: Session = Depends(get_db)):
    bots = db.scalars(select(Bot).where(Bot.user_id == user.id).order_by(Bot.id.desc())).all()
    return [_bot_card(b, db) for b in bots]


def _bot_card(bot: Bot, db: Session) -> dict:
    """What the "my bots" list shows at a glance: live where (and which version), latest tests, last change."""
    from . import bale
    from .models import VersionTests

    v = latest_version(bot.id, db)
    out = {"id": bot.id, "name": bot.name, "version": v.version if v else 0, "spec": None, "tests": None, "live": [], "last_change": None}
    if v is None:
        return out
    t = db.scalars(select(VersionTests).where(VersionTests.bot_id == bot.id, VersionTests.version == v.version)).first()
    if t is not None:
        out["tests"] = {"passed": sum(1 for r in t.results if r["passed"]), "total": len(t.results)}
    for ch in bale.CHANNELS.values():
        p = db.scalars(select(ch.pub_model).where(ch.pub_model.bot_id == bot.id)).first()
        if p is not None:
            out["live"].append({"messenger": ch.name, "version": p.version})
    out["last_change"] = {"note": (v.note or "")[:120], "at": v.created_at.isoformat()}
    return out


@app.post("/api/bots")
def create_bot(body: NewBot, user: User = Depends(current_user), db: Session = Depends(get_db)):
    billing.check_new_bot(db, user)
    if body.template not in TEMPLATES:
        raise HTTPException(400, "قالب نامعتبر است")
    spec = load_template(body.template)
    bot = Bot(user_id=user.id, name=spec.name)
    db.add(bot)
    db.flush()
    db.add(BotVersion(bot_id=bot.id, version=1, spec=spec.model_dump(), note="ساخته شده از قالب"))
    db.commit()
    return bot_out(bot, db)


@app.get("/api/bots/{bot_id}")
def get_bot(bot_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return bot_out(own_bot(bot_id, user, db), db)


# ---------- simulator ----------
class SimMessage(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    text: str = Field(max_length=2000)


@app.post("/api/bots/{bot_id}/simulate")
def simulate(bot_id: int, body: SimMessage, user: User = Depends(current_user), db: Session = Depends(get_db)):
    bot = own_bot(bot_id, user, db)
    ver = latest_version(bot.id, db)
    if ver is None:
        raise HTTPException(400, "این ربات هنوز ساخته نشده است")
    spec = BotSpec.model_validate(ver.spec)
    row = db.scalar(select(ChatSession).where(ChatSession.bot_id == bot.id, ChatSession.key == "sim:" + body.session_id))
    if row is None:
        row = ChatSession(bot_id=bot.id, key="sim:" + body.session_id, state=bot_engine.new_session())
        db.add(row)
    state = copy.deepcopy(row.state)  # a shallow copy would hide in-place edits from SQLAlchemy's change detection
    state["cust"] = "sim:" + body.session_id
    state["pay_ok"] = state["pay_sim"] = True  # the simulator shows a fake "pay" button; real invoices exist only in Bale
    actions = bot_engine.handle(spec, state, body.text, SqlStore(db, bot.id, sandbox=True), matcher=faq_index.matcher_for(db, bot.id, spec))
    row.state = state
    db.commit()
    from . import media

    for i, a in enumerate(actions):  # the phone preview shows which file would be sent (the real file only goes out on Bale)
        if a.get("type") == "media":
            a.update(media.describe(db, bot.id, a["block"]))
        elif str(a.get("type", "")).startswith("anon_"):  # pairing needs two real customers: the preview only explains it
            actions[i] = {"type": "send", "text": "(گفتگوی ناشناس فقط بین دو مشتری واقعی در بله یا تلگرام کار می‌کند؛ اینجا نمونه‌اش را نمی‌شود دید.)", "buttons": []}
    return {"actions": actions}


@app.post("/api/bots/{bot_id}/simulate/reset")
def reset_sandbox(bot_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    bot = own_bot(bot_id, user, db)
    db.execute(delete(Record).where(Record.bot_id == bot.id, Record.sandbox.is_(True)))
    db.execute(delete(ChatSession).where(ChatSession.bot_id == bot.id, ChatSession.key.like("sim:%")))
    db.commit()
    return {"ok": True}


@app.get("/api/bots/{bot_id}/records")
def records(bot_id: int, sandbox: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    bot = own_bot(bot_id, user, db)
    q = select(Record).where(Record.bot_id == bot.id, Record.sandbox == sandbox).order_by(Record.id.desc()).limit(500)
    return [{"id": r.id, "collection": r.collection, "data": {k: v for k, v in r.data.items() if not k.startswith("_")},
             "created_at": r.created_at.isoformat()} for r in db.scalars(q)]


# ---------- builder agent ----------
from fastapi import BackgroundTasks  # noqa: E402

from .agent import run_builder  # noqa: E402
from .models import BuilderMessage, BuilderRun, LlmCall, VersionTests  # noqa: E402

DAILY_RUN_LIMIT = 40  # per user per 24h: protects the OpenAI budget while the demo is public


class BuilderIn(BaseModel):
    text: str = Field(min_length=2, max_length=3000)


@app.post("/api/bots/draft")
def create_draft(user: User = Depends(current_user), db: Session = Depends(get_db)):
    billing.check_new_bot(db, user)
    bot = Bot(user_id=user.id, name="ربات جدید")
    db.add(bot)
    db.commit()
    return {"id": bot.id, "name": bot.name, "version": 0, "spec": None}


@app.post("/api/bots/{bot_id}/builder")
def builder_send(bot_id: int, body: BuilderIn, tasks: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from datetime import datetime, timedelta, timezone

    bot = own_bot(bot_id, user, db)
    _fail_interrupted_runs(RUN_TIMEOUT_MIN)
    running = db.scalar(select(BuilderRun).where(BuilderRun.bot_id == bot.id, BuilderRun.status == "running"))
    if running:
        raise HTTPException(409, "ایجنت هنوز در حال کار روی درخواست قبلی است")
    billing.check_ai_request(db, user)
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    used = db.scalar(select(func.count()).select_from(BuilderRun).join(Bot, Bot.id == BuilderRun.bot_id).where(Bot.user_id == user.id, BuilderRun.created_at >= since))
    if used >= DAILY_RUN_LIMIT:
        raise HTTPException(429, "سقف درخواست‌های روزانه پر شده است؛ فردا دوباره تلاش کنید")
    if db.scalar(select(func.count()).select_from(BuilderRun).where(BuilderRun.created_at >= since)) >= settings.global_daily_runs:
        raise HTTPException(503, "ظرفیت امروز ایجنت تکمیل شده است؛ فردا دوباره تلاش کنید")
    run = BuilderRun(bot_id=bot.id, status="running", events=[], result={})
    db.add(run)
    db.commit()
    tasks.add_task(run_builder, run.id, bot.id, body.text)
    return {"run_id": run.id}


@app.get("/api/bots/{bot_id}/builder/runs/{run_id}")
def builder_run(bot_id: int, run_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    own_bot(bot_id, user, db)
    run = db.get(BuilderRun, run_id)
    if not run or run.bot_id != bot_id:
        raise HTTPException(404, "اجرا یافت نشد")
    return {"id": run.id, "status": run.status, "events": run.events, "result": run.result}


@app.get("/api/bots/{bot_id}/builder/active")
def builder_active(bot_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Lets the page resume the live progress view after a refresh or when reopening the bot mid-build."""
    own_bot(bot_id, user, db)
    _fail_interrupted_runs(RUN_TIMEOUT_MIN)
    run = db.scalar(select(BuilderRun).where(BuilderRun.bot_id == bot_id, BuilderRun.status == "running").order_by(BuilderRun.id.desc()))
    return {"run_id": run.id if run else None, "events": run.events if run else []}


@app.get("/api/bots/{bot_id}/builder/messages")
def builder_messages(bot_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    own_bot(bot_id, user, db)
    rows = db.scalars(select(BuilderMessage).where(BuilderMessage.bot_id == bot_id).order_by(BuilderMessage.id)).all()
    return [{"role": m.role, "content": m.content} for m in rows]


@app.get("/api/bots/{bot_id}/tests")
def bot_tests(bot_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    own_bot(bot_id, user, db)
    t = db.scalars(select(VersionTests).where(VersionTests.bot_id == bot_id).order_by(VersionTests.version.desc())).first()
    return {"version": t.version, "results": t.results} if t else {"version": 0, "results": []}


@app.get("/api/bots/{bot_id}/cost")
def bot_cost(bot_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    own_bot(bot_id, user, db)
    rows = db.execute(select(LlmCall.step, func.count(), func.sum(LlmCall.cost_usd), func.sum(LlmCall.input_tokens), func.sum(LlmCall.output_tokens)).where(LlmCall.bot_id == bot_id).group_by(LlmCall.step)).all()
    return {"total_usd": sum(r[2] or 0 for r in rows), "by_step": [{"step": r[0], "calls": r[1], "usd": r[2], "in": r[3], "out": r[4]} for r in rows]}


@app.get("/api/bots/{bot_id}/versions")
def bot_versions(bot_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from .testing import spec_diff

    own_bot(bot_id, user, db)
    rows = db.scalars(select(BotVersion).where(BotVersion.bot_id == bot_id).order_by(BotVersion.version)).all()
    tests = {t.version: t.results for t in db.scalars(select(VersionTests).where(VersionTests.bot_id == bot_id))}
    out, prev = [], None
    for v in rows:
        res = tests.get(v.version, [])
        out.append({"version": v.version, "note": v.note, "created_at": v.created_at.isoformat(),
                    "diff": spec_diff(prev, v.spec), "tests_passed": sum(r["passed"] for r in res), "tests_total": len(res)})
        prev = v.spec
    return list(reversed(out))


from .publish import router as publish_router  # noqa: E402

app.include_router(publish_router)

from .catalog import router as catalog_router  # noqa: E402

app.include_router(catalog_router)

from .export import router as export_router  # noqa: E402

app.include_router(export_router)

from .records_ops import router as records_ops_router  # noqa: E402

app.include_router(records_ops_router)

from .billing import router as billing_router  # noqa: E402

app.include_router(billing_router)

from .customers import router as customers_router  # noqa: E402

app.include_router(customers_router)

from .media import router as media_router  # noqa: E402

app.include_router(media_router)

from .communities import router as communities_router  # noqa: E402

app.include_router(communities_router)

from .referral import router as referral_router  # noqa: E402

app.include_router(referral_router)

from .outreach import router as outreach_router  # noqa: E402

app.include_router(outreach_router)

from .payments import router as payments_router  # noqa: E402

app.include_router(payments_router)

from .telegram import router as telegram_router  # noqa: E402  (also registers the Telegram channel)

app.include_router(telegram_router)

# ---------- static frontend (Next.js export copied to api/static at build time) ----------
import os  # noqa: E402

from fastapi.staticfiles import StaticFiles  # noqa: E402

_static = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.isdir(_static):
    app.mount("/", StaticFiles(directory=_static, html=True), name="web")