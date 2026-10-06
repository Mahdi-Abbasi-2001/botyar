"""Shop round 2 through the API: product photos (upload, serve, replace, delete) and the owner confirming a card-to-card order."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import io  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import bale  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Bot, BotFile, BotVersion, Product, Record, User  # noqa: E402

SPEC = {"name": "t", "welcome": "سلام", "menu": [{"label": "خرید", "block": "shop"}],
        "blocks": [{"type": "catalog_order", "id": "shop", "title": "فروشگاه", "source": "table",
                    "payment": "card", "card_number": "6037997512345678"}]}
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 2000


@pytest.fixture()
def world(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "public_base_url", "https://example.test")
    monkeypatch.setattr(settings, "bale_shared_bot_token", "SHAREDTOKEN")
    sent = []

    def fake(token, method, payload=None, timeout=15):
        if method == "sendMessage":
            sent.append((str(payload["chat_id"]), payload["text"]))
        return {"username": "botyar_test_bot"} if method == "getMe" else True

    monkeypatch.setattr(bale, "api_call", fake)
    with TestClient(app) as c:
        tok = c.post("/api/auth/register", json={"username": "shop_owner", "password": "123456"}).json()["token"]
        H = {"Authorization": f"Bearer {tok}"}
        with SessionLocal() as db:
            uid = db.query(User).filter(User.username == "shop_owner").one().id
            bot = Bot(user_id=uid, name="t")
            db.add(bot)
            db.flush()
            db.add(BotVersion(bot_id=bot.id, version=1, spec=SPEC, note=""))
            p = Product(bot_id=bot.id, block_id="shop", name="کفش", category="", price=100000, stock=3, options=[], position=0)
            db.add(p)
            db.commit()
            bid, pid = bot.id, p.id
        st = c.post(f"/api/bots/{bid}/publish", json={"mode": "shared"}, headers=H).json()
        monkeypatch.setattr(settings, "_code", st.get("code", ""), raising=False)
        yield c, H, bid, pid, sent


def upload(c, H, bid, pid, data=JPEG):
    return c.put(f"/api/bots/{bid}/catalog/products/{pid}/photo", files={"file": ("a.jpg", io.BytesIO(data), "image/jpeg")}, headers=H)


def test_product_photo_upload_serve_and_delete(world):
    c, H, bid, pid, _ = world
    r = upload(c, H, bid, pid)
    assert r.status_code == 200 and r.json()["photo"] is True
    assert c.get(f"/api/bots/{bid}/catalog/products/{pid}/photo", headers=H).content == JPEG
    assert upload(c, H, bid, pid, JPEG + b"1").status_code == 200          # replacing keeps one file
    with SessionLocal() as db:
        assert db.query(BotFile).filter(BotFile.block_id == f"product:{pid}").count() == 1
    assert upload(c, H, bid, pid, b"not an image").status_code == 422
    assert upload(c, H, bid, pid, b"\xff\xd8\xff" + b"0" * 1_600_000).status_code == 413
    assert c.get(f"/api/bots/{bid}/catalog/products/{pid}/photo").status_code == 401
    assert c.delete(f"/api/bots/{bid}/catalog/products/{pid}/photo", headers=H).json()["photo"] is False
    assert c.get(f"/api/bots/{bid}/catalog/products/{pid}/photo", headers=H).status_code == 404


def test_deleting_a_product_or_replacing_the_catalog_removes_photos(world):
    c, H, bid, pid, _ = world
    upload(c, H, bid, pid)
    c.post(f"/api/bots/{bid}/catalog/commit", json={"products": [{"name": "کیف", "category": "", "price": 5, "stock": None, "options": [], "description": ""}], "mode": "replace"}, headers=H)
    with SessionLocal() as db:
        assert db.query(BotFile).count() == 0


def test_another_owner_cannot_touch_the_photo(world):
    c, H, bid, pid, _ = world
    upload(c, H, bid, pid)
    other = c.post("/api/auth/register", json={"username": "evil_owner", "password": "123456"}).json()["token"]
    O = {"Authorization": f"Bearer {other}"}
    assert c.get(f"/api/bots/{bid}/catalog/products/{pid}/photo", headers=O).status_code == 404
    assert upload(c, O, bid, pid).status_code == 404


def test_owner_confirms_a_card_payment_and_the_customer_is_told(world):
    c, H, bid, pid, sent = world
    with SessionLocal() as db:
        r = Record(bot_id=bid, collection="shop", sandbox=False,
                   data={"name": "م", "items": [{"id": pid, "name": "کفش", "price": 1, "qty": 1, "options": {}}], "total": 1,
                         "status": "transfer_sent", "transfer_ref": "123456", "_cust": "bale:555"})
        db.add(r)
        db.commit()
        rid = r.id
    url = f"/api/bots/{bid}/records/{rid}"
    assert c.patch(url, json={"action": "status", "status": "preparing"}, headers=H).status_code == 409
    r = c.patch(url, json={"action": "confirm_payment"}, headers=H)
    assert r.status_code == 200 and r.json()["status"] == "new"
    assert "واریز شما تأیید شد" in dict(sent)["555"]
    assert c.patch(url, json={"action": "confirm_payment"}, headers=H).status_code == 409


def test_bale_location_and_photo_messages_reach_the_engine(world, monkeypatch):
    seen = []
    from app import engine as eng
    real = eng.handle
    monkeypatch.setattr(eng, "handle", lambda spec, state, t, *a, **k: seen.append(t) or real(spec, state, t, *a, **k))
    c, H, bid, pid, _ = world
    url = f"/api/hook/shared/{bale.shared_hook_secret()}"

    def post(**msg):
        c.post(url, json={"update_id": len(seen) + 1, "message": {"message_id": 1, "chat": {"id": 42, "type": "private"}, "from": {"id": 42}, **msg}})

    post(text=f"/start {settings._code.lower()}")
    post(location={"latitude": 35.7, "longitude": 51.4})
    post(photo=[{"file_id": "small"}, {"file_id": "BIG"}])
    assert "loc:35.7,51.4" in seen and "photo:BIG" in seen
