from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User

bearer = HTTPBearer(auto_error=False)


def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode()[:72], bcrypt.gensalt()).decode()


def check_password(p: str, h: str) -> bool:
    return bcrypt.checkpw(p.encode()[:72], h.encode())


def make_token(user_id: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_hours)
    return jwt.encode({"sub": str(user_id), "exp": exp}, settings.jwt_secret, algorithm="HS256")


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if cred is None:
        raise HTTPException(401, "نیاز به ورود")
    try:
        uid = int(jwt.decode(cred.credentials, settings.jwt_secret, algorithms=["HS256"])["sub"])
    except Exception:
        raise HTTPException(401, "نشست نامعتبر است")
    user = db.get(User, uid)
    if user is None:
        raise HTTPException(401, "کاربر یافت نشد")
    return user
