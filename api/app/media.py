"""Photos and documents the owner attaches to message blocks. Stored in the database (small files only) and sent on Bale."""
from __future__ import annotations

import os
import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auth import current_user
from .db import get_db
from .models import Bot, BotFile, BotVersion, User
from .spec import BotSpec

router = APIRouter()
MAX_BYTES = 5 * 1024 * 1024        # per file (Bale itself allows more; the database is the limit here)
MAX_TOTAL = 25 * 1024 * 1024       # per bot
DOC_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv", ".zip"}
IMAGE_MAGIC = [(b"\xff\xd8\xff", "image/jpeg"), (b"\x89PNG\r\n\x1a\n", "image/png"), (b"RIFF", "image/webp")]


def _bot(bot_id: int, user: User, db: Session) -> Bot:
    bot = db.get(Bot, bot_id)
    if not bot or bot.user_id != user.id:
        raise HTTPException(404, "ربات یافت نشد")
    return bot


def _spec(bot_id: int, db: Session) -> BotSpec | None:
    ver = db.scalars(select(BotVersion).where(BotVersion.bot_id == bot_id).order_by(BotVersion.version.desc())).first()
    return BotSpec.model_validate(ver.spec) if ver else None


def _slots(bot_id: int, db: Session) -> dict:
    spec = _spec(bot_id, db)
    return {b.id: b for b in (spec.blocks if spec else []) if b.type == "message" and b.media != "none"}


def get_file(db: Session, bot_id: int, block_id: str) -> tuple[str, str, bytes] | None:
    """(filename, mime, bytes) for the live bot's block, or None when the owner has not uploaded anything yet."""
    f = db.scalars(select(BotFile).where(BotFile.bot_id == bot_id, BotFile.block_id == block_id)).first()
    return (f.filename, f.mime, f.data) if f else None


def describe(db: Session, bot_id: int, block_id: str) -> dict:
    f = db.scalars(select(BotFile).where(BotFile.bot_id == bot_id, BotFile.block_id == block_id)).first()
    return {"uploaded": f is not None, "filename": f.filename if f else "", "size": f.size if f else 0}


@router.get("/api/bots/{bot_id}/media")
def list_media(bot_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _bot(bot_id, user, db)
    return [{"block": b.id, "text": b.text[:60], "kind": b.media, **describe(db, bot_id, b.id)} for b in _slots(bot_id, db).values()]


def _clean_name(name: str) -> str:
    base = os.path.basename(name or "file").strip()
    base = re.sub(r"[^\w.\- ()؀-ۿ]", "_", base)[:100]
    return base or "file"


@router.put("/api/bots/{bot_id}/media/{block_id}")
async def upload_media(bot_id: int, block_id: str, file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    _bot(bot_id, user, db)
    block = _slots(bot_id, db).get(block_id)
    if block is None:
        raise HTTPException(404, "این بخش فایلی نمی‌خواهد؛ از ایجنت بخواهید برای آن «ارسال عکس» یا «ارسال فایل» بگذارد.")
    data = await file.read(MAX_BYTES + 1)
    if not data:
        raise HTTPException(422, "فایل خالی است")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "حجم فایل بیشتر از ۵ مگابایت است")
    name = _clean_name(file.filename or "")
    if block.media == "image":
        mime = next((m for sig, m in IMAGE_MAGIC if data.startswith(sig) and (m != "image/webp" or data[8:12] == b"WEBP")), None)
        if mime is None:
            raise HTTPException(422, "فقط عکس JPG، PNG یا WEBP پذیرفته می‌شود")
    else:
        ext = os.path.splitext(name)[1].lower()
        if ext not in DOC_EXT:
            raise HTTPException(422, "نوع فایل مجاز نیست (PDF، Word، Excel، PowerPoint، متن، CSV یا ZIP)")
        if ext == ".pdf" and not data.startswith(b"%PDF"):
            raise HTTPException(422, "این فایل PDF معتبر نیست")
        mime = file.content_type or "application/octet-stream"
    existing = db.scalars(select(BotFile).where(BotFile.bot_id == bot_id, BotFile.block_id == block_id)).first()
    total = db.scalar(select(func.coalesce(func.sum(BotFile.size), 0)).where(BotFile.bot_id == bot_id)) or 0
    if total - (existing.size if existing else 0) + len(data) > MAX_TOTAL:
        raise HTTPException(413, "مجموع فایل‌های این ربات از ۲۵ مگابایت بیشتر می‌شود")
    if existing is None:
        db.add(BotFile(bot_id=bot_id, block_id=block_id, kind=block.media, filename=name, mime=mime, size=len(data), data=data))
    else:
        existing.kind, existing.filename, existing.mime, existing.size, existing.data = block.media, name, mime, len(data), data
    db.commit()
    return describe(db, bot_id, block_id)


@router.delete("/api/bots/{bot_id}/media/{block_id}")
def delete_media(bot_id: int, block_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _bot(bot_id, user, db)
    f = db.scalars(select(BotFile).where(BotFile.bot_id == bot_id, BotFile.block_id == block_id)).first()
    if f:
        db.delete(f)
        db.commit()
    return {"ok": True}
