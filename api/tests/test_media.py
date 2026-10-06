"""Photos/files and map pins on message blocks: spec, engine actions, upload validation, Bale delivery, simulator preview."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app import bale, testing  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.engine import MemoryStore, handle, new_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Bot, BotVersion, User, VersionTests  # noqa: E402
from app.spec import BotSpec  # noqa: E402

SPEC = {"name": "فروشگاه", "welcome": "سلام", "menu": [{"label": "کاتالوگ", "block": "cat"}, {"label": "آدرس", "block": "addr"}, {"label": "بیشتر", "block": "more"}],
        "blocks": [{"type": "message", "id": "cat", "text": "کاتالوگ ما", "media": "document"},
                   {"type": "message", "id": "addr", "text": "آدرس: میدان ولیعصر", "location": {"latitude": 35.7, "longitude": 51.4}},
                   {"type": "menu", "id": "more", "title": "بیشتر", "items": [{"label": "لیست قیمت", "block": "price"}]},
                   {"type": "message", "id": "price", "text": "لیست قیمت", "media": "image", "location": {"latitude": 35.0, "longitude": 51.0}}]}
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100
PDF = b"%PDF-1.4\n" + b"0" * 100


def kinds(out):
    return [a["type"] for a in out]


def test_spec_validation_for_media_and_location():
    BotSpec.model_validate(SPEC)
    with pytest.raises(ValidationError):
        BotSpec.model_validate({**SPEC, "blocks": [{"type": "message", "id": "x", "text": "t", "media": "video"}]})
    with pytest.raises(ValidationError):
        BotSpec.model_validate({**SPEC, "blocks": [{"type": "message", "id": "x", "text": "t", "location": {"latitude": 95, "longitude": 10}}]})


def test_engine_emits_text_then_media_then_location_then_the_menu():
    sp, s, st = BotSpec.model_validate(SPEC), new_session(), MemoryStore()
    handle(sp, s, "/start", st)
    out = handle(sp, s, "m:0", st)
    assert kinds(out) == ["send", "media", "send"] and out[1] == {"type": "media", "block": "cat", "kind": "document"}
    out = handle(sp, s, "m:1", st)
    assert kinds(out) == ["send", "location", "send"] and out[1]["latitude"] == 35.7
    handle(sp, s, "m:2", st)
    out = handle(sp, s, "s:0", st)                       # inside a sub-menu: media + location, then the sub-menu again
    assert kinds(out) == ["send", "media", "location", "send"] and s["block"] == "more"


def test_agent_tests_see_the_attachment_and_pin():
    sc = testing.TestScenario(name="n", setup=[], records=[], steps=[
        testing.TestStep(say="/start", reply_contains=[], reply_not_contains=[]),
        testing.TestStep(say="m:0", reply_contains=["📎 فایل"], reply_not_contains=["📍"]),
        testing.TestStep(say="m:1", reply_contains=["📍 35.7, 51.4"], reply_not_contains=[])])
    assert testing.run_scenario(BotSpec.model_validate(SPEC), sc)["passed"]


@pytest.fixture()
def world(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    bale._seen.clear()
    monkeypatch.setattr(settings, "public_base_url", "https://example.test")
    monkeypatch.setattr(settings, "bale_shared_bot_token", "SHAREDTOKEN")
    calls, uploads = [], []

    def fake(token, method, payload=None, timeout=15):
        calls.append((method, payload))
        return {"username": "botyar_test_bot"} if method == "getMe" else True

    def fake_upload(token, method, fields, field, filename, data, mime, timeout=60):
        uploads.append((method, fields, field, filename, len(data), mime))
        return True

    monkeypatch.setattr(bale, "api_call", fake)
    monkeypatch.setattr(bale, "api_upload", fake_upload)
    with TestClient(app) as c:
        tok = c.post("/api/auth/register", json={"username": "m_x.com", "password": "123456"}).json()["token"]
        H = {"Authorization": f"Bearer {tok}"}
        with SessionLocal() as db:
            uid = db.query(User).filter(User.username == "m_x.com").one().id
            bot = Bot(user_id=uid, name="فروشگاه")
            db.add(bot)
            db.flush()
            db.add(BotVersion(bot_id=bot.id, version=1, spec=SPEC, note=""))
            db.add(VersionTests(bot_id=bot.id, version=1, scenarios=[], results=[{"name": "t", "passed": True, "failures": [], "transcript": []}]))
            db.commit()
            bid = bot.id
        yield c, H, bid, calls, uploads


def put(c, H, bid, block, name, data, ctype="application/octet-stream"):
    return c.put(f"/api/bots/{bid}/media/{block}", files={"file": (name, data, ctype)}, headers=H)


def test_upload_rules(world):
    c, H, bid, *_ = world
    slots = c.get(f"/api/bots/{bid}/media", headers=H).json()
    assert {s["block"]: s["kind"] for s in slots} == {"cat": "document", "price": "image"} and not any(s["uploaded"] for s in slots)
    assert put(c, H, bid, "cat", "catalog.pdf", PDF, "application/pdf").json() == {"uploaded": True, "filename": "catalog.pdf", "size": len(PDF)}
    assert put(c, H, bid, "cat", "x.exe", b"MZ" + b"0" * 50).status_code == 422                     # not an allowed document type
    assert put(c, H, bid, "cat", "fake.pdf", b"not a pdf").status_code == 422
    assert put(c, H, bid, "price", "p.png", PNG).status_code == 200
    assert put(c, H, bid, "price", "p.png", b"GIF89a" + b"0" * 20).status_code == 422                 # not a JPG/PNG/WEBP
    assert put(c, H, bid, "price", "p.png", b"").status_code == 422
    assert put(c, H, bid, "price", "big.png", PNG + b"0" * (5 * 1024 * 1024)).status_code == 413
    assert put(c, H, bid, "addr", "a.png", PNG).status_code == 404                                    # that block takes no file
    assert put(c, H, bid, "nope", "a.png", PNG).status_code == 404
    assert put(c, H, bid, "cat", "../../etc/passwd.pdf", PDF).json()["filename"] == "passwd.pdf"      # path parts are dropped
    other = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"username": "o_x.com", "password": "123456"}).json()["token"]}
    assert put(c, other, bid, "cat", "c.pdf", PDF).status_code == 404 and c.get(f"/api/bots/{bid}/media", headers=other).status_code == 404
    assert c.delete(f"/api/bots/{bid}/media/cat", headers=other).status_code == 404
    assert c.delete(f"/api/bots/{bid}/media/cat", headers=H).status_code == 200
    assert not [s for s in c.get(f"/api/bots/{bid}/media", headers=H).json() if s["block"] == "cat"][0]["uploaded"]


def test_simulator_describes_the_attachment_and_bale_gets_the_real_file_and_pin(world):
    c, H, bid, calls, uploads = world
    sim = lambda t: c.post(f"/api/bots/{bid}/simulate", json={"session_id": "s", "text": t}, headers=H).json()["actions"]
    sim("/start")
    out = sim("m:0")
    assert out[1]["type"] == "media" and out[1]["uploaded"] is False
    put(c, H, bid, "cat", "catalog.pdf", PDF, "application/pdf")
    out = sim("m:0")
    assert out[1]["uploaded"] is True and out[1]["filename"] == "catalog.pdf"

    pub = c.post(f"/api/bots/{bid}/publish", json={"mode": "shared"}, headers=H).json()
    n = [60000]

    def msg(text):
        n[0] += 1
        return c.post(f"/api/hook/shared/{bale.shared_hook_secret()}", json={"update_id": n[0], "message": {
            "message_id": 1, "from": {"id": 77, "first_name": "x"}, "chat": {"id": 77, "type": "private"}, "text": text}})

    def tap(data):
        n[0] += 1
        return c.post(f"/api/hook/shared/{bale.shared_hook_secret()}", json={"update_id": n[0], "callback_query": {
            "id": "q", "from": {"id": 77}, "data": data, "message": {"message_id": 7, "chat": {"id": 77, "type": "private"}}}})

    msg(f"/start {pub['code']}")
    uploads.clear(); calls.clear()
    tap("m:0")
    assert uploads == [("sendDocument", {"chat_id": "77"}, "document", "catalog.pdf", len(PDF), "application/pdf")]
    calls.clear()
    tap("m:1")
    loc = [p for m, p in calls if m == "sendLocation"]
    assert loc == [{"chat_id": "77", "latitude": 35.7, "longitude": 51.4}]
    uploads.clear()
    tap("m:2"); tap("s:0")                                             # image not uploaded yet: text and pin still go out, no crash
    assert uploads == [] and any(m == "sendLocation" and p["latitude"] == 35.0 for m, p in calls)
