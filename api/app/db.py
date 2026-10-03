from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

_url = settings.database_url
if _url.startswith("postgres://"):
    _url = _url.replace("postgres://", "postgresql+psycopg://", 1)
elif _url.startswith("postgresql://"):
    _url = _url.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(_url, connect_args={"check_same_thread": False} if _url.startswith("sqlite") else {}, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
