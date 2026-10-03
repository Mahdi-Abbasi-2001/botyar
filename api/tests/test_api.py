import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


def setup_module():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def test_full_flow():
    c = TestClient(app)
    assert c.post("/api/auth/register", json={"email": "a@b.com", "password": "123456"}).status_code == 200
    assert c.post("/api/auth/register", json={"email": "a@b.com", "password": "123456"}).status_code == 409
    assert c.post("/api/auth/login", json={"email": "a@b.com", "password": "wrong1"}).status_code == 401
    tok = c.post("/api/auth/login", json={"email": "a@b.com", "password": "123456"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert c.get("/api/bots").status_code == 401
    bot = c.post("/api/bots", json={"template": "workshop"}, headers=h).json()
    sid = "t1"
    for t in ["/start", "m:0", "s:thu1", "سارا", "09121234567"]:
        r = c.post(f"/api/bots/{bot['id']}/simulate", json={"session_id": sid, "text": t}, headers=h).json()
    assert any("ثبت‌نام شما" in a["text"] for a in r["actions"])
    recs = c.get(f"/api/bots/{bot['id']}/records?sandbox=true", headers=h).json()
    assert recs[0]["data"]["name"] == "سارا"
    # another user cannot see it
    tok2 = c.post("/api/auth/register", json={"email": "x@y.com", "password": "123456"}).json()["token"]
    assert c.get(f"/api/bots/{bot['id']}", headers={"Authorization": f"Bearer {tok2}"}).status_code == 404
