"""Shared bots: customers arrive through a business's link or pick it from the directory; typed codes are not accepted."""
import itertools
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import bale, telegram  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

uid = itertools.count(1)


@pytest.fixture()
def env(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "public_base_url", "https://example.test")
    monkeypatch.setattr(settings, "bale_shared_bot_token", "BALESHARED")
    monkeypatch.setattr(settings, "telegram_relay_url", "https://relay.example")
    monkeypatch.setattr(settings, "telegram_relay_key", "relay-key")
    monkeypatch.setattr(settings, "telegram_shared_bot_token", "123456:TGSHARED")
    calls = {"bale": [], "tg": []}

    def faker(name):
        def fake(token, method, payload=None, timeout=15):
            calls[name].append((method, payload or {}))
            return {"username": f"{name}_shared_bot"} if method == "getMe" else True
        return fake

    monkeypatch.setattr(bale, "api_call", faker("bale"))
    monkeypatch.setattr(telegram, "api_call", faker("tg"))
    bale._username_cache.clear()
    telegram._username_cache.clear()
    bale._seen.clear()
    with TestClient(app) as c:
        yield c, calls
    bale._seen.clear()


def owner(c, email):
    tok = c.post("/api/auth/register", json={"email": email, "password": "123456"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def bot(c, H, template="workshop"):
    return c.post("/api/bots", json={"template": template}, headers=H).json()["id"]


def msg(chat, text):
    return {"update_id": next(uid) + 100_000, "message": {"message_id": 1, "chat": {"id": chat, "type": "private"}, "text": text}}


def cb(chat, data):
    return {"update_id": next(uid) + 100_000, "callback_query": {"id": "q", "from": {"id": chat}, "data": data,
                                                                 "message": {"message_id": 9, "chat": {"id": chat, "type": "private"}}}}


BALE_URL = lambda: f"/api/hook/shared/{bale.shared_hook_secret()}"  # noqa: E731


def last_out(calls, chat, channel="bale"):
    """The last message for this chat, whether it was sent or edited in place."""
    return [p for m, p in calls[channel] if m in ("sendMessage", "editMessageText") and str(p.get("chat_id")) == str(chat)][-1]


def buttons(payload):
    return [(row[0]["text"], row[0]["callback_data"]) for row in payload.get("reply_markup", {}).get("inline_keyboard", [])]


def test_directory_pages_newest_first_and_picking_opens_the_bot(env):
    c, calls = env
    H = owner(c, "many@x.com")
    ids = [bot(c, H) for _ in range(10)]
    for b in ids:
        assert c.post(f"/api/bots/{b}/publish", json={"mode": "shared"}, headers=H).status_code == 200
    c.post(BALE_URL(), json=msg(50, "سلام"))                  # no link yet: any message shows the directory
    page1 = buttons(last_out(calls, 50))
    picks = [d for _, d in page1 if d.startswith("bdir:")]
    assert len(picks) == 8 and picks[0] == "bdir:10"          # newest publication first, 8 per page
    assert ("بعدی ◀", "bdirp:1") in page1
    c.post(BALE_URL(), json=cb(50, "bdirp:1"))
    out = last_out(calls, 50)
    assert out.get("message_id") == 9                         # the page is edited in place, not re-sent
    assert [d for _, d in buttons(out) if d.startswith("bdir:")] == ["bdir:2", "bdir:1"] and ("▶ قبلی", "bdirp:0") in buttons(out)
    c.post(BALE_URL(), json=cb(50, "bdir:2"))
    assert "خوش آمدید" in [p for m, p in calls["bale"] if m == "sendMessage" and p["chat_id"] == "50"][-2]["text"]


def test_hidden_and_own_token_bots_are_not_listed_but_links_still_work(env):
    c, calls = env
    H = owner(c, "o@x.com")
    shown, hidden, own = bot(c, H), bot(c, H), bot(c, H, "cafe")
    pub_shown = c.post(f"/api/bots/{shown}/publish", json={"mode": "shared"}, headers=H).json()
    pub_hidden = c.post(f"/api/bots/{hidden}/publish", json={"mode": "shared"}, headers=H).json()
    c.post(f"/api/bots/{own}/publish", json={"mode": "own", "token": "999:OWNTOKEN"}, headers=H)
    st = c.put(f"/api/bots/{hidden}/listing", json={"listed": False}, headers=H).json()
    assert st["listed"] is False and pub_hidden["listed"] is True

    c.post(BALE_URL(), json=msg(60, "/start"))
    assert [d for _, d in buttons(last_out(calls, 60))] == ["bdir:1"]   # only the visible shared bot
    c.post(BALE_URL(), json=cb(60, "bdir:2"))                            # a stale/forged pick of the hidden bot
    assert "کدام کسب‌وکار" in last_out(calls, 60)["text"]
    c.post(BALE_URL(), json=msg(60, f"/start {pub_hidden['code']}"))    # but its own link keeps working
    assert "خوش آمدید" in [p for m, p in calls["bale"] if m == "sendMessage" and p["chat_id"] == "60"][-2]["text"]
    assert pub_shown["code"] != pub_hidden["code"]

    c.put(f"/api/bots/{hidden}/listing", json={"listed": True}, headers=H)
    c.post(BALE_URL(), json=msg(61, "/start"))
    assert [d for _, d in buttons(last_out(calls, 61))] == ["bdir:2", "bdir:1"]


def test_typed_codes_and_unknown_links_fall_back_to_the_directory(env):
    c, calls = env
    H = owner(c, "t@x.com")
    b = bot(c, H)
    code = c.post(f"/api/bots/{b}/publish", json={"mode": "shared"}, headers=H).json()["code"]
    c.post(BALE_URL(), json=msg(70, code))
    assert "کدام کسب‌وکار" in last_out(calls, 70)["text"]
    c.post(BALE_URL(), json=msg(70, "/start ZZZZZZ"))
    assert "کدام کسب‌وکار" in last_out(calls, 70)["text"]


def test_empty_directory_says_so(env):
    c, calls = env
    c.post(BALE_URL(), json=msg(80, "/start"))
    out = last_out(calls, 80)
    assert "هنوز کسب‌وکاری" in out["text"] and not buttons(out)


def test_listing_switch_is_owner_only(env):
    c, _ = env
    b = bot(c, owner(c, "a@x.com"))
    H2 = owner(c, "b@x.com")
    assert c.put(f"/api/bots/{b}/listing", json={"listed": False}).status_code in (401, 403)
    assert c.put(f"/api/bots/{b}/listing", json={"listed": False}, headers=H2).status_code == 404


def test_telegram_shared_bot_has_its_own_directory(env):
    c, calls = env
    H = owner(c, "tg@x.com")
    b1, b2 = bot(c, H), bot(c, H)
    c.post(f"/api/bots/{b1}/publish", json={"mode": "shared"}, headers=H)          # Bale only
    c.post(f"/api/bots/{b2}/telegram/publish", json={"mode": "shared"}, headers=H)  # Telegram only
    c.post(f"/api/tghook/shared/{telegram.shared_hook_secret()}", json=msg(90, "/start"))
    assert [d for _, d in buttons(last_out(calls, 90, "tg"))] == ["bdir:1"]       # the Telegram publication, not the Bale one
    c.post(f"/api/tghook/shared/{telegram.shared_hook_secret()}", json=cb(90, "bdir:1"))
    assert "خوش آمدید" in [p for m, p in calls["tg"] if m == "sendMessage" and p["chat_id"] == "90"][-2]["text"]


def test_bot_list_shows_where_each_bot_is_live_and_its_last_change(env):
    from app.db import SessionLocal
    from app.models import VersionTests

    c, _ = env
    H = owner(c, "cards@x.com")
    both, bale_only, none = bot(c, H), bot(c, H), bot(c, H)
    draft = c.post("/api/bots/draft", json={}, headers=H).json()["id"]
    c.post(f"/api/bots/{both}/publish", json={"mode": "shared"}, headers=H)
    c.post(f"/api/bots/{both}/telegram/publish", json={"mode": "shared"}, headers=H)
    c.post(f"/api/bots/{bale_only}/publish", json={"mode": "shared"}, headers=H)
    with SessionLocal() as db:
        db.add(VersionTests(bot_id=none, version=1, scenarios=[], results=[{"name": "a", "passed": True, "failures": [], "transcript": []},
                                                                           {"name": "b", "passed": False, "failures": ["x"], "transcript": []}]))
        db.commit()
    cards = {b["id"]: b for b in c.get("/api/bots", headers=H).json()}
    assert sorted(x["messenger"] for x in cards[both]["live"]) == ["bale", "tg"] and cards[both]["live"][0]["version"] == 1
    assert [x["messenger"] for x in cards[bale_only]["live"]] == ["bale"]
    assert cards[none]["live"] == [] and cards[none]["tests"] == {"passed": 1, "total": 2}
    assert cards[both]["tests"] is None and cards[both]["last_change"]["note"] and cards[both]["last_change"]["at"]
    assert cards[draft]["version"] == 0 and cards[draft]["live"] == [] and cards[draft]["last_change"] is None
    assert all(card["spec"] is None for card in cards.values())  # the list stays light
