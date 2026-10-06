"""Through the API: answering an unanswered FAQ question (reply to the customer + a new FAQ version that a live bot picks up),
the owner's decision on an application, and downloading a file a customer sent."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import bale, faq_index  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Bot, BotVersion, Publication, Record, User, VersionTests  # noqa: E402

FAQ = {"type": "faq", "id": "q", "title": "پرسش‌ها", "entries": [{"question": "ساعت کاری کافه چیست؟", "answer": "۸ تا ۲۲"}]}
JOB = {"type": "form", "id": "job", "title": "درخواست همکاری", "review": True,
       "fields": [{"key": "name", "label": "نام؟"}, {"key": "cv", "label": "رزومه", "kind": "file"}]}
SPEC = {"name": "کافه", "welcome": "سلام", "menu": [{"label": "سؤالات", "block": "q"}, {"label": "همکاری", "block": "job"}], "blocks": [FAQ, JOB]}
def step(say, *contains):
    return {"say": say, "reply_contains": list(contains), "reply_not_contains": []}


TEST = {"name": "ساعت کاری", "setup": [], "records": [], "steps": [step("/start"), step("m:0"), step("ساعت کاری کافه چیست؟", "۸ تا ۲۲")]}


@pytest.fixture()
def world(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "public_base_url", "https://example.test")
    monkeypatch.setattr(settings, "bale_shared_bot_token", "SHAREDTOKEN")
    monkeypatch.setattr(faq_index, "ensure", lambda *a, **k: {})        # no embedding calls in tests
    sent = []

    def fake(token, method, payload=None, timeout=15):
        if method == "sendMessage":
            sent.append((str(payload["chat_id"]), payload["text"]))
        if method == "getFile":
            return {"file_path": "docs/cv.pdf"}
        return {"username": "botyar_test_bot"} if method == "getMe" else True

    monkeypatch.setattr(bale, "api_call", fake)
    with TestClient(app) as c:
        tok = c.post("/api/auth/register", json={"username": "cafe_owner", "password": "123456"}).json()["token"]
        H = {"Authorization": f"Bearer {tok}"}
        with SessionLocal() as db:
            uid = db.query(User).filter(User.username == "cafe_owner").one().id
            bot = Bot(user_id=uid, name="کافه")
            db.add(bot)
            db.flush()
            db.add(BotVersion(bot_id=bot.id, version=1, spec=SPEC, note=""))
            db.add(VersionTests(bot_id=bot.id, version=1, scenarios=[TEST], results=[{"name": "ساعت کاری", "passed": True}]))
            db.commit()
            bid = bot.id
        assert c.post(f"/api/bots/{bid}/publish", json={"mode": "shared"}, headers=H).status_code == 200

        def add(collection, data, sandbox=False):
            with SessionLocal() as db:
                r = Record(bot_id=bid, collection=collection, data=data, sandbox=sandbox)
                db.add(r)
                db.commit()
                return r.id

        yield c, H, bid, add, sent


def latest(bid):
    with SessionLocal() as db:
        return db.query(BotVersion).filter(BotVersion.bot_id == bid).order_by(BotVersion.version.desc()).first()


def test_answering_a_question_replies_and_teaches_the_live_bot(world):
    c, H, bid, add, sent = world
    rid = add("q", {"question": "پارکینگ دارین؟", "status": "unanswered", "_cust": "bale:77"})
    r = c.post(f"/api/bots/{bid}/records/{rid}/answer", json={"answer": "بله، روبه‌روی کافه.", "question": "پارکینگ دارید؟"}, headers=H).json()
    assert r["added_version"] == 2 and r["not_added"] == "" and r["customer_messages"]["sent"] == 1
    assert "پاسخ سؤال شما" in dict(sent)["77"] and "روبه‌روی کافه" in dict(sent)["77"]
    v = latest(bid)
    assert v.version == 2 and v.spec["blocks"][0]["entries"][-1]["question"] == "پارکینگ دارید؟"
    with SessionLocal() as db:
        assert db.query(Publication).filter(Publication.bot_id == bid).one().version == 2   # the live bot moved with it
        assert db.query(VersionTests).filter(VersionTests.version == 2).one().results[0]["passed"]
        assert db.get(Record, rid).data["status"] == "handled"
    assert c.post(f"/api/bots/{bid}/records/{rid}/answer", json={"answer": "x"}, headers=H).status_code == 404  # answered once


def test_reply_only_and_duplicates_and_a_question_that_breaks_a_test(world):
    c, H, bid, add, _ = world
    rid = add("q", {"question": "منوی صبحانه؟", "status": "unanswered"})
    r = c.post(f"/api/bots/{bid}/records/{rid}/answer", json={"answer": "از ۸ تا ۱۱", "add_to_faq": False}, headers=H).json()
    assert r["added_version"] is None and latest(bid).version == 1
    rid = add("q", {"question": "ساعت کاری کافه چیست؟", "status": "unanswered"})
    r = c.post(f"/api/bots/{bid}/records/{rid}/answer", json={"answer": "۸ تا ۲۲"}, headers=H).json()
    assert r["added_version"] is None and "همین حالا" in r["not_added"]
    # a near-copy of an existing question makes the saved test ambiguous: it is NOT added, the reply still goes out
    rid = add("q", {"question": "ساعت کاری کافه چیه؟", "status": "unanswered"})
    r = c.post(f"/api/bots/{bid}/records/{rid}/answer", json={"answer": "صبح‌ها", "question": "ساعت کاری کافه چیست ؟ "}, headers=H).json()
    assert r["added_version"] is None and "تست" in r["not_added"] and latest(bid).version == 1


def test_only_the_owner_can_answer(world):
    c, H, bid, add, _ = world
    rid = add("q", {"question": "سؤال؟", "status": "unanswered"})
    other = c.post("/api/auth/register", json={"username": "evil_cafe", "password": "123456"}).json()["token"]
    assert c.post(f"/api/bots/{bid}/records/{rid}/answer", json={"answer": "x"}, headers={"Authorization": f"Bearer {other}"}).status_code == 404


def test_owner_decision_on_an_application(world):
    c, H, bid, add, sent = world
    rid = add("job", {"name": "مریم", "cv": "📎 cv.pdf", "status": "received", "_cust": "bale:88", "_files": {"cv": {"id": "F1", "name": "cv.pdf", "size": 9}}})
    url = f"/api/bots/{bid}/records/{rid}"
    assert c.patch(url, json={"action": "cancel"}, headers=H).status_code == 409
    assert c.patch(url, json={"action": "status", "status": "done"}, headers=H).status_code == 409
    r = c.patch(url, json={"action": "status", "status": "accepted", "reason": "شنبه ساعت ۱۰ مصاحبه"}, headers=H)
    assert r.status_code == 200 and r.json()["status"] == "accepted"
    assert "پذیرفته شد" in dict(sent)["88"] and "مصاحبه" in dict(sent)["88"]


def test_owner_downloads_a_file_from_bale(world, monkeypatch):
    c, H, bid, add, _ = world
    import httpx

    class R:
        content = b"%PDF-1.4 cv"

        def raise_for_status(self):
            pass

    got = []
    monkeypatch.setattr(httpx, "get", lambda url, **k: got.append(url) or R())
    rid = add("job", {"name": "مریم", "_cust": "bale:88", "_files": {"cv": {"id": "F1", "name": "رزومه.pdf", "size": 9}}})
    r = c.get(f"/api/bots/{bid}/records/{rid}/files/cv", headers=H)
    assert r.status_code == 200 and r.content == b"%PDF-1.4 cv" and "UTF-8''" in r.headers["content-disposition"]
    assert got == ["https://tapi.bale.ai/file/botSHAREDTOKEN/docs/cv.pdf"]
    assert c.get(f"/api/bots/{bid}/records/{rid}/files/nope", headers=H).status_code == 404
    sim = add("job", {"_cust": "sim:x", "_files": {"cv": {"id": "sim", "name": "a.pdf"}}}, sandbox=True)
    assert c.get(f"/api/bots/{bid}/records/{sim}/files/cv", headers=H).status_code == 409
    tg = add("job", {"_cust": "tg:5", "_files": {"cv": {"id": "T", "name": "a.pdf"}}})
    assert c.get(f"/api/bots/{bid}/records/{tg}/files/cv", headers=H).status_code == 409
    assert c.get(f"/api/bots/{bid}/records/{rid}/files/cv").status_code == 401
