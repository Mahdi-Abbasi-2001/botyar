"""Online payment: invoice only when a wallet is configured, pre-checkout validation, idempotent success, expiry, safety of the test button."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from datetime import timedelta  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import bale, engine as eng, outreach  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.dates import now_tehran  # noqa: E402
from app.engine import MemoryStore, handle, new_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Bot, BotVersion, Record, User  # noqa: E402
from app.spec import BotSpec  # noqa: E402

SPEC = {"name": "کافه", "welcome": "سلام", "menu": [{"label": "سفارش", "block": "o"}],
        "blocks": [{"type": "catalog_order", "id": "o", "title": "منو", "payment": "online", "delivery_fee": 20000, "allow_cancel": True,
                    "items": [{"id": "latte", "name": "لاته", "price": 100000}],
                    "fields": [{"key": "name", "label": "نام شما؟", "kind": "text"}]},
                   {"type": "admin_notify", "id": "n", "on": "o", "text": "سفارش جدید"}]}
SP = BotSpec.model_validate(SPEC)


def kinds(out):
    return [a["type"] for a in out]


def order(sess, store, *steps):
    out = None
    for t in ["/start", "m:0", "i:latte", "n:2", "checkout", *steps]:
        out = handle(SP, sess, t, store)
    return out


def test_without_a_wallet_the_order_is_a_normal_one_and_says_so():
    s, st = new_session(), MemoryStore()
    s["cust"] = "bale:1"
    out = order(s, st, "سارا")
    assert st.find("o")[0]["status"] == "new" and "invoice" not in kinds(out)
    assert "هنوز برای این ربات فعال نشده" in out[0]["text"] and "notify_admin" in kinds(out)


def test_with_a_wallet_an_invoice_is_issued_and_the_owner_is_told_only_after_payment():
    s, st = new_session(), MemoryStore()
    s["cust"], s["pay_ok"] = "bale:1", True
    out = order(s, st, "سارا")
    row = st.find("o")[0]
    inv = [a for a in out if a["type"] == "invoice"][0]
    assert row["status"] == "awaiting_payment" and row["total"] == 120000 and inv["amount"] == 120000 and inv["rid"] == row["id"]
    assert "notify_admin" not in kinds(out)
    paid = eng.mark_paid(SP, st, now_tehran(), SP.blocks[0], row, "ch1")
    assert "notify_admin" in kinds(paid) and "پرداخت‌شده" in [a for a in paid if a["type"] == "notify_admin"][0]["text"]
    row = st.find("o")[0]
    assert row["status"] == "new" and row["paid"] is True and row["_charge"] == "ch1"
    assert eng.mark_paid(SP, st, now_tehran(), SP.blocks[0], row) == []          # a repeated delivery changes nothing


def test_the_fake_pay_button_works_only_in_the_simulator_and_only_for_the_owner_of_the_order():
    st = MemoryStore()
    s = new_session(); s["cust"], s["pay_ok"], s["pay_sim"] = "sim:1", True, True
    out = order(s, st, "سارا")
    rid = st.find("o")[0]["id"]
    assert f"pay:{rid}" in [b["data"] for a in out for b in a.get("buttons", [])] and "invoice" not in kinds(out)
    other = new_session(); other["cust"], other["pay_sim"] = "sim:2", True
    handle(SP, other, f"pay:{rid}", st)
    assert st.find("o")[0]["status"] == "awaiting_payment"                        # somebody else's order
    real = new_session(); real["cust"] = "bale:9"                                 # a real chat: pay_sim is absent
    handle(SP, real, f"pay:{rid}", st)
    assert st.find("o")[0]["status"] == "awaiting_payment"
    out = handle(SP, s, f"pay:{rid}", st)
    assert st.find("o")[0]["status"] == "new" and "پرداخت انجام شد" in out[0]["text"]


def test_paid_orders_cannot_be_cancelled_by_the_customer_and_unpaid_ones_expire_with_stock_back():
    st = MemoryStore()
    s = new_session(); s["cust"], s["pay_ok"], s["pay_sim"] = "bale:1", True, True
    order(s, st, "سارا")
    rid = st.find("o")[0]["id"]
    now = now_tehran()
    assert eng.expire_unpaid(SP, st, now) == []                                   # still inside the window
    actions = eng.expire_unpaid(SP, st, now + timedelta(minutes=eng.PAY_WINDOW_MINUTES + 1))
    assert st.find("o")[0]["status"] == "cancelled" and actions and actions[0]["cust"] == "bale:1"
    # paid order: customer cancel refused
    s2 = new_session(); s2["cust"], s2["pay_ok"], s2["pay_sim"] = "bale:2", True, True
    order(s2, st, "علی")
    rid2 = st.find("o")[1]["id"]
    handle(SP, s2, f"pay:{rid2}", st)
    out = handle(SP, s2, "/start", st)
    out = handle(SP, s2, "m:1", st)
    out = handle(SP, s2, f"x:0:{rid2}", st)
    assert "پرداخت شده" in "\n".join(a["text"] for a in out)


# ---- Bale integration ----
@pytest.fixture()
def world(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    bale._seen.clear()
    monkeypatch.setattr(settings, "public_base_url", "https://example.test")
    monkeypatch.setattr(settings, "bale_shared_bot_token", "SHAREDTOKEN")
    calls = []

    def fake(token, method, payload=None, timeout=15):
        calls.append((method, payload))
        return {"username": "botyar_test_bot"} if method == "getMe" else True

    monkeypatch.setattr(bale, "api_call", fake)
    with TestClient(app) as c:
        tok = c.post("/api/auth/register", json={"username": "p_x.com", "password": "123456"}).json()["token"]
        H = {"Authorization": f"Bearer {tok}"}
        with SessionLocal() as db:
            uid = db.query(User).filter(User.username == "p_x.com").one().id
            bot = Bot(user_id=uid, name="کافه")
            db.add(bot)
            db.flush()
            db.add(BotVersion(bot_id=bot.id, version=1, spec=SPEC, note=""))
            db.commit()
            bid = bot.id
        pub = c.post(f"/api/bots/{bid}/publish", json={"mode": "shared"}, headers=H).json()
        yield c, H, bid, pub, calls


def drive(c, pub, chat=801):
    n = [20000]

    def post(update):
        n[0] += 1
        update["update_id"] = n[0]
        return c.post(f"/api/hook/shared/{bale.shared_hook_secret()}", json=update)

    def msg(text, **extra):
        return post({"message": {"message_id": 1, "from": {"id": chat, "first_name": "x"}, "chat": {"id": chat, "type": "private"}, "text": text, **extra}})

    def tap(data):
        return post({"callback_query": {"id": "q", "from": {"id": chat}, "data": data, "message": {"message_id": 7, "chat": {"id": chat, "type": "private"}}}})

    return post, msg, tap


def test_shared_bot_accepts_only_the_test_wallet_and_the_full_payment_flow_works(world):
    c, H, bid, pub, calls = world
    post, msg, tap = drive(c, pub)
    msg(f"/start {pub['code']}")
    assert c.put(f"/api/bots/{bid}/payment", json={"wallet_token": "REAL-WALLET-TOKEN-123"}, headers=H).json()["active"] is False
    calls.clear()
    tap("m:0"); tap("i:latte"); tap("n:1"); tap("checkout"); msg("سارا")
    assert not [m for m, _ in calls if m == "sendInvoice"]                              # a real token on the shared bot is ignored
    with SessionLocal() as db:
        assert db.query(Record).filter(Record.sandbox.is_(False)).one().data["status"] == "new"
        db.query(Record).delete()
        db.commit()

    st = c.put(f"/api/bots/{bid}/payment", json={"wallet_token": "WALLET-TEST-1111111111111111"}, headers=H).json()
    assert st["active"] is True and st["test"] is True and "wallet" not in str(st).lower().replace("configured", "")
    calls.clear()
    tap("m:0"); tap("i:latte"); tap("n:1"); tap("checkout"); msg("سارا")
    inv = [p for m, p in calls if m == "sendInvoice"]
    assert len(inv) == 1 and inv[0]["provider_token"] == "WALLET-TEST-1111111111111111" and inv[0]["prices"][0]["amount"] == 1200000   # 120,000 toman in rials
    rid = int(inv[0]["payload"][2:])

    calls.clear()
    post({"pre_checkout_query": {"id": "pc1", "from": {"id": 801}, "currency": "IRR", "total_amount": 1200000, "invoice_payload": f"o:{rid}"}})
    assert calls[-1][1]["ok"] is True
    post({"pre_checkout_query": {"id": "pc2", "from": {"id": 999}, "currency": "IRR", "total_amount": 1200000, "invoice_payload": f"o:{rid}"}})
    assert calls[-1][1]["ok"] is False                                                   # another person's order
    post({"pre_checkout_query": {"id": "pc3", "from": {"id": 801}, "currency": "IRR", "total_amount": 100, "invoice_payload": f"o:{rid}"}})
    assert calls[-1][1]["ok"] is False                                                   # wrong amount
    post({"pre_checkout_query": {"id": "pc4", "from": {"id": 801}, "currency": "IRR", "total_amount": 1, "invoice_payload": "o:99999"}})
    assert calls[-1][1]["ok"] is False and calls[-1][1]["error_message"]

    calls.clear()
    sp = {"currency": "IRR", "total_amount": 1200000, "invoice_payload": f"o:{rid}", "provider_payment_charge_id": "CHG1"}
    msg("", successful_payment=sp)
    with SessionLocal() as db:
        d = db.get(Record, rid).data
        assert d["status"] == "new" and d["paid"] is True and d["_charge"] == "CHG1"
    texts = [p.get("text", "") for m, p in calls if m == "sendMessage"]
    assert any("پرداخت انجام شد" in t for t in texts)
    n_before = len(calls)
    msg("", successful_payment=sp)                                                       # Bale redelivers: nothing happens twice
    assert not [1 for m, p in calls[n_before:] if "پرداخت انجام شد" in p.get("text", "")]


def test_successful_payment_with_a_wrong_amount_or_stranger_is_ignored(world):
    c, H, bid, pub, calls = world
    post, msg, tap = drive(c, pub)
    msg(f"/start {pub['code']}")
    c.put(f"/api/bots/{bid}/payment", json={"wallet_token": "WALLET-TEST-1111111111111111"}, headers=H)
    tap("m:0"); tap("i:latte"); tap("n:1"); tap("checkout"); msg("سارا")
    with SessionLocal() as db:
        rid = db.query(Record).one().id
    post({"message": {"message_id": 1, "from": {"id": 801}, "chat": {"id": 801, "type": "private"}, "successful_payment": {"currency": "IRR", "total_amount": 5, "invoice_payload": f"o:{rid}"}}})
    post({"message": {"message_id": 1, "from": {"id": 777}, "chat": {"id": 777, "type": "private"}, "successful_payment": {"currency": "IRR", "total_amount": 1200000, "invoice_payload": f"o:{rid}"}}})
    with SessionLocal() as db:
        assert db.get(Record, rid).data["status"] == "awaiting_payment"


def test_unpaid_orders_expire_in_the_background_job_and_owner_cannot_move_them_forward(world):
    c, H, bid, pub, calls = world
    post, msg, tap = drive(c, pub)
    msg(f"/start {pub['code']}")
    c.put(f"/api/bots/{bid}/payment", json={"wallet_token": "WALLET-TEST-1111111111111111"}, headers=H)
    tap("m:0"); tap("i:latte"); tap("n:1"); tap("checkout"); msg("سارا")
    with SessionLocal() as db:
        rid = db.query(Record).one().id
    assert c.patch(f"/api/bots/{bid}/records/{rid}", json={"action": "status", "status": "preparing"}, headers=H).status_code == 409
    calls.clear()
    with SessionLocal() as db:
        assert outreach.expire_unpaid_orders(db, now_tehran()) == 0
        assert outreach.expire_unpaid_orders(db, now_tehran() + timedelta(minutes=eng.PAY_WINDOW_MINUTES + 1)) == 1
    with SessionLocal() as db:
        assert db.get(Record, rid).data["status"] == "cancelled"
    assert any("مهلت پرداخت" in p.get("text", "") for m, p in calls if m == "sendMessage")


def test_payment_endpoints_are_private(world):
    c, H, bid, pub, calls = world
    tok2 = c.post("/api/auth/register", json={"username": "q_x.com", "password": "123456"}).json()["token"]
    H2 = {"Authorization": f"Bearer {tok2}"}
    assert c.get(f"/api/bots/{bid}/payment", headers=H2).status_code == 404
    assert c.put(f"/api/bots/{bid}/payment", json={"wallet_token": "WALLET-TEST-1111111111111111"}, headers=H2).status_code == 404
    assert c.delete(f"/api/bots/{bid}/payment", headers=H2).status_code == 404
    assert c.put(f"/api/bots/{bid}/payment", json={"wallet_token": "has space token"}, headers=H).status_code == 422
