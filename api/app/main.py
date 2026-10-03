from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import engine as bot_engine
from .auth import check_password, current_user, hash_password, make_token
from .config import settings
from .db import Base, engine, get_db
from .models import Bot, BotVersion, ChatSession, Record, User
from .spec import BotSpec
from .store import SqlStore
from .templates import TEMPLATES, load_template


@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="BuildX Bot Builder", lifespan=lifespan)
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


@app.post("/api/auth/register")
def register(body: Credentials, db: Session = Depends(get_db)):
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
    return [bot_out(b, db) | {"spec": None} for b in bots]


@app.post("/api/bots")
def create_bot(body: NewBot, user: User = Depends(current_user), db: Session = Depends(get_db)):
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
    spec = BotSpec.model_validate(latest_version(bot.id, db).spec)
    row = db.scalar(select(ChatSession).where(ChatSession.bot_id == bot.id, ChatSession.key == "sim:" + body.session_id))
    if row is None:
        row = ChatSession(bot_id=bot.id, key="sim:" + body.session_id, state=bot_engine.new_session())
        db.add(row)
    state = dict(row.state)
    actions = bot_engine.handle(spec, state, body.text, SqlStore(db, bot.id, sandbox=True))
    row.state = state
    db.commit()
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
    return [{"id": r.id, "collection": r.collection, "data": r.data, "created_at": r.created_at.isoformat()} for r in db.scalars(q)]


# ---------- static frontend (Next.js export copied to api/static at build time) ----------
import os  # noqa: E402

from fastapi.staticfiles import StaticFiles  # noqa: E402

_static = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.isdir(_static):
    app.mount("/", StaticFiles(directory=_static, html=True), name="web")
