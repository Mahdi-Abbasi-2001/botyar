"""Through Bale and the API: anonymous chat rooms and time limits, invites that count after a first order, saved inbox
replies, and the feedback report over time."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from datetime import datetime, timedelta, timezone  # noqa: E402

import pytest  # noqa: E402

from app import anon, outreach  # noqa: E402
from app.dates import now_tehran  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import AnonPair, ReferralJoin, Record  # noqa: E402

from tests.test_referral_gate import driver, world  # noqa: E402,F401


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    anon._hits.clear()
    yield


def texts(sent, chat_id):
    return [t for ch, t, _ in sent if ch == str(chat_id)]


ANON = {"name": "باشگاه", "welcome": "سلام", "menu": [{"label": "چت ناشناس", "block": "anon"}],
        "blocks": [{"type": "anon_chat", "id": "anon", "title": "چت ناشناس", "topics": ["درس", "سرگرمی"], "max_minutes": 20}]}


def open_bot(world, spec, people):
    c, H, make, sent, _ = world
    bid = make(spec)
    pub = c.post(f"/api/bots/{bid}/publish", json={"mode": "shared"}, headers=H).json()
    msg, tap = driver(c)
    for chat_id in people:
        msg(chat_id, f"/start {pub['code']}", f"کاربر {chat_id}")
    return c, H, bid, sent, msg, tap, pub


def test_people_are_paired_only_within_their_room_and_long_chats_end(world):
    c, H, bid, sent, msg, tap, _ = open_bot(world, ANON, (901, 902, 903))
    tap(901, "m:0"); tap(901, "ac:find:0")                                      # «درس»
    tap(902, "m:0"); tap(902, "ac:find:1")                                      # «سرگرمی»: no match with 901
    assert not any("شریک گفتگو پیدا شد" in t for t in texts(sent, 901) + texts(sent, 902))
    sent.clear()
    tap(903, "m:0"); tap(903, "ac:find:0")                                      # «درس» again: paired with 901
    assert any("شریک گفتگو پیدا شد" in t for t in texts(sent, 901)) and any("شریک گفتگو پیدا شد" in t for t in texts(sent, 903))
    with SessionLocal() as db:
        outreach.expire_anon_waiting(db, datetime.now(timezone.utc) + timedelta(minutes=10))  # 902, alone in its room, stops waiting
        assert db.query(AnonPair).filter(AnonPair.active.is_(True)).count() == 1                  # the chat itself goes on
    sent.clear()
    with SessionLocal() as db:
        outreach.expire_anon_waiting(db, datetime.now(timezone.utc) + timedelta(minutes=21))
        assert db.query(AnonPair).filter(AnonPair.active.is_(True)).count() == 0
    assert any("زمان این گفت‌وگو (۲۰ دقیقه) تمام شد" in t for t in texts(sent, 901))
    assert any("زمان این گفت‌وگو" in t for t in texts(sent, 903))


INVITE = {"name": "کافه", "welcome": "سلام", "menu": [{"label": "دعوت", "block": "ref"}, {"label": "سفارش", "block": "o"}],
          "blocks": [{"type": "referral", "id": "ref", "title": "دعوت", "goal": 1, "reward_text": "یک قهوه رایگان", "reward_code": "FRIEND",
                      "count_after": "order"},
                     {"type": "catalog_order", "id": "o", "title": "منو", "items": [{"id": "a", "name": "کیک", "price": 50000}],
                      "fields": [{"key": "name", "label": "نام؟"}], "discount_codes": [{"code": "FRIEND", "percent": 10}]}]}


def test_an_invite_counts_only_after_the_friends_first_order_and_the_code_arrives(world):
    c, H, bid, sent, msg, tap, pub = open_bot(world, INVITE, (911,))
    tap(911, "m:0")
    code = [t for t in texts(sent, 911) if "start=" in t][0].split("start=")[1].split()[0].strip()
    sent.clear()
    msg(912, f"/start {code}", "علی")
    assert any("وقتی اولین سفارش یا نوبتش را ثبت کند" in t for t in texts(sent, 911))
    with SessionLocal() as db:
        assert db.query(ReferralJoin).one().confirmed is False
    tap(911, "m:0")
    assert any("0 از 1" in t.replace("۰", "0").replace("۱", "1") for t in texts(sent, 911))
    sent.clear()
    tap(912, "m:1"); tap(912, "i:a"); tap(912, "checkout"); tap(912, "dc:no"); msg(912, "علی", "علی")  # the friend's first order
    got = " ".join(texts(sent, 911))
    assert "اولین سفارش یا نوبتش را ثبت کرد" in got and "به هدف رسیدید" in got and "FRIEND" in got
    with SessionLocal() as db:
        assert db.query(ReferralJoin).one().confirmed is True
    sent.clear()
    tap(912, "m:1"); tap(912, "i:a"); tap(912, "checkout"); tap(912, "dc:no"); msg(912, "علی", "علی")  # a second order counts nothing more
    assert texts(sent, 911) == []


def test_saved_replies_crud_and_ownership(world):
    c, H, make, _, _ = world
    bid = make(ANON)
    r = c.post(f"/api/bots/{bid}/inbox/replies", json={"text": "سفارش شما فردا ارسال می‌شود."}, headers=H).json()
    assert c.get(f"/api/bots/{bid}/inbox/replies", headers=H).json() == [r]
    other = c.post("/api/auth/register", json={"username": "evil_inbox", "password": "123456"}).json()["token"]
    O = {"Authorization": f"Bearer {other}"}
    assert c.get(f"/api/bots/{bid}/inbox/replies", headers=O).status_code == 404
    assert c.delete(f"/api/bots/{bid}/inbox/replies/{r['id']}", headers=O).status_code == 404
    assert c.post(f"/api/bots/{bid}/inbox/replies", json={"text": "  "}, headers=H).status_code == 422
    assert c.delete(f"/api/bots/{bid}/inbox/replies/{r['id']}", headers=H).json() == {"ok": True}
    assert c.get(f"/api/bots/{bid}/inbox/replies", headers=H).json() == []


def test_feedback_report_by_week(world):
    c, H, make, _, _ = world
    spec = {"name": "x", "welcome": "س", "menu": [{"label": "نظر", "block": "f"}],
            "blocks": [{"type": "feedback", "id": "f", "title": "نظر شما", "aspects": ["غذا", "برخورد"]}]}
    bid = make(spec)
    now = now_tehran()
    with SessionLocal() as db:
        for days, rating, food in ((0, 5, 5), (1, 3, 2), (14, 1, 1)):
            at = (now - timedelta(days=days)).isoformat()
            db.add(Record(bot_id=bid, collection="f", sandbox=False, data={"rating": rating, "ratings": {"غذا": food, "برخورد": rating}, "_at": at}))
        db.commit()
    data = c.get(f"/api/bots/{bid}/feedback/stats?weeks=4", headers=H).json()
    f = data[0]
    assert f["title"] == "نظر شما" and f["count"] == 3 and f["avg"] == 3.0 and f["aspects"] == {"غذا": 2.67, "برخورد": 3.0}
    assert len(f["weeks"]) == 4 and sum(w["count"] for w in f["weeks"]) == 3 and f["weeks"][-1]["avg"] is not None
