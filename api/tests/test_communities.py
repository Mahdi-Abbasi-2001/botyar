"""Linking groups/channels with a one-time code, post forwarding, group moderation."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from datetime import datetime, timedelta, timezone  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import bale  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Bot, BotVersion, ChatBinding, ForwardRule, GroupRule, LinkToken, User, VersionTests  # noqa: E402

SPEC = {"name": "کافه", "welcome": "سلام", "menu": [{"label": "درباره", "block": "a"}], "blocks": [{"type": "message", "id": "a", "text": "ما کافه‌ایم"}]}


@pytest.fixture()
def cw(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    bale._seen.clear()
    from app import communities

    communities._admin_cache.clear()
    monkeypatch.setattr(settings, "public_base_url", "https://example.test")
    monkeypatch.setattr(settings, "bale_shared_bot_token", "SHAREDTOKEN")
    calls, st = [], {"admins": {"-100": {1}, "-200": {1}, "-300": {1}}, "fail": set()}

    def fake(token, method, payload=None, timeout=15):
        calls.append((method, dict(payload or {})))
        if method in st["fail"]:
            raise bale.BaleError(f"{method} failed")
        if method == "getMe":
            return {"username": "botyar_test_bot", "id": 9999}
        if method == "getChatMember":
            return {"status": "administrator" if payload["user_id"] in st["admins"].get(str(payload["chat_id"]), set()) else "member"}
        return True

    monkeypatch.setattr(bale, "api_call", fake)
    with TestClient(app) as c:
        tok = c.post("/api/auth/register", json={"username": "c_x.com", "password": "123456"}).json()["token"]
        H = {"Authorization": f"Bearer {tok}"}
        with SessionLocal() as db:
            uid = db.query(User).filter(User.username == "c_x.com").one().id
            bot = Bot(user_id=uid, name="کافه")
            db.add(bot); db.flush()
            db.add(BotVersion(bot_id=bot.id, version=1, spec=SPEC, note=""))
            db.add(VersionTests(bot_id=bot.id, version=1, scenarios=[], results=[{"name": "t", "passed": True, "failures": [], "transcript": []}]))
            db.commit()
            bid = bot.id
        c.post(f"/api/bots/{bid}/publish", json={"mode": "shared"}, headers=H)
        n = [80000]

        def post(update):
            n[0] += 1
            update["update_id"] = n[0]
            return c.post(f"/api/hook/shared/{bale.shared_hook_secret()}", json=update)

        def channel_post(chat_id, text, mid=10):
            return post({"channel_post": {"message_id": mid, "chat": {"id": int(chat_id), "type": "channel", "title": f"کانال {chat_id}"}, "text": text}})

        def group_msg(chat_id, uid, text, mid=20, **extra):
            return post({"message": {"message_id": mid, "from": {"id": uid, "first_name": f"کاربر{uid}"}, "chat": {"id": int(chat_id), "type": "supergroup", "title": f"گروه {chat_id}"}, "text": text, **extra}})

        def link(kind_fn, chat_id, uid=None):
            code = c.post(f"/api/bots/{bid}/link-token", headers=H).json()["code"]
            (kind_fn(chat_id, f"/link {code}") if uid is None else kind_fn(chat_id, uid, f"/link {code}"))
            return code

        yield c, H, bid, calls, st, channel_post, group_msg, link


def methods(calls, name):
    return [p for m, p in calls if m == name]


def test_link_token_links_a_channel_once_deletes_the_message_and_reports_back(cw):
    c, H, bid, calls, st, channel_post, group_msg, link = cw
    t = c.post(f"/api/bots/{bid}/link-token", headers=H).json()
    assert len(t["code"]) == 8 and t["command"] == f"/link {t['code']}" and t["expires_minutes"] == 15
    calls.clear()
    channel_post(-100, t["command"], mid=55)
    assert methods(calls, "deleteMessage") == [{"chat_id": "-100", "message_id": 55}]               # the code does not stay visible
    assert any("وصل شد" in p["text"] for p in methods(calls, "sendMessage"))
    chats = c.get(f"/api/bots/{bid}/chats", headers=H).json()["chats"]
    assert [(x["messenger"], x["kind"], x["title"]) for x in chats] == [("bale", "channel", "کانال -100")]
    calls.clear()
    channel_post(-200, t["command"])                                                                  # a used code does nothing
    assert any("نامعتبر" in p["text"] for p in methods(calls, "sendMessage")) and len(c.get(f"/api/bots/{bid}/chats", headers=H).json()["chats"]) == 1
    channel_post(-200, "/link ZZZZZZZZ")
    channel_post(-200, "/link")
    assert len(c.get(f"/api/bots/{bid}/chats", headers=H).json()["chats"]) == 1


def test_expired_code_and_non_admin_group_link_are_refused(cw):
    c, H, bid, calls, st, channel_post, group_msg, link = cw
    t = c.post(f"/api/bots/{bid}/link-token", headers=H).json()
    with SessionLocal() as db:
        row = db.query(LinkToken).one()
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    channel_post(-100, t["command"])
    assert c.get(f"/api/bots/{bid}/chats", headers=H).json()["chats"] == []
    t2 = c.post(f"/api/bots/{bid}/link-token", headers=H).json()
    calls.clear()
    group_msg(-300, 2, t2["command"])                                                                 # user 2 is not an admin of the group
    assert any("فقط مدیر گروه" in p["text"] for p in methods(calls, "sendMessage")) and c.get(f"/api/bots/{bid}/chats", headers=H).json()["chats"] == []
    group_msg(-300, 1, t2["command"])                                                                 # user 1 is
    chats = c.get(f"/api/bots/{bid}/chats", headers=H).json()["chats"]
    assert chats[0]["kind"] == "group" and chats[0]["rule"]["delete_links"] is True and chats[0]["rule"]["max_warnings"] == 3


def test_a_chat_cannot_be_hijacked_by_another_owner(cw):
    c, H, bid, calls, st, channel_post, group_msg, link = cw
    link(channel_post, -100)
    other = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"username": "z_x.com", "password": "123456"}).json()["token"]}
    with SessionLocal() as db:
        uid = db.query(User).filter(User.username == "z_x.com").one().id
        b2 = Bot(user_id=uid, name="دیگری")
        db.add(b2); db.flush()
        db.add(BotVersion(bot_id=b2.id, version=1, spec=SPEC, note=""))
        db.add(VersionTests(bot_id=b2.id, version=1, scenarios=[], results=[{"name": "t", "passed": True, "failures": [], "transcript": []}]))
        db.commit()
        b2id = b2.id
    code = c.post(f"/api/bots/{b2id}/link-token", headers=other).json()["code"]
    calls.clear()
    channel_post(-100, f"/link {code}")
    assert any("قبلاً به ربات دیگری وصل" in p["text"] for p in methods(calls, "sendMessage"))
    assert c.get(f"/api/bots/{b2id}/chats", headers=other).json()["chats"] == []
    assert c.get(f"/api/bots/{bid}/chats", headers=other).status_code == 404
    assert c.post(f"/api/bots/{bid}/link-token", headers=other).status_code == 404


def test_forwarding_copies_channel_posts_and_refuses_loops_and_unlinked_sources(cw):
    c, H, bid, calls, st, channel_post, group_msg, link = cw
    link(channel_post, -100); link(channel_post, -200)
    ids = {x["title"]: x["id"] for x in c.get(f"/api/bots/{bid}/chats", headers=H).json()["chats"]}
    a, b = ids["کانال -100"], ids["کانال -200"]
    assert c.post(f"/api/bots/{bid}/forwards", json={"source": a, "dest": a}, headers=H).status_code == 422
    assert c.post(f"/api/bots/{bid}/forwards", json={"source": a, "dest": b}, headers=H).status_code == 200
    assert c.post(f"/api/bots/{bid}/forwards", json={"source": a, "dest": b}, headers=H).status_code == 409
    assert c.post(f"/api/bots/{bid}/forwards", json={"source": b, "dest": a}, headers=H).status_code == 422   # would loop forever
    calls.clear()
    channel_post(-100, "تخفیف امروز", mid=77)
    assert methods(calls, "copyMessage") == [{"chat_id": "-200", "from_chat_id": "-100", "message_id": 77}]
    calls.clear()
    channel_post(-200, "پست کانال مقصد")                                                               # destination posts go nowhere
    channel_post(-999, "کانال ناشناس")
    assert methods(calls, "copyMessage") == []
    rules = c.get(f"/api/bots/{bid}/chats", headers=H).json()["forwards"]
    assert rules[0]["forwarded"] == 1 and rules[0]["last_error"] == ""
    st["fail"].add("copyMessage")
    channel_post(-100, "دوباره")
    assert "copyMessage failed" in c.get(f"/api/bots/{bid}/chats", headers=H).json()["forwards"][0]["last_error"]
    rid = rules[0]["id"]
    assert c.delete(f"/api/bots/{bid}/forwards/{rid}", headers=H).status_code == 200
    st["fail"].clear(); calls.clear()
    channel_post(-100, "بعد از حذف")
    assert methods(calls, "copyMessage") == []


def test_forwarding_to_a_group_and_across_messengers_is_text_only(cw):
    c, H, bid, calls, st, channel_post, group_msg, link = cw
    link(channel_post, -100)
    with SessionLocal() as db:   # a Telegram channel bound to the same bot, but the bot is not published on Telegram
        tg = ChatBinding(bot_id=bid, ch="tg", chat_id="-777", kind="channel", title="تلگرام")
        db.add(tg); db.commit()
        tg_id = tg.id
    src = c.get(f"/api/bots/{bid}/chats", headers=H).json()["chats"][0]["id"]
    assert c.post(f"/api/bots/{bid}/forwards", json={"source": src, "dest": tg_id}, headers=H).status_code == 200
    channel_post(-100, "پست")
    err = c.get(f"/api/bots/{bid}/chats", headers=H).json()["forwards"][0]["last_error"]
    assert "منتشر نشده" in err
    assert c.post(f"/api/bots/{bid}/forwards", json={"source": tg_id, "dest": src}, headers=H).status_code == 422   # a loop across messengers too
    # a group can be a destination but never a source
    code = c.post(f"/api/bots/{bid}/link-token", headers=H).json()["code"]
    group_msg(-300, 1, f"/link {code}")
    gid = [x["id"] for x in c.get(f"/api/bots/{bid}/chats", headers=H).json()["chats"] if x["kind"] == "group"][0]
    assert c.post(f"/api/bots/{bid}/forwards", json={"source": gid, "dest": src}, headers=H).status_code == 422
    assert c.post(f"/api/bots/{bid}/forwards", json={"source": src, "dest": gid}, headers=H).status_code == 200


def linked_group(cw):
    c, H, bid, calls, st, channel_post, group_msg, link = cw
    link(group_msg, -300, uid=1)
    return c.get(f"/api/bots/{bid}/chats", headers=H).json()["chats"][0]["id"]


def test_moderation_deletes_links_warns_then_bans_and_spares_admins_and_normal_chat(cw):
    c, H, bid, calls, st, channel_post, group_msg, link = cw
    linked_group(cw)
    calls.clear()
    group_msg(-300, 5, "سلام به همه", mid=1)
    group_msg(-300, 1, "ببینید https://spam.example", mid=2)                                          # an admin: never moderated
    assert methods(calls, "deleteMessage") == []
    for i, bad in enumerate(["بیایید https://spam.example", "کانال ما @spamchannel", "سایت spam.ir"], start=3):
        group_msg(-300, 5, bad, mid=i)
    assert [p["message_id"] for p in methods(calls, "deleteMessage")] == [3, 4, 5]
    assert methods(calls, "banChatMember") == [{"chat_id": "-300", "user_id": 5}]                      # the 3rd warning bans
    assert any("حذف شد" in p["text"] for p in methods(calls, "sendMessage"))
    rule = c.get(f"/api/bots/{bid}/chats", headers=H).json()["chats"][0]["rule"]
    assert rule["deleted"] == 3 and rule["banned"] == 1
    calls.clear()
    group_msg(-300, 6, "یک پیام عادی بدون لینک", mid=9)
    assert methods(calls, "deleteMessage") == []


def test_moderation_settings_banned_words_forwards_welcome_and_delete_only_mode(cw):
    c, H, bid, calls, st, channel_post, group_msg, link = cw
    gid = linked_group(cw)
    body = {"delete_links": False, "delete_forwards": True, "banned_words": ["قمار", " کلاهبرداری "], "max_warnings": 0, "welcome_text": "سلام {name} به گروه خوش آمدی"}
    assert c.put(f"/api/bots/{bid}/chats/{gid}/moderation", json=body, headers=H).status_code == 200
    calls.clear()
    group_msg(-300, 5, "https://ok.example", mid=1)                                                    # links are allowed now
    group_msg(-300, 5, "بیا قمار کنیم", mid=2)
    group_msg(-300, 5, "این کلاهبرداری است", mid=3)
    group_msg(-300, 5, "پیام فوروارد", mid=4, forward_date=123)
    assert [p["message_id"] for p in methods(calls, "deleteMessage")] == [2, 3, 4]
    for i in range(5, 12):
        group_msg(-300, 5, "قمار", mid=i)
    assert methods(calls, "banChatMember") == []                                                       # max_warnings 0 = only delete
    calls.clear()
    c.post(f"/api/hook/shared/{bale.shared_hook_secret()}", json={"update_id": 99999, "message": {
        "message_id": 30, "chat": {"id": -300, "type": "supergroup", "title": "g"}, "new_chat_members": [{"id": 8, "first_name": "مینا"}, {"id": 9, "first_name": "ربات", "is_bot": True}]}})
    assert [p["text"] for p in methods(calls, "sendMessage")] == ["سلام مینا به گروه خوش آمدی"]
    assert c.put(f"/api/bots/{bid}/chats/{gid}/moderation", json={**body, "max_warnings": 99}, headers=H).status_code == 422
    assert c.put(f"/api/bots/{bid}/chats/{gid}/moderation", json={**body, "banned_words": ["x"] * 51}, headers=H).status_code == 422


def test_admin_commands_ban_unban_warns_work_only_for_admins_on_replies(cw):
    c, H, bid, calls, st, channel_post, group_msg, link = cw
    linked_group(cw)
    reply = {"reply_to_message": {"message_id": 1, "from": {"id": 5, "first_name": "بد"}}}
    calls.clear()
    group_msg(-300, 6, "/ban", mid=2, **reply)                                                          # a normal member: ignored
    assert methods(calls, "banChatMember") == []
    group_msg(-300, 1, "/ban", mid=3)                                                                   # admin but no reply
    assert any("ریپلای" in p["text"] for p in methods(calls, "sendMessage"))
    group_msg(-300, 1, "/ban", mid=4, **reply)
    assert methods(calls, "banChatMember") == [{"chat_id": "-300", "user_id": 5}]
    group_msg(-300, 1, "/unban", mid=5, **reply)
    assert methods(calls, "unbanChatMember") == [{"chat_id": "-300", "user_id": 5, "only_if_banned": True}]
    group_msg(-300, 5, "https://a.example", mid=6)
    calls.clear()
    group_msg(-300, 1, "/warns", mid=7, **reply)
    assert any("اخطارهای این کاربر: 1" in p["text"] for p in methods(calls, "sendMessage"))


def test_failures_do_not_crash_and_unlinked_groups_are_ignored(cw):
    c, H, bid, calls, st, channel_post, group_msg, link = cw
    linked_group(cw)
    st["fail"] |= {"deleteMessage", "banChatMember"}
    for i in range(3):
        assert group_msg(-300, 5, "https://x.example", mid=i + 1).status_code == 200                    # bot not admin / message too old
    calls.clear()
    group_msg(-555, 5, "https://x.example")                                                              # a group nobody linked
    assert methods(calls, "deleteMessage") == []


def test_unlinking_removes_rules_and_authorisation(cw):
    c, H, bid, calls, st, channel_post, group_msg, link = cw
    link(channel_post, -100); link(channel_post, -200)
    ch = {x["title"]: x["id"] for x in c.get(f"/api/bots/{bid}/chats", headers=H).json()["chats"]}
    c.post(f"/api/bots/{bid}/forwards", json={"source": ch["کانال -100"], "dest": ch["کانال -200"]}, headers=H)
    other = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"username": "z_x.com", "password": "123456"}).json()["token"]}
    assert c.delete(f"/api/bots/{bid}/chats/{ch['کانال -100']}", headers=other).status_code == 404
    assert c.delete(f"/api/bots/{bid}/chats/{ch['کانال -100']}", headers=H).status_code == 200
    with SessionLocal() as db:
        assert db.query(ForwardRule).count() == 0 and db.query(ChatBinding).count() == 1
    assert c.delete(f"/api/bots/{bid}/chats/99999", headers=H).status_code == 404
    for i in range(communities_max() - 1):
        c.post(f"/api/bots/{bid}/link-token", headers=H)
    # the 10-chat limit is checked when a token is requested
    with SessionLocal() as db:
        for i in range(communities_max()):
            db.add(ChatBinding(bot_id=bid, ch="bale", chat_id=str(i), kind="channel"))
        db.commit()
    assert c.post(f"/api/bots/{bid}/link-token", headers=H).status_code == 409


def communities_max():
    from app import communities

    return communities.MAX_BINDINGS
