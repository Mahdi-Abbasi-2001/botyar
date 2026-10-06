"""Accounts sign in with a username; accounts made earlier with an email keep working."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def c():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as client:
        yield client


def test_register_and_sign_in_with_a_username(c):
    r = c.post("/api/auth/register", json={"username": "Mahdi_1", "password": "123456"})
    assert r.status_code == 200 and r.json()["username"] == "mahdi_1"          # stored lower-case
    for name in ("mahdi_1", "MAHDI_1", "  mahdi_1 "):                           # case and stray spaces don't matter
        assert c.post("/api/auth/login", json={"username": name, "password": "123456"}).status_code == 200
    tok = c.post("/api/auth/login", json={"username": "mahdi_1", "password": "123456"}).json()["token"]
    assert c.get("/api/me", headers={"Authorization": f"Bearer {tok}"}).json()["username"] == "mahdi_1"


def test_taken_username_and_wrong_password_are_explained(c):
    c.post("/api/auth/register", json={"username": "cafe.nimkat", "password": "123456"})
    r = c.post("/api/auth/register", json={"username": "Cafe.Nimkat", "password": "abcdef"})
    assert r.status_code == 409 and "نام کاربری" in r.json()["detail"]
    r = c.post("/api/auth/login", json={"username": "cafe.nimkat", "password": "wrong1"})
    assert r.status_code == 401 and r.json()["detail"] == "نام کاربری یا رمز عبور اشتباه است"
    assert c.post("/api/auth/login", json={"username": "nobody", "password": "123456"}).status_code == 401


@pytest.mark.parametrize("bad", ["ab", "1abc", "a@b.com", "علی", "has space", "_lead", "a" * 33, "dash-ed"])
def test_bad_usernames_get_the_rule(c, bad):
    r = c.post("/api/auth/register", json={"username": bad, "password": "123456"})
    assert r.status_code == 422 and "۳ تا ۳۲" in r.json()["detail"]


def test_old_accounts_sign_in_with_the_email_they_used_before(c):
    """After the migration an older account's username is its old email; typing it still works."""
    from app.auth import hash_password
    from app.db import SessionLocal
    from app.models import User

    with SessionLocal() as db:
        db.add(User(username="old@example.com", password_hash=hash_password("123456")))
        db.commit()
    assert c.post("/api/auth/login", json={"username": "Old@Example.com", "password": "123456"}).status_code == 200
    assert c.post("/api/auth/register", json={"username": "old@example.com", "password": "123456"}).status_code == 422  # new ones can't


def test_the_api_no_longer_knows_email(c):
    assert c.post("/api/auth/register", json={"email": "new@example.com", "password": "123456"}).status_code == 422
    tok = c.post("/api/auth/register", json={"username": "fresh", "password": "123456"}).json()["token"]
    assert c.get("/api/me", headers={"Authorization": f"Bearer {tok}"}).json() == {"username": "fresh"}


def test_migration_turns_an_old_users_table_into_usernames(tmp_path):
    """A database made before usernames: users.email with a unique index and existing accounts."""
    from sqlalchemy import create_engine, inspect, text

    from app.migrate import users_email_to_username

    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255) NOT NULL, password_hash VARCHAR(255), created_at DATETIME)"))
        conn.execute(text("CREATE UNIQUE INDEX ix_users_email ON users (email)"))
        conn.execute(text("INSERT INTO users (id, email, password_hash) VALUES (1, 'Owner@Cafe.ir', 'h1'), (2, 'b@x.com', 'h2')"))
    assert users_email_to_username(eng) is True
    insp = inspect(eng)
    cols = {c["name"] for c in insp.get_columns("users")}
    assert "email" not in cols and "username" in cols
    with eng.connect() as conn:
        assert conn.execute(text("SELECT id, username, password_hash FROM users ORDER BY id")).all() == [(1, "owner@cafe.ir", "h1"), (2, "b@x.com", "h2")]
    assert any(ix["column_names"] == ["username"] and ix["unique"] for ix in insp.get_indexes("users"))
    with eng.begin() as conn, pytest.raises(Exception):  # usernames stay unique
        conn.execute(text("INSERT INTO users (id, username, password_hash) VALUES (3, 'b@x.com', 'h3')"))
    assert users_email_to_username(eng) is False  # running again changes nothing


def test_register_needs_an_identifier(c):
    assert c.post("/api/auth/register", json={"password": "123456"}).status_code == 422
    assert c.post("/api/auth/login", json={"password": "123456"}).status_code == 422
