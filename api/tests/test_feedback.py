"""Feedback block: 1-5 rating, optional comment, owner notification, flood limit."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from app.engine import MemoryStore, handle, new_session  # noqa: E402
from app.spec import BotSpec  # noqa: E402

SPEC = BotSpec.model_validate({
    "name": "کافه", "welcome": "سلام", "menu": [{"label": "نظر شما", "block": "fb"}],
    "blocks": [{"type": "feedback", "id": "fb", "title": "نظرسنجی"}, {"type": "admin_notify", "id": "n", "on": "fb", "text": "نظر جدید"}]})


def chat(store, cust="bale:1"):
    s = new_session()
    s["cust"] = cust
    return s


def say(s, store, *texts):
    out = None
    for t in texts:
        out = handle(SPEC, s, t, store)
    return out


def test_rating_then_comment_is_stored_and_owner_notified():
    store, s = MemoryStore(), chat(None)
    out = say(s, store, "/start", "m:0", "r:4", "قهوه عالی بود")
    assert any(a["type"] == "notify_admin" and "قهوه" in a["text"] and "⭐⭐⭐⭐" in a["text"] for a in out)
    assert [(r["rating"], r["comment"]) for r in store.find("fb")] == [(4, "قهوه عالی بود")]


def test_skip_comment_and_invalid_rating():
    store, s = MemoryStore(), chat(None)
    out = say(s, store, "/start", "m:0", "سلام")
    assert s["step"] == "rate" and "دکمه" in out[0]["text"]
    say(s, store, "r:9")
    assert s["step"] == "rate"
    say(s, store, "r:5", "sk")
    assert store.find("fb")[0]["comment"] == "" and s["block"] is None


def test_daily_limit_per_customer():
    store, s = MemoryStore(), chat(None)
    for i in range(7):
        out = say(s, store, "/start", "m:0", "r:5", "sk")
    assert len(store.find("fb")) == 5 and "ثبت شده" in out[0]["text"]
    s2 = chat(None, "bale:2")
    say(s2, store, "/start", "m:0", "r:1", "sk")
    assert len(store.find("fb")) == 6
