"""Plans: enforced limits (bots, live bots, AI requests, customers per live bot), upgrade requests, admin approval, customers list."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import bale, billing  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Bot, BotVersion, BuilderRun, CustomerSeen, Subscription, User, VersionTests  # noqa: E402

SPEC = {"name": "کافه", "welcome": "سلام", "menu": [{"label": "درباره", "block": "a"}], "blocks": [{"type": "message", "id": "a", "text": "ما کافه‌ایم"}]}


@pytest.fixture()
def world(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    bale._seen.clear()
    bale._cap_notice.clear()
    monkeypatch.setattr(settings, "public_base_url", "https://example.test")
    monkeypatch.setattr(settings, "bale_shared_bot_token", "SHAREDTOKEN")
    monkeypatch.setattr(settings, "admin_emails", "boss@x.com")
    sent = []

    def fake(token, method, payload=None, timeout=15):
        if method == "sendMessage":
            sent.append((str(payload["chat_id"]), payload["text"]))
        return {"username": "botyar_test_bot"} if method == "getMe" else True

    monkeypatch.setattr(bale, "api_call", fake)
    with TestClient(app) as c:
        def user(email):
            tok = c.post("/api/auth/register", json={"email": email, "password": "123456"}).json()["token"]
            return {"Authorization": f"Bearer {tok}"}

        yield c, user, sent


def add_bot(email, name="کافه"):
    with SessionLocal() as db:
        uid = db.query(User).filter(User.email == email).one().id
        bot = Bot(user_id=uid, name=name)
        db.add(bot)
        db.flush()
        db.add(BotVersion(bot_id=bot.id, version=1, spec=SPEC, note=""))
        db.add(VersionTests(bot_id=bot.id, version=1, scenarios=[], results=[{"name": "t", "passed": True, "failures": [], "transcript": []}]))
        db.commit()
        return bot.id


def test_public_plans_list_and_my_plan_start_on_free(world):
    c, user, _ = world
    plans = c.get("/api/plans").json()
    assert [p["key"] for p in plans["plans"]] == ["free", "basic", "pro", "agency"] and plans["prices_proposed"] is True
    H = user("a@x.com")
    me = c.get("/api/me/plan", headers=H).json()
    assert me["plan"]["key"] == "free" and me["usage"]["bots"] == 0 and me["admin"] is False


def test_bot_limit_blocks_the_fourth_draft_on_free_and_an_upgrade_lifts_it(world):
    c, user, _ = world
    H, B = user("a@x.com"), user("boss@x.com")
    for _ in range(3):
        assert c.post("/api/bots/draft", headers=H).status_code == 200
    r = c.post("/api/bots/draft", headers=H)
    assert r.status_code == 402 and "ارتقا" in r.json()["detail"]
    assert c.post("/api/me/upgrade", json={"plan": "pro", "note": "کافه‌دارم"}, headers=H).status_code == 200
    assert c.post("/api/me/upgrade", json={"plan": "pro"}, headers=H).status_code == 409           # one pending request at a time
    assert c.get("/api/admin/upgrades", headers=H).status_code == 404                              # not an admin: the page does not exist
    reqs = c.get("/api/admin/upgrades", headers=B).json()
    assert reqs[0]["email"] == "a@x.com" and reqs[0]["plan"] == "pro" and reqs[0]["status"] == "pending"
    assert c.post(f"/api/admin/upgrades/{reqs[0]['id']}", json={"approve": True}, headers=H).status_code == 404
    assert c.post(f"/api/admin/upgrades/{reqs[0]['id']}", json={"approve": True}, headers=B).status_code == 200
    assert c.post(f"/api/admin/upgrades/{reqs[0]['id']}", json={"approve": True}, headers=B).status_code == 404   # already decided
    assert c.get("/api/me/plan", headers=H).json()["plan"]["key"] == "pro"
    assert c.post("/api/bots/draft", headers=H).status_code == 200


def test_rejected_request_keeps_the_free_plan_and_free_cannot_be_requested(world):
    c, user, _ = world
    H, B = user("a@x.com"), user("boss@x.com")
    assert c.post("/api/me/upgrade", json={"plan": "free"}, headers=H).status_code == 422
    assert c.post("/api/me/upgrade", json={"plan": "nonsense"}, headers=H).status_code == 422
    c.post("/api/me/upgrade", json={"plan": "basic"}, headers=H)
    rid = c.get("/api/admin/upgrades", headers=B).json()[0]["id"]
    c.post(f"/api/admin/upgrades/{rid}", json={"approve": False}, headers=B)
    assert c.get("/api/me/plan", headers=H).json()["plan"]["key"] == "free"


def test_ai_request_limit(world):
    c, user, _ = world
    H = user("a@x.com")
    bid = c.post("/api/bots/draft", headers=H).json()["id"]
    with SessionLocal() as db:
        for _ in range(billing.PLANS["free"]["ai_requests"]):
            db.add(BuilderRun(bot_id=bid, status="done", events=[], result={}))
        db.commit()
    r = c.post(f"/api/bots/{bid}/builder", json={"text": "یه ربات بساز"}, headers=H)
    assert r.status_code == 402 and "ایجنت" in r.json()["detail"]


def test_only_one_live_bot_on_free(world):
    c, user, _ = world
    H = user("a@x.com")
    b1, b2 = add_bot("a@x.com", "یک"), add_bot("a@x.com", "دو")
    assert c.post(f"/api/bots/{b1}/publish", json={"mode": "shared"}, headers=H).status_code == 200
    r = c.post(f"/api/bots/{b2}/publish", json={"mode": "shared"}, headers=H)
    assert r.status_code == 402 and "منتشر" in r.json()["detail"]
    assert c.post(f"/api/bots/{b1}/publish", json={"mode": "shared"}, headers=H).status_code == 200   # re-publishing the live bot is fine


def hook(c, pub):
    n = [40000]

    def msg(chat, text, name="مشتری"):
        n[0] += 1
        return c.post(f"/api/hook/shared/{bale.shared_hook_secret()}", json={"update_id": n[0], "message": {
            "message_id": 1, "from": {"id": chat, "first_name": name}, "chat": {"id": chat, "type": "private"}, "text": text}})

    return msg


def test_customer_cap_blocks_new_customers_only_and_the_owner_is_told_once(world, monkeypatch):
    c, user, sent = world
    monkeypatch.setitem(billing.PLANS["free"], "customers", 2)
    H = user("a@x.com")
    bid = add_bot("a@x.com")
    pub = c.post(f"/api/bots/{bid}/publish", json={"mode": "shared"}, headers=H).json()
    msg = hook(c, pub)
    link = f"/start {pub['code']}"
    msg(900, f"/admin {pub['admin_code']}")
    for chat in (1, 2):
        msg(chat, link, f"نفر{chat}")
    sent.clear()
    msg(3, link, "نفر سوم")
    assert any(chat == "3" and billing.FULL_TEXT in t for chat, t in sent)
    assert sum(chat == "900" and "ظرفیت ماهانه" in t for chat, t in sent) == 1
    msg(4, link)
    assert sum(chat == "900" and "ظرفیت ماهانه" in t for chat, t in sent) == 1                  # once a day
    sent.clear()
    msg(1, "/start")                                                                                  # an existing customer keeps working
    assert not any(billing.FULL_TEXT in t for _, t in sent)
    with SessionLocal() as db:
        assert db.query(CustomerSeen).filter(CustomerSeen.bot_id == bid).count() == 2


def test_customers_tab_lists_searches_exports_and_hides_chat_ids(world):
    c, user, _ = world
    H, other = user("a@x.com"), user("z@x.com")
    bid = add_bot("a@x.com")
    pub = c.post(f"/api/bots/{bid}/publish", json={"mode": "shared"}, headers=H).json()
    msg = hook(c, pub)
    msg(501, f"/start {pub['code']}", "سارا")
    msg(502, f"/start {pub['code']}", "علی")
    msg(501, "/start", "سارا")
    data = c.get(f"/api/bots/{bid}/customers", headers=H).json()
    assert data["total"] == 2 and data["active_30d"] == 2 and data["cap"] == 100
    assert {i["name"] for i in data["items"]} == {"سارا", "علی"} and "501" not in str(data) and "bale:" not in str(data)
    assert [i["messages"] for i in data["items"] if i["name"] == "سارا"] == [2]
    assert [i["name"] for i in c.get(f"/api/bots/{bid}/customers?q=سار", headers=H).json()["items"]] == ["سارا"]
    csv = c.get(f"/api/bots/{bid}/export/customers", headers=H)
    assert csv.status_code == 200 and "سارا" in csv.content.decode("utf-8-sig") and "bale:" not in csv.text
    assert c.get(f"/api/bots/{bid}/export/customers?format=xlsx", headers=H).status_code == 200
    assert c.get(f"/api/bots/{bid}/customers", headers=other).status_code == 404
    assert c.get(f"/api/bots/{bid}/export/customers", headers=other).status_code == 404
