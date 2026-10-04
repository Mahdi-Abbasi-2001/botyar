"""Contact block: customers write to the owner, the owner answers from the dashboard inbox and the reply reaches the customer's chat."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import bale  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.engine import MemoryStore, handle, new_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Bot, BotVersion, User  # noqa: E402
from app.spec import BotSpec  # noqa: E402

SPEC = {"name": "فروشگاه", "welcome": "سلام", "menu": [{"label": "پیام به مدیر", "block": "contact"}],
        "blocks": [{"type": "contact", "id": "contact", "title": "تماس با ما"},
                   {"type": "admin_notify", "id": "n", "on": "contact", "text": "پیام جدید"}]}


def chat(spec=SPEC, store=None, cust="bale:1", name="سارا"):
    s = new_session()
    s["cust"], s["cust_name"] = cust, name
    return BotSpec.model_validate(spec), s, store or MemoryStore()


def say(spec, s, store, *texts):
    out = None
    for t in texts:
        out = handle(spec, s, t, store)
    return out


def test_message_is_stored_confirmed_and_the_owner_is_notified():
    spec, s, store = chat()
    out = say(spec, s, store, "/start", "m:0", "سلام، سفارشم کی می‌رسد؟")
    assert "ارسال شد" in out[0]["text"]
    notes = [a for a in out if a["type"] == "notify_admin"]
    assert len(notes) == 1 and "سفارشم" in notes[0]["text"] and "سارا" in notes[0]["text"]
    rows = store.find("contact")
    assert len(rows) == 1 and rows[0]["from"] == "customer" and rows[0]["thread"] and rows[0]["_cust"] == "bale:1"


def test_follow_up_messages_stay_in_the_same_thread_and_other_customers_get_their_own():
    spec, s, store = chat()
    say(spec, s, store, "/start", "m:0", "اول", "دوم")
    spec2, s2, _ = chat(cust="bale:2", name="علی")
    say(spec2, s2, store, "/start", "m:0", "سوم")
    rows = store.find("contact")
    assert len(rows) == 3 and len({r["thread"] for r in rows[:2]}) == 1 and rows[2]["thread"] != rows[0]["thread"]


def test_flooding_is_limited_and_long_messages_are_cut():
    spec, s, store = chat()
    say(spec, s, store, "/start", "m:0")
    for i in range(25):
        out = say(spec, s, store, f"پیام {i}")
    assert len(store.find("contact")) == 20 and "زیاد" in out[0]["text"]
    spec, s, store = chat()
    say(spec, s, store, "/start", "m:0", "ا" * 5000)
    assert len(store.find("contact")[0]["text"]) == 1000


def test_menu_button_returns_to_menu_and_forged_blocks_do_not_break():
    spec, s, store = chat()
    out = say(spec, s, store, "/start", "m:0", "/menu")
    assert s["block"] is None and store.find("contact") == []


@pytest.fixture()
def world(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    bale._seen.clear()
    monkeypatch.setattr(settings, "public_base_url", "https://example.test")
    monkeypatch.setattr(settings, "bale_shared_bot_token", "SHAREDTOKEN")
    sent = []

    def fake(token, method, payload=None, timeout=15):
        if method == "sendMessage":
            sent.append((str(payload["chat_id"]), payload["text"]))
        return {"username": "botyar_test_bot"} if method == "getMe" else True

    monkeypatch.setattr(bale, "api_call", fake)
    with TestClient(app) as c:
        tok = c.post("/api/auth/register", json={"email": "ct@x.com", "password": "123456"}).json()["token"]
        H = {"Authorization": f"Bearer {tok}"}
        with SessionLocal() as db:
            uid = db.query(User).filter(User.email == "ct@x.com").one().id
            bot = Bot(user_id=uid, name="فروشگاه")
            db.add(bot)
            db.flush()
            db.add(BotVersion(bot_id=bot.id, version=1, spec=SPEC, note=""))
            db.commit()
            bid = bot.id
        yield c, H, bid, sent


def test_owner_reply_from_the_inbox_reaches_the_customer_on_bale(world):
    c, H, bid, sent = world
    st = c.post(f"/api/bots/{bid}/publish", json={"mode": "shared"}, headers=H).json()
    url = f"/api/hook/shared/{bale.shared_hook_secret()}"
    n = [7000]

    def msg(chat_id, text):
        n[0] += 1
        return {"update_id": n[0], "message": {"message_id": 1, "from": {"id": chat_id, "first_name": "مریم"},
                                               "chat": {"id": chat_id, "type": "private"}, "text": text}}

    def tap(chat_id, data):
        n[0] += 1
        return {"update_id": n[0], "callback_query": {"id": "q", "from": {"id": chat_id, "first_name": "مریم"}, "data": data,
                                                      "message": {"message_id": 7, "chat": {"id": chat_id, "type": "private"}}}}

    c.post(url, json=msg(900, f"/admin {st['admin_code']}"))
    c.post(url, json=msg(901, st["code"]))
    c.post(url, json=tap(901, "m:0"))
    sent.clear()
    c.post(url, json=msg(901, "ارسال به شیراز هم دارید؟"))
    assert any(chat_id == "900" and "مریم" in t and "شیراز" in t for chat_id, t in sent)

    box = c.get(f"/api/bots/{bid}/inbox", headers=H).json()
    assert len(box) == 1 and box[0]["who"] == "مریم" and box[0]["unanswered"] is True and "cust" not in box[0]
    assert "_cust" not in str(box)
    t = box[0]
    sent.clear()
    r = c.post(f"/api/bots/{bid}/inbox/{t['collection']}/{t['thread']}/reply", json={"text": "بله، ارسال داریم"}, headers=H).json()
    assert r["delivered"] == 1
    assert sent == [("901", "✉️ پاسخ مدیر:\nبله، ارسال داریم")]
    box = c.get(f"/api/bots/{bid}/inbox", headers=H).json()
    assert [m["from"] for m in box[0]["messages"]] == ["customer", "owner"] and box[0]["unanswered"] is False

    # other owners can neither read nor answer
    tok2 = c.post("/api/auth/register", json={"email": "other@x.com", "password": "123456"}).json()["token"]
    H2 = {"Authorization": f"Bearer {tok2}"}
    assert c.get(f"/api/bots/{bid}/inbox", headers=H2).status_code == 404
    assert c.post(f"/api/bots/{bid}/inbox/{t['collection']}/{t['thread']}/reply", json={"text": "x"}, headers=H2).status_code == 404
    assert c.post(f"/api/bots/{bid}/inbox/{t['collection']}/nope/reply", json={"text": "x"}, headers=H).status_code == 404
    assert c.post(f"/api/bots/{bid}/inbox/{t['collection']}/{t['thread']}/reply", json={"text": "   "}, headers=H).status_code in (404, 422)


def test_simulator_threads_are_sandboxed_and_nothing_is_sent(world):
    c, H, bid, sent = world
    c.post(f"/api/bots/{bid}/simulate", json={"session_id": "s", "text": "/start"}, headers=H)
    c.post(f"/api/bots/{bid}/simulate", json={"session_id": "s", "text": "m:0"}, headers=H)
    c.post(f"/api/bots/{bid}/simulate", json={"session_id": "s", "text": "سلام"}, headers=H)
    assert c.get(f"/api/bots/{bid}/inbox", headers=H).json() == []
    t = c.get(f"/api/bots/{bid}/inbox?sandbox=true", headers=H).json()[0]
    sent.clear()
    r = c.post(f"/api/bots/{bid}/inbox/{t['collection']}/{t['thread']}/reply?sandbox=true", json={"text": "جواب"}, headers=H).json()
    assert r["delivered"] == 0 and sent == []
