"""Owner dashboard actions: cancel a booking/order, move an order along new -> preparing -> ready -> done."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import bale  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.engine import MemoryStore, handle, new_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Bot, BotVersion, Product, Record, User  # noqa: E402
from app.spec import BotSpec  # noqa: E402

SPEC = {"name": "t", "welcome": "سلام", "menu": [{"label": "ثبت‌نام", "block": "b"}, {"label": "خرید", "block": "shop"}],
        "blocks": [{"type": "booking", "id": "b", "title": "کارگاه", "waitlist": True, "allow_cancel": True,
                    "slots": [{"id": "once", "label": "کارگاه ویژه", "capacity": 1}]},
                   {"type": "catalog_order", "id": "shop", "title": "فروشگاه", "source": "table", "allow_cancel": True, "cancel_window_minutes": 30},
                   {"type": "admin_notify", "id": "n", "on": "b", "text": "ثبت‌نام جدید"}]}


@pytest.fixture()
def world(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "public_base_url", "https://example.test")
    monkeypatch.setattr(settings, "bale_shared_bot_token", "SHAREDTOKEN")
    sent = []

    def fake(token, method, payload=None, timeout=15):
        if method == "sendMessage":
            sent.append((str(payload["chat_id"]), payload["text"]))
        return {"username": "botyar_test_bot"} if method == "getMe" else True

    monkeypatch.setattr(bale, "api_call", fake)
    with TestClient(app) as c:
        tok = c.post("/api/auth/register", json={"email": "own@x.com", "password": "123456"}).json()["token"]
        H = {"Authorization": f"Bearer {tok}"}
        with SessionLocal() as db:
            uid = db.query(User).filter(User.email == "own@x.com").one().id
            bot = Bot(user_id=uid, name="t")
            db.add(bot)
            db.flush()
            db.add(BotVersion(bot_id=bot.id, version=1, spec=SPEC, note=""))
            db.add(Product(bot_id=bot.id, block_id="shop", name="کفش", category="", price=100000, stock=3, options=[], position=0))
            db.commit()
            bid = bot.id
        c.post(f"/api/bots/{bid}/publish", json={"mode": "shared"}, headers=H)

        def add(collection, data, sandbox=False):
            with SessionLocal() as db:
                r = Record(bot_id=bid, collection=collection, data=data, sandbox=sandbox)
                db.add(r)
                db.commit()
                return r.id

        yield c, H, bid, add, sent


def act(c, H, bid, rid, **body):
    return c.patch(f"/api/bots/{bid}/records/{rid}", json=body, headers=H)


def status_of(c, H, bid, rid, sandbox=False):
    return next(r["data"]["status"] for r in c.get(f"/api/bots/{bid}/records?sandbox={str(sandbox).lower()}", headers=H).json() if r["id"] == rid)


def test_owner_cancels_a_booking_the_waitlist_moves_and_both_customers_are_told(world):
    c, H, bid, add, sent = world
    a = add("b", {"name": "علی", "phone": "09120000001", "slot": "once", "slot_label": "کارگاه ویژه", "status": "confirmed", "_cust": "bale:111"})
    w = add("b", {"name": "رضا", "phone": "09120000002", "slot": "once", "slot_label": "کارگاه ویژه", "status": "waitlisted", "_cust": "bale:222"})
    r = act(c, H, bid, a, action="cancel", reason="کلاس لغو شد").json()
    assert r["status"] == "cancelled" and r["promoted"]["name"] == "رضا" and r["customer_messages"] == {"wanted": 2, "sent": 2, "sandbox": False}
    texts = dict(sent)
    assert "توسط مدیر لغو شد" in texts["111"] and "دلیل: کلاس لغو شد" in texts["111"]
    assert "جای خالی شد" in texts["222"]
    assert status_of(c, H, bid, w) == "confirmed"


def test_owner_cancelling_an_order_puts_stock_back_and_tells_the_customer(world):
    c, H, bid, add, sent = world
    with SessionLocal() as db:
        db.query(Product).filter(Product.bot_id == bid).one().stock = 1        # 2 of 3 are in this order
        db.commit()
        pid = db.query(Product).filter(Product.bot_id == bid).one().id
    o = add("shop", {"name": "مریم", "phone": "09123456789", "items": [{"id": pid, "name": "کفش", "price": 100000, "qty": 2, "options": {}}],
                     "total": 200000, "status": "new", "_cust": "bale:333"})
    r = act(c, H, bid, o, action="cancel")
    assert r.status_code == 200 and "سفارش شما توسط مدیر لغو شد" in dict(sent)["333"]
    with SessionLocal() as db:
        assert db.query(Product).filter(Product.bot_id == bid).one().stock == 3


def test_order_status_flow_messages_customer_on_progress_only(world):
    c, H, bid, add, sent = world
    o = add("shop", {"name": "مریم", "phone": "09123456789", "items": [], "total": 1, "status": "new", "_cust": "bale:333"})
    assert act(c, H, bid, o, action="status", status="preparing").json()["status"] == "preparing"
    assert "در حال آماده‌سازی" in sent[-1][1] and len(sent) == 1
    assert act(c, H, bid, o, action="status", status="ready").json()["status"] == "ready"
    assert "آماده است" in sent[-1][1] and len(sent) == 2
    act(c, H, bid, o, action="status", status="preparing")                      # a correction backwards: silent
    assert len(sent) == 2 and status_of(c, H, bid, o) == "preparing"
    assert act(c, H, bid, o, action="status", status="done").json()["status"] == "done"
    assert len(sent) == 2                                                       # closing an order sends nothing
    assert act(c, H, bid, o, action="status", status="ready").status_code == 409  # a closed order is frozen
    assert act(c, H, bid, o, action="cancel").status_code == 409                # …and cannot be cancelled any more


def test_invalid_actions_are_refused(world):
    c, H, bid, add, sent = world
    bk = add("b", {"name": "علی", "slot": "once", "status": "confirmed", "_cust": "bale:111"})
    o = add("shop", {"name": "م", "items": [], "total": 1, "status": "new"})
    assert act(c, H, bid, bk, action="status", status="preparing").status_code == 409     # bookings have no preparing status
    assert act(c, H, bid, o, action="status", status="shipped").status_code == 409
    assert act(c, H, bid, o, action="status").status_code == 409
    assert act(c, H, bid, bk, action="explode").status_code == 422
    act(c, H, bid, bk, action="cancel")
    assert act(c, H, bid, bk, action="cancel").status_code == 409                          # already cancelled
    assert act(c, H, bid, 999999, action="cancel").status_code == 404


def test_only_the_owner_can_act_on_a_record(world):
    c, H, bid, add, sent = world
    rid = add("b", {"name": "علی", "slot": "once", "status": "confirmed", "_cust": "bale:111"})
    other = c.post("/api/auth/register", json={"email": "evil@x.com", "password": "123456"}).json()["token"]
    O = {"Authorization": f"Bearer {other}"}
    assert act(c, O, bid, rid, action="cancel").status_code == 404
    assert c.patch(f"/api/bots/{bid}/records/{rid}", json={"action": "cancel"}).status_code == 401
    assert status_of(c, H, bid, rid) == "confirmed" and sent == []
    # a record id from ANOTHER bot cannot be reached through my bot's URL either
    with SessionLocal() as db:
        uid = db.query(User).filter(User.email == "evil@x.com").one().id
        b2 = Bot(user_id=uid, name="x")
        db.add(b2)
        db.flush()
        theirs = Record(bot_id=b2.id, collection="b", data={"status": "confirmed"}, sandbox=False)
        db.add(theirs)
        db.commit()
        theirs_id = theirs.id
    assert act(c, H, bid, theirs_id, action="cancel").status_code == 404


def test_sandbox_records_can_be_managed_but_no_chat_message_is_sent(world):
    c, H, bid, add, sent = world
    rid = add("shop", {"name": "م", "items": [], "total": 1, "status": "new", "_cust": "sim:abc"}, sandbox=True)
    r = act(c, H, bid, rid, action="status", status="preparing").json()
    assert r["status"] == "preparing" and r["customer_messages"]["sandbox"] is True and sent == []


def test_once_preparing_the_customer_can_no_longer_cancel_and_sees_the_status():
    """The reason this status exists: don't let someone cancel a coffee that is already being made."""
    spec = BotSpec.model_validate(SPEC)
    st = MemoryStore()
    st.load_catalog("shop", [{"name": "کفش", "category": "", "price": 100000, "stock": 5, "options": [], "description": ""}])
    s = new_session()
    s["cust"] = "bale:1"
    for m in ("/start", "m:1", "p:1", "n:1", "checkout", "مریم", "09123456789"):
        handle(spec, s, m, st)
    rec = st.rows["shop"][0]
    out = handle(spec, s, "/start")  if False else handle(spec, s, "m:2", st)
    assert any("لغو:" in b["text"] for a in out for b in a["buttons"])         # still cancellable while "new"
    st.update("shop", rec["id"], status="preparing")
    out = handle(spec, s, "/start", st)
    out = handle(spec, s, "m:2", st)
    text = "\n".join(a["text"] for a in out)
    assert "سفارش 1 — در حال آماده‌سازی" in text and not any("لغو:" in b["text"] for a in out for b in a["buttons"])
