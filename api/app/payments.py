"""The owner connects a Bale wallet token so customers can pay inside the bot. The money goes to the wallet behind the token."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import bale
from .auth import current_user
from .db import get_db
from .models import Bot, PaymentConfig, Publication, User

router = APIRouter()
TEST_PREFIX = "WALLET-TEST-"


class WalletIn(BaseModel):
    wallet_token: str = Field(min_length=8, max_length=200)


def _bot(bot_id: int, user: User, db: Session) -> Bot:
    bot = db.get(Bot, bot_id)
    if not bot or bot.user_id != user.id:
        raise HTTPException(404, "ربات یافت نشد")
    return bot


@router.get("/api/bots/{bot_id}/payment")
def payment_status(bot_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _bot(bot_id, user, db)
    cfg = db.scalars(select(PaymentConfig).where(PaymentConfig.bot_id == bot_id)).first()
    pub = db.scalars(select(Publication).where(Publication.bot_id == bot_id)).first()
    test = bool(cfg) and bale.decrypt(cfg.token_enc).startswith(TEST_PREFIX)
    return {"configured": cfg is not None, "test": test, "mode": pub.mode if pub else None,
            "active": bool(pub) and bool(cfg) and (pub.mode == "own" or test)}


@router.put("/api/bots/{bot_id}/payment")
def set_payment(bot_id: int, body: WalletIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _bot(bot_id, user, db)
    tok = body.wallet_token.strip()
    if " " in tok:
        raise HTTPException(422, "توکن کیف پول نباید فاصله داشته باشد.")
    cfg = db.scalars(select(PaymentConfig).where(PaymentConfig.bot_id == bot_id)).first()
    if cfg is None:
        db.add(PaymentConfig(bot_id=bot_id, token_enc=bale.encrypt(tok)))
    else:
        cfg.token_enc = bale.encrypt(tok)
    db.commit()
    return payment_status(bot_id, user, db)


@router.delete("/api/bots/{bot_id}/payment")
def clear_payment(bot_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _bot(bot_id, user, db)
    cfg = db.scalars(select(PaymentConfig).where(PaymentConfig.bot_id == bot_id)).first()
    if cfg:
        db.delete(cfg)
        db.commit()
    return {"ok": True}
