"""Owner actions on records from the dashboard: cancel a booking/order, move an order along
new -> preparing -> ready -> done. The rules live in engine.cancel_record / engine.set_order_status (shared with the
customer flow); this module only authorises, takes the per-bot lock, saves, and delivers the customer messages."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
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
    action: Literal["cancel", "status"]
    status: str | None = None  # preparing | ready | done (for action="status")
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
    block = next((b for b in spec.blocks if b.id == rec.collection and b.type in ("booking", "catalog_order")), None)
    if block is None:
        raise HTTPException(409, "بخش مربوط به این ثبت دیگر در ربات نیست")

    store = SqlStore(db, bot_id, sandbox=rec.sandbox)
    now = now_tehran()
    with bale._locks[bot_id]:  # same lock as customers' bookings: an owner action must not interleave with a capacity check
        row = store.find(rec.collection, id=rec.id)[0]
        status_now = row.get("status")
        promoted = None
        try:
            if body.action == "cancel":
                if status_now in ("cancelled", "done"):
                    raise ValueError("این ثبت قبلاً بسته یا لغو شده است.")
                actions, promoted = engine.cancel_record(spec, store, now, block, row, by="owner", reason=body.reason)
            else:
                if not body.status:
                    raise ValueError("وضعیت جدید را مشخص کنید.")
                actions = engine.set_order_status(store, now, block, row, body.status)
        except ValueError as e:
            db.rollback()
            raise HTTPException(409, str(e))
        db.commit()

    sent = 0 if rec.sandbox else bale.send_customer_actions(db, bot_id, actions)  # simulator customers (sim:…) have no chat
    wanted = sum(a["type"] == "notify_customer" for a in actions)
    new_status = store.find(rec.collection, id=rec.id)[0]["status"]
    return {"id": rec.id, "status": new_status, "customer_messages": {"wanted": wanted, "sent": sent, "sandbox": rec.sandbox},
            "promoted": {"id": promoted["id"], "name": promoted.get("name")} if promoted else None}
