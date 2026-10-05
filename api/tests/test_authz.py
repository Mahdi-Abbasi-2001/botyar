"""Authorization matrix over EVERY route in the OpenAPI schema (so a newly added route cannot be forgotten):
anonymous -> 401, another user -> never 2xx, owner -> not 401/403/404."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import BuilderRun, Product, Record, VersionTests  # noqa: E402

PUBLIC = {("POST", "/api/auth/login"), ("POST", "/api/auth/register"), ("GET", "/api/health"), ("GET", "/api/templates"), ("GET", "/api/plans"),
          ("POST", "/api/hook/shared/{secret}"), ("POST", "/api/hook/own/{pub_id}/{secret}"),
          ("POST", "/api/tghook/shared/{secret}"), ("POST", "/api/tghook/own/{pub_id}/{secret}")}
NO_BOT = {("GET", "/api/bots"), ("POST", "/api/bots"), ("POST", "/api/bots/draft"), ("GET", "/api/me"),
          ("GET", "/api/me/plan"), ("POST", "/api/me/upgrade"), ("POST", "/api/me/plan/cancel"), ("GET", "/api/admin/upgrades"), ("POST", "/api/admin/upgrades/{rid}")}  # scoped to the caller, no bot id


@pytest.fixture()
def world():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        def user(email):
            tok = c.post("/api/auth/register", json={"email": email, "password": "123456"}).json()["token"]
            return {"Authorization": f"Bearer {tok}"}

        a, b = user("a@x.com"), user("b@x.com")
        bot = c.post("/api/bots", json={"template": "cafe"}, headers=a).json()["id"]
        with SessionLocal() as db:
            db.add(Product(bot_id=bot, block_id="order", name="x", category="", price=1, stock=None, options=[], position=0))
            run = BuilderRun(bot_id=bot, status="done", events=[], result={})
            db.add(run)
            db.add(VersionTests(bot_id=bot, version=1, scenarios=[], results=[]))
            rec = Record(bot_id=bot, collection="order", data={"status": "new", "items": [], "total": 1}, sandbox=False)
            db.add(rec)
            db.commit()
            ids = {"bot_id": bot, "run_id": run.id, "pid": db.query(Product).first().id, "pub_id": 1, "secret": "x", "record_id": rec.id}
        yield c, a, b, ids


def routes():
    out = []
    for path, ops in app.openapi()["paths"].items():
        for method in ops:
            out.append((method.upper(), path))
    return out


def fill(path, ids):
    for k, v in ids.items():
        path = path.replace("{" + k + "}", str(v))
    return path


def call(c, method, path, headers=None):
    kw = {"headers": headers or {}}
    if method in ("POST", "PUT", "PATCH"):
        kw["json"] = {}
    return c.request(method, path, **kw)


def test_every_protected_route_requires_a_login(world):
    c, a, b, ids = world
    seen = []
    for method, path in routes():
        if (method, path) in PUBLIC or not path.startswith("/api"):
            continue
        r = call(c, method, fill(path, ids))
        assert r.status_code == 401, f"{method} {path} answered {r.status_code} without a login"
        seen.append(path)
    # guard: the enumeration really includes every route family (a router that silently went missing would fail here)
    for family in ("/records/{record_id}", "/publish", "/publication", "/catalog/preview", "/catalog/commit", "/export/products", "/export/records", "/builder", "/simulate"):
        assert any(family in p for p in seen), f"route family {family} not covered by the matrix"


def test_another_user_can_never_touch_my_bot(world):
    c, a, b, ids = world
    for method, path in routes():
        if (method, path) in PUBLIC | NO_BOT or "{bot_id}" not in path:
            continue
        r = call(c, method, fill(path, ids), b)
        assert r.status_code not in range(200, 300), f"LEAK: {method} {path} -> {r.status_code} for a different user"
        if method == "GET":
            assert r.status_code == 404, f"{method} {path} -> {r.status_code}"


def test_owner_is_not_locked_out_of_her_own_routes(world):
    c, a, b, ids = world
    for method, path in routes():
        if (method, path) in PUBLIC or "{bot_id}" not in path:
            continue
        r = call(c, method, fill(path, ids), a)
        assert r.status_code not in (401, 403, 404) or r.json().get("detail") in (
            "محصولی برای خروجی گرفتن نیست", "ثبتی برای خروجی گرفتن نیست", "محصول یافت نشد", "اجرا یافت نشد", "این ربات بخش فروشگاهی با فهرست محصولات ندارد"), f"{method} {path} -> {r.status_code} {r.text[:80]}"


def test_webhook_urls_reject_wrong_secrets(world):
    c, *_ = world
    assert c.post("/api/hook/shared/not-the-secret", json={}).status_code == 404
    assert c.post("/api/hook/own/1/not-the-secret", json={}).status_code == 404
    assert c.post("/api/hook/own/99999/x", json={}).status_code == 404
    assert c.post("/api/tghook/shared/not-the-secret", json={}).status_code == 404
    assert c.post("/api/tghook/own/1/not-the-secret", json={}).status_code == 404
    assert c.post("/api/tghook/own/99999/x", json={}).status_code == 404
