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
    assert c.post("/api/auth/register", json={"username": "a_b.com", "password": "123456"}).status_code == 200
    assert c.post("/api/auth/register", json={"username": "a_b.com", "password": "123456"}).status_code == 409
    assert c.post("/api/auth/login", json={"username": "a_b.com", "password": "wrong1"}).status_code == 401
    tok = c.post("/api/auth/login", json={"username": "a_b.com", "password": "123456"}).json()["token"]
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
    tok2 = c.post("/api/auth/register", json={"username": "x_y.com", "password": "123456"}).json()["token"]
    assert c.get(f"/api/bots/{bot['id']}", headers={"Authorization": f"Bearer {tok2}"}).status_code == 404


def test_two_option_groups_in_a_row_survive_persistence():
    """Regression: consecutive same-step messages used to lose nested state (shallow copy hid in-place edits)."""
    from app.db import SessionLocal
    from app.models import Bot, BotVersion, User

    c = TestClient(app)
    tok = c.post("/api/auth/register", json={"username": "opt_b.com", "password": "123456"}).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    me = c.get("/api/me", headers=H).json()
    spec = {"name": "t", "welcome": "سلام", "menu": [{"label": "سفارش", "block": "o"}],
            "blocks": [{"type": "catalog_order", "id": "o", "title": "منو", "min_total": 0,
                        "items": [{"id": "tee", "name": "تی‌شرت", "price": 100000,
                                   "options": [{"name": "سایز", "choices": ["S", "M"]}, {"name": "رنگ", "choices": ["سفید", "مشکی"]}]}]}]}
    with SessionLocal() as db:
        uid = db.query(User).filter(User.username == me["username"]).one().id
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
    codes = [c.post("/api/auth/register", json={"username": f"rl{i}_b.com", "password": "123456"}, headers=h).status_code for i in range(3)]
    assert codes == [200, 200, 429]
    # a different IP is unaffected
    assert c.post("/api/auth/register", json={"username": "rl9_b.com", "password": "123456"}, headers={"x-forwarded-for": "8.8.8.8"}).status_code == 200

    tok = c.post("/api/auth/login", json={"username": "rl0_b.com", "password": "123456"}).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    bot = c.post("/api/bots/draft", headers=H).json()["id"]
    monkeypatch.setattr(settings, "global_daily_runs", 0)
    r = c.post(f"/api/bots/{bot}/builder", json={"text": "سلام ربات"}, headers=H)
    assert r.status_code == 503 and "ظرفیت" in r.json()["detail"]


def test_interrupted_agent_run_does_not_lock_the_bot():
    """A server restart kills the agent thread; the run must not stay 'running' and block the bot forever."""
    from datetime import datetime, timedelta, timezone

    from app.db import SessionLocal
    from app.models import BuilderRun

    c = TestClient(app)
    tok = c.post("/api/auth/register", json={"username": "stuck_b.com", "password": "123456"}).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    bot = c.post("/api/bots/draft", headers=H).json()["id"]
    with SessionLocal() as db:
        db.add(BuilderRun(bot_id=bot, status="running", events=[], result={}, created_at=datetime.now(timezone.utc) - timedelta(hours=2)))
        db.commit()
    # (the agent itself is not started here: only the lock matters, so use a text the request validator accepts and stop at 200)
    from app import agent, main
    orig = main.run_builder
    main.run_builder = lambda *a, **k: None
    try:
        r = c.post(f"/api/bots/{bot}/builder", json={"text": "یک ربات می‌خوام"}, headers=H)
    finally:
        main.run_builder = orig
    assert r.status_code == 200
    # while a *fresh* run is in flight the second request is still refused
    r2 = c.post(f"/api/bots/{bot}/builder", json={"text": "یک ربات دیگر"}, headers=H)
    assert r2.status_code == 409


def test_active_run_endpoint_lets_the_page_resume_after_a_refresh():
    from app import main
    from app.db import SessionLocal
    from app.models import BuilderRun

    c = TestClient(app)
    tok = c.post("/api/auth/register", json={"username": "resume_b.com", "password": "123456"}).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    bot = c.post("/api/bots/draft", headers=H).json()["id"]
    assert c.get(f"/api/bots/{bot}/builder/active", headers=H).json() == {"run_id": None, "events": []}
    with SessionLocal() as db:
        run = BuilderRun(bot_id=bot, status="running", events=["در حال طراحی ساختار ربات…"], result={})
        db.add(run)
        db.commit()
        rid = run.id
    got = c.get(f"/api/bots/{bot}/builder/active", headers=H).json()
    assert got["run_id"] == rid and got["events"] == ["در حال طراحی ساختار ربات…"]
    other = c.post("/api/auth/register", json={"username": "resume2_b.com", "password": "123456"}).json()["token"]
    assert c.get(f"/api/bots/{bot}/builder/active", headers={"Authorization": f"Bearer {other}"}).status_code == 404
