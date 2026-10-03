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


def test_two_option_groups_in_a_row_survive_persistence():
    """Regression: consecutive same-step messages used to lose nested state (shallow copy hid in-place edits)."""
    from app.db import SessionLocal
    from app.models import Bot, BotVersion, User

    c = TestClient(app)
    tok = c.post("/api/auth/register", json={"email": "opt@b.com", "password": "123456"}).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    me = c.get("/api/me", headers=H).json()
    spec = {"name": "t", "welcome": "سلام", "menu": [{"label": "سفارش", "block": "o"}],
            "blocks": [{"type": "catalog_order", "id": "o", "title": "منو", "min_total": 0,
                        "items": [{"id": "tee", "name": "تی‌شرت", "price": 100000,
                                   "options": [{"name": "سایز", "choices": ["S", "M"]}, {"name": "رنگ", "choices": ["سفید", "مشکی"]}]}]}]}
    with SessionLocal() as db:
        uid = db.query(User).filter(User.email == me["email"]).one().id
        bot = Bot(user_id=uid, name="t")
        db.add(bot)
        db.flush()
        db.add(BotVersion(bot_id=bot.id, version=1, spec=spec, note=""))
        db.commit()
        bid = bot.id
    last = None
    for t in ["/start", "m:0", "i:tee", "M", "مشکی", "checkout", "علی", "09123456789"]:
        last = c.post(f"/api/bots/{bid}/simulate", json={"session_id": "q", "text": t}, headers=H).json()
    assert any("سفارش شما ثبت شد" in a["text"] for a in last["actions"])
    rec = c.get(f"/api/bots/{bid}/records?sandbox=true", headers=H).json()[0]["data"]
    assert rec["items"][0]["options"] == {"سایز": "M", "رنگ": "مشکی"}


def test_register_is_rate_limited_per_ip_and_global_run_cap(monkeypatch):
    from app.config import settings
    from app import main

    main._reg_hits.clear()
    monkeypatch.setattr(settings, "register_per_ip_hour", 2)
    c = TestClient(app)
    h = {"x-forwarded-for": "9.9.9.9"}
    codes = [c.post("/api/auth/register", json={"email": f"rl{i}@b.com", "password": "123456"}, headers=h).status_code for i in range(3)]
    assert codes == [200, 200, 429]
    # a different IP is unaffected
    assert c.post("/api/auth/register", json={"email": "rl9@b.com", "password": "123456"}, headers={"x-forwarded-for": "8.8.8.8"}).status_code == 200

    tok = c.post("/api/auth/login", json={"email": "rl0@b.com", "password": "123456"}).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    bot = c.post("/api/bots/draft", headers=H).json()["id"]
    monkeypatch.setattr(settings, "global_daily_runs", 0)
    r = c.post(f"/api/bots/{bot}/builder", json={"text": "سلام ربات"}, headers=H)
    assert r.status_code == 503 and "ظرفیت" in r.json()["detail"]
