import itertools
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import bale  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

uid = itertools.count(1000)


@pytest.fixture()
def env(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "public_base_url", "https://example.test")
    monkeypatch.setattr(settings, "bale_shared_bot_token", "SHAREDTOKEN")
    calls: list[tuple[str, dict]] = []

    def fake(token, method, payload=None, timeout=15):
        calls.append((method, payload or {}))
        if method == "getMe":
            return {"username": "botyar_test_bot"}
        return True

    monkeypatch.setattr(bale, "api_call", fake)
    bale._username_cache.clear()
    with TestClient(app) as c:
        yield c, calls


def msg(chat, text):
    return {"update_id": next(uid), "message": {"message_id": 1, "chat": {"id": chat, "type": "private"}, "text": text}}


def cb(chat, data):
    return {"update_id": next(uid), "callback_query": {"id": "q1", "from": {"id": chat}, "data": data,
                                                       "message": {"chat": {"id": chat, "type": "private"}}}}


def sent(calls, chat):
    return [p for m, p in calls if m == "sendMessage" and str(p["chat_id"]) == str(chat)]


def test_shared_bot_full_journey(env):
    c, calls = env
    tok = c.post("/api/auth/register", json={"username": "o_x.com", "password": "123456"}).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    bot = c.post("/api/bots", json={"template": "workshop"}, headers=H).json()["id"]
    st = c.post(f"/api/bots/{bot}/publish", json={"mode": "shared"}, headers=H).json()
    assert st["published"] and st["mode"] == "shared" and len(st["code"]) == 6 and st["shared_bot_username"] == "botyar_test_bot"
    url = f"/api/hook/shared/{bale.shared_hook_secret()}"

    assert c.post("/api/hook/shared/wrong", json=msg(1, "hi")).status_code == 404

    # a chat without a link gets the directory of published bots
    c.post(url, json=msg(111, "/start"))
    directory = sent(calls, 111)[-1]
    assert "کدام کسب‌وکار" in directory["text"]
    assert [b[0]["callback_data"] for b in directory["reply_markup"]["inline_keyboard"]] == ["bdir:1"]
    # a code TYPED as a message no longer opens a bot (only the link does)
    c.post(url, json=msg(111, st["code"]))
    assert "کدام کسب‌وکار" in sent(calls, 111)[-1]["text"]
    # the link (ble.ir/<bot>?start=CODE arrives as "/start CODE") opens the bot: welcome + menu with inline buttons
    c.post(url, json=msg(111, f"/start {st['code'].lower()}"))
    out = sent(calls, 111)
    assert "خوش آمدید" in out[-2]["text"] and len(out[-1]["reply_markup"]["inline_keyboard"]) == 2

    # owner links their chat for notifications
    c.post(url, json=msg(999, f"/admin {st['admin_code']}"))
    assert c.get(f"/api/bots/{bot}/publication", headers=H).json()["admin_linked"] is True
    c.post(url, json=msg(999, "/admin WRONGCODE"))
    assert "نامعتبر" in sent(calls, 999)[-1]["text"]

    # customer books via buttons; callback queries are acknowledged
    for step in [cb(111, "m:0"), cb(111, "s:thu1"), msg(111, "علی"), msg(111, "۰۹۱۲۳۴۵۶۷۸۹")]:
        c.post(url, json=step)
    assert any(m == "answerCallbackQuery" for m, _ in calls)
    assert "با موفقیت" in sent(calls, 111)[-2]["text"]
    assert "🔔" in sent(calls, 999)[-1]["text"] and "علی" in sent(calls, 999)[-1]["text"]

    live = c.get(f"/api/bots/{bot}/records?sandbox=false", headers=H).json()
    assert len(live) == 1 and live[0]["data"]["phone"] == "09123456789"
    assert c.get(f"/api/bots/{bot}/records?sandbox=true", headers=H).json() == []

    # /switch forgets the link and shows the directory; picking from it opens the bot again
    c.post(url, json=msg(111, "/switch"))
    assert "کدام کسب‌وکار" in sent(calls, 111)[-1]["text"]
    c.post(url, json=msg(111, "m:0"))
    assert "کدام کسب‌وکار" in sent(calls, 111)[-1]["text"]
    c.post(url, json=cb(111, "bdir:1"))
    assert "خوش آمدید" in sent(calls, 111)[-2]["text"]


def test_duplicate_delivery_is_ignored(env):
    c, calls = env
    tok = c.post("/api/auth/register", json={"username": "d_x.com", "password": "123456"}).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    bot = c.post("/api/bots", json={"template": "cafe"}, headers=H).json()["id"]
    code = c.post(f"/api/bots/{bot}/publish", json={"mode": "shared"}, headers=H).json()["code"]
    url = f"/api/hook/shared/{bale.shared_hook_secret()}"
    same = msg(222, f"/start {code}")
    c.post(url, json=same)
    n = len(sent(calls, 222))
    c.post(url, json=same)  # Bale retry of the very same update
    assert len(sent(calls, 222)) == n


def test_long_button_data_gets_a_short_token():
    long_label = "گزینه‌ای با نام خیلی خیلی طولانی فارسی که از شصت و چهار بایت بیشتر است"
    store: dict = {}
    mk = bale.to_markup([{"text": long_label, "data": long_label}, {"text": "کوتاه", "data": "m:0"}], store)
    d0 = mk["inline_keyboard"][0][0]["callback_data"]
    assert d0 == "~0" and store["~0"] == long_label and len(d0.encode()) <= 64
    assert mk["inline_keyboard"][1][0]["callback_data"] == "m:0"


def test_cannot_publish_when_tests_fail(env):
    from app.db import SessionLocal
    from app.models import VersionTests

    c, _ = env
    tok = c.post("/api/auth/register", json={"username": "f_x.com", "password": "123456"}).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    bot = c.post("/api/bots", json={"template": "cafe"}, headers=H).json()["id"]
    with SessionLocal() as db:
        db.add(VersionTests(bot_id=bot, version=1, scenarios=[], results=[{"name": "x", "passed": False, "failures": ["boom"], "transcript": []}]))
        db.commit()
    r = c.post(f"/api/bots/{bot}/publish", json={"mode": "shared"}, headers=H)
    assert r.status_code == 409 and "تست" in r.json()["detail"]


def test_next_page_edits_the_clicked_message_but_typed_text_sends_new(env):
    from app.db import SessionLocal
    from app.models import Bot, BotVersion, Product, User

    c, calls = env
    tok = c.post("/api/auth/register", json={"username": "pg_x.com", "password": "123456"}).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    spec = {"name": "shop", "welcome": "سلام", "menu": [{"label": "خرید", "block": "shop"}],
            "blocks": [{"type": "catalog_order", "id": "shop", "title": "فروشگاه", "source": "table", "items": []}]}
    with SessionLocal() as db:
        uid = db.query(User).filter(User.username == "pg_x.com").one().id
        bot = Bot(user_id=uid, name="shop")
        db.add(bot)
        db.flush()
        db.add(BotVersion(bot_id=bot.id, version=1, spec=spec, note=""))
        for i in range(12):
            db.add(Product(bot_id=bot.id, block_id="shop", name=f"کالا {i}", category="", price=1000 * (i + 1), stock=None, options=[], position=i))
        db.commit()
        bid = bot.id
    code = c.post(f"/api/bots/{bid}/publish", json={"mode": "shared"}, headers=H).json()["code"]
    url = f"/api/hook/shared/{bale.shared_hook_secret()}"
    c.post(url, json=msg(777, f"/start {code}"))
    c.post(url, json=cb(777, "m:0"))                       # first list page (a normal new message)
    calls.clear()
    click = cb(777, "pg:1")
    click["callback_query"]["message"]["message_id"] = 4242
    c.post(url, json=click)
    methods = [m for m, _ in calls]
    assert "editMessageText" in methods and "sendMessage" not in methods
    edit = next(p for m, p in calls if m == "editMessageText")
    assert edit["message_id"] == 4242 and "صفحه ۲" in edit["text"]

    calls.clear()
    c.post(url, json=msg(777, "کالا 3"))                   # typed search: nothing to edit
    assert [m for m, _ in calls] == ["sendMessage"]


def test_edit_failure_falls_back_to_a_new_message():
    sent = []

    def fake(token, method, payload=None, timeout=15):
        sent.append(method)
        if method == "editMessageText":
            raise bale.BaleError("message can't be edited")
        return True

    orig = bale.api_call
    bale.api_call = fake
    try:
        bale.deliver("T", "1", [{"type": "send", "text": "صفحه 2", "buttons": [], "edit": True}], {}, "", 55)
    finally:
        bale.api_call = orig
    assert sent == ["editMessageText", "sendMessage"]


def test_customers_see_persian_digits_but_callback_data_stays_ascii(env):
    c, calls = env
    tok = c.post("/api/auth/register", json={"username": "dg_x.com", "password": "123456"}).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    bot = c.post("/api/bots", json={"template": "workshop"}, headers=H).json()["id"]
    code = c.post(f"/api/bots/{bot}/publish", json={"mode": "shared"}, headers=H).json()["code"]
    url = f"/api/hook/shared/{bale.shared_hook_secret()}"
    c.post(url, json=msg(333, f"/start {code}"))
    c.post(url, json=cb(333, "m:0"))
    last = sent(calls, 333)[-1]
    buttons = [b[0] for b in last["reply_markup"]["inline_keyboard"]]
    assert any("۱۲ جای خالی" in b["text"] for b in buttons) and not any(ch in b["text"] for b in buttons for ch in "0123456789")
    assert [b["callback_data"] for b in buttons] == ["s:thu1", "s:thu2"]  # engine input is untouched
    c.post(url, json=cb(333, "s:thu1"))
    c.post(url, json=msg(333, "علی"))
    c.post(url, json=msg(333, "09123456789"))              # the customer's own typing is stored as typed
    assert c.get(f"/api/bots/{bot}/records?sandbox=false", headers=H).json()[0]["data"]["phone"] == "09123456789"


def test_owner_notification_keeps_phone_digits_as_typed(env):
    c, calls = env
    tok = c.post("/api/auth/register", json={"username": "nt_x.com", "password": "123456"}).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    bot = c.post("/api/bots", json={"template": "workshop"}, headers=H).json()["id"]
    st = c.post(f"/api/bots/{bot}/publish", json={"mode": "shared"}, headers=H).json()
    url = f"/api/hook/shared/{bale.shared_hook_secret()}"
    c.post(url, json=msg(555, f"/admin {st['admin_code']}"))
    c.post(url, json=msg(556, f"/start {st['code']}"))
    for step in [cb(556, "m:0"), cb(556, "s:thu1"), msg(556, "علی"), msg(556, "09123456789")]:
        c.post(url, json=step)
    note = sent(calls, 555)[-1]["text"]
    assert "09123456789" in note and "۰۹۱۲" not in note


def test_cancel_on_bale_promotes_the_waiting_customer_and_messages_them(env):
    from app.db import SessionLocal
    from app.models import Bot, BotVersion, User

    c, calls = env
    tok = c.post("/api/auth/register", json={"username": "cx_x.com", "password": "123456"}).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    spec = {"name": "کلاس", "welcome": "سلام", "menu": [{"label": "ثبت‌نام", "block": "b"}],
            "blocks": [{"type": "booking", "id": "b", "title": "ثبت‌نام کلاس", "waitlist": True, "allow_cancel": True,
                        "slots": [{"id": "once", "label": "کارگاه ویژه", "capacity": 1}]},
                       {"type": "admin_notify", "id": "n", "on": "b", "text": "ثبت‌نام جدید"}]}
    with SessionLocal() as db:
        uid = db.query(User).filter(User.username == "cx_x.com").one().id
        bot = Bot(user_id=uid, name="کلاس")
        db.add(bot)
        db.flush()
        db.add(BotVersion(bot_id=bot.id, version=1, spec=spec, note=""))
        db.commit()
        bid = bot.id
    st = c.post(f"/api/bots/{bid}/publish", json={"mode": "shared"}, headers=H).json()
    url = f"/api/hook/shared/{bale.shared_hook_secret()}"
    c.post(url, json=msg(900, f"/admin {st['admin_code']}"))                      # the owner
    for chat, phone in ((901, "09120000001"), (902, "09120000002")):               # 901 gets the place, 902 waits
        c.post(url, json=msg(chat, f"/start {st['code']}"))
        for step in (cb(chat, "m:0"), cb(chat, "s:once"), msg(chat, "مشتری"), msg(chat, phone)):
            c.post(url, json=step)
    assert "لیست انتظار" in sent(calls, 902)[-2]["text"]
    # the menu now has the built-in «ثبت‌های من» button, with an ASCII callback
    c.post(url, json=msg(901, "/start"))
    last_menu = sent(calls, 901)[-1]["reply_markup"]["inline_keyboard"]
    assert last_menu[-1][0]["callback_data"] == "m:1" and "ثبت‌های من" in last_menu[-1][0]["text"]
    c.post(url, json=cb(901, "m:1"))
    listing = sent(calls, 901)[-1]
    rid = next(r["data"] for r in c.get(f"/api/bots/{bid}/records?sandbox=false", headers=H).json() if r["data"]["status"] == "confirmed") and 1
    assert listing["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == f"x:0:{rid}"
    calls.clear()
    c.post(url, json=cb(901, f"x:0:{rid}"))
    c.post(url, json=cb(901, "xy"))
    assert "لغو شد" in sent(calls, 901)[-2]["text"]
    promo = sent(calls, 902)                                                       # a DIFFERENT chat got a message
    assert len(promo) == 1 and "جای خالی شد" in promo[0]["text"]
    owner = " ".join(p["text"] for p in sent(calls, 900))
    assert "❌" in owner and "✅" in owner                                           # the owner heard about both
    live = {r["data"]["phone"]: r["data"]["status"] for r in c.get(f"/api/bots/{bid}/records?sandbox=false", headers=H).json()}
    assert live == {"09120000001": "cancelled", "09120000002": "confirmed"}
    assert not any("_cust" in r["data"] for r in c.get(f"/api/bots/{bid}/records?sandbox=false", headers=H).json())   # identity never reaches the owner UI
