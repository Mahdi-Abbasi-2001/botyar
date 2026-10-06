"""A product table that still holds only the agent's invented demo products must not go live by accident:
real customers would see and order products that don't exist."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import bale  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Product  # noqa: E402


@pytest.fixture()
def owner(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "public_base_url", "https://example.test")
    monkeypatch.setattr(settings, "bale_shared_bot_token", "SHAREDTOKEN")
    monkeypatch.setattr(bale, "api_call", lambda token, method, payload=None, timeout=15: {"username": "botyar_test_bot"} if method == "getMe" else True)
    bale._username_cache.clear()
    with TestClient(app) as c:
        H = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"username": "shop", "password": "123456"}).json()["token"]}
        bot = c.post("/api/bots", json={"template": "cafe"}, headers=H).json()["id"]
        yield c, H, bot


def add_products(bot, sample):
    with SessionLocal() as db:
        for i, name in enumerate(["کیف دوشی مشکی", "شال نخی"]):
            db.add(Product(bot_id=bot, block_id="order", name=name, category="", price=100000, stock=None, options=[], position=i, is_sample=sample))
        db.commit()


def test_publishing_demo_products_is_refused_with_the_reason(owner):
    c, H, bot = owner
    add_products(bot, sample=True)
    assert c.get(f"/api/bots/{bot}/publication", headers=H).json()["sample_products"] is True
    r = c.post(f"/api/bots/{bot}/publish", json={"mode": "shared"}, headers=H)
    assert r.status_code == 409 and "نمونه" in r.json()["detail"] and "«محصولات»" in r.json()["detail"]
    assert c.get(f"/api/bots/{bot}/publication", headers=H).json()["published"] is False


def test_the_owner_can_still_publish_the_demo_on_purpose(owner):
    c, H, bot = owner
    add_products(bot, sample=True)
    assert c.post(f"/api/bots/{bot}/publish", json={"mode": "shared", "allow_samples": True}, headers=H).json()["published"] is True


def test_real_products_or_no_table_publish_normally(owner):
    c, H, bot = owner
    assert c.get(f"/api/bots/{bot}/publication", headers=H).json()["sample_products"] is False  # inline menu, no table
    add_products(bot, sample=False)
    assert c.get(f"/api/bots/{bot}/publication", headers=H).json()["sample_products"] is False
    assert c.post(f"/api/bots/{bot}/publish", json={"mode": "shared"}, headers=H).json()["published"] is True


def test_telegram_status_reports_demo_products_too(owner):
    c, H, bot = owner
    add_products(bot, sample=True)
    assert c.get(f"/api/bots/{bot}/telegram", headers=H).json()["sample_products"] is True
