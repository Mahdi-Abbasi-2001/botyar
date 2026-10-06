"""Hostile / messy input must produce a clear Persian error, never a 500."""
import io
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import bale  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.engine import MemoryStore, handle, new_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import BotVersion  # noqa: E402
from app.spec import BotSpec  # noqa: E402


@pytest.fixture()
def shop():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app, raise_server_exceptions=False) as c:
        tok = c.post("/api/auth/register", json={"username": "rb_x.com", "password": "123456"}).json()["token"]
        H = {"Authorization": f"Bearer {tok}"}
        bot = c.post("/api/bots", json={"template": "cafe"}, headers=H).json()["id"]
        with SessionLocal() as db:  # turn the cafe into a table-catalog bot
            v = db.scalars(select(BotVersion).where(BotVersion.bot_id == bot)).first()
            spec = dict(v.spec)
            spec["blocks"] = [dict(b, source="table", items=[]) if b["type"] == "catalog_order" else b for b in spec["blocks"]]
            v.spec = spec
            db.commit()
        yield c, H, bot


def upload(c, H, bot, name, data, ctype):
    return c.post(f"/api/bots/{bot}/catalog/preview", headers=H, files=[("files", (name, io.BytesIO(data), ctype))])


@pytest.mark.parametrize("name,data,ctype,status", [
    ("garbage.csv", os.urandom(3000), "text/csv", 422),
    ("fake.xlsx", b"this is not a zip", "application/vnd.ms-excel", 422),
    ("empty.csv", b"", "text/csv", 422),
    ("header-only.csv", "نام,قیمت\n".encode(), "text/csv", 422),
    ("huge.csv", b"x" * 9_000_000, "text/csv", 413),
    ("notimage.png", b"not really a png", "image/png", 422),
    ("empty.pdf", b"%PDF-1.4\n%%EOF", "application/pdf", 422),
])
def test_bad_uploads_get_a_clear_error_not_a_500(shop, name, data, ctype, status):
    c, H, bot = shop
    r = upload(c, H, bot, name, data, ctype)
    assert r.status_code == status, r.text[:120]
    assert r.json()["detail"]  # a Persian sentence the UI can show


def test_commit_rejects_values_the_database_could_not_store(shop):
    c, H, bot = shop
    base = {"category": "", "price": 1, "stock": None, "options": [], "description": ""}
    for bad in ({**base, "name": "x" * 5000}, {**base, "name": "  "}, {**base, "name": "ok", "category": "c" * 500},
                {**base, "name": "ok", "options": [{"name": "سایز", "choices": ["a" * 200]}]}):
        r = c.post(f"/api/bots/{bot}/catalog/commit", headers=H, json={"mode": "replace", "products": [bad]})
        assert r.status_code == 422, bad
    ok = c.post(f"/api/bots/{bot}/catalog/commit", headers=H, json={"mode": "replace", "products": [{**base, "name": "کفش"}]})
    assert ok.status_code == 200


def test_webhook_with_malformed_body_is_a_400_not_a_500(shop):
    c, *_ = shop
    url = f"/api/hook/shared/{bale.shared_hook_secret()}"
    assert c.post(url, content=b"{not json", headers={"content-type": "application/json"}).status_code == 400
    assert c.post(url, json=["a", "list"]).status_code == 400
    assert c.post(url, json={}).status_code == 200  # an empty-but-valid update is simply ignored


def test_very_long_product_and_category_names_are_shortened_in_buttons():
    spec = BotSpec.model_validate({"name": "s", "welcome": "سلام", "menu": [{"label": "خرید", "block": "shop"}],
                                   "blocks": [{"type": "catalog_order", "id": "shop", "title": "ف", "source": "table"}]})
    st = MemoryStore()
    st.load_catalog("shop", [{"name": "ن" * 250, "category": "د" * 250, "price": 1000, "stock": None, "options": [], "description": ""},
                             {"name": "کالا", "category": "کوتاه", "price": 1000, "stock": None, "options": [], "description": ""}])
    sess = new_session()
    out = handle(spec, sess, "/start", st)
    out = handle(spec, sess, "m:0", st)
    labels = [b["text"] for a in out for b in a["buttons"]]
    assert all(len(t) <= 60 for t in labels), labels
    out = handle(spec, sess, "all", st)
    assert all(len(b["text"]) <= 60 for a in out for b in a["buttons"])
