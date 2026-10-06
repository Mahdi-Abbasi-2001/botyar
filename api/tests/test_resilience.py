"""Messenger outages: retries, health, the outbox, webhook refresh, friendly errors, isolated background jobs."""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from datetime import datetime, timedelta, timezone  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import bale, outbox, outreach, resilience, telegram, webhooks  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Bot, BotVersion, OutboxMessage, Publication, User, VersionTests  # noqa: E402

OK = lambda: httpx.Response(200, json={"ok": True, "result": {"id": 1}})  # noqa: E731


@pytest.fixture(autouse=True)
def _fresh_health():
    resilience.reset()
    yield
    resilience.reset()


def run(seq, name="bale"):
    """Run resilience.request against a scripted sequence of responses/exceptions; returns (result_or_error, calls, sleeps)."""
    calls, sleeps = [0], []

    def send():
        item = seq[min(calls[0], len(seq) - 1)]
        calls[0] += 1
        if isinstance(item, Exception):
            raise item
        return item() if callable(item) else item

    try:
        out = resilience.request(name, send, sleep=sleeps.append)
    except Exception as e:  # noqa: BLE001
        out = e
    return out, calls[0], sleeps


def test_success_and_a_clean_refusal_do_not_retry_and_mark_the_messenger_up():
    out, n, sl = run([OK()])
    assert out == {"id": 1} and n == 1 and sl == [] and resilience.health("bale")["status"] == "ok"
    out, n, sl = run([httpx.Response(400, json={"ok": False, "description": "Bad Request: chat not found"})])
    assert type(out) is resilience.BaleError and "chat not found" in str(out) and n == 1 and resilience.health("bale")["status"] == "ok"   # a "no" is not an outage
    out, n, _ = run([httpx.Response(403, json={"ok": False, "description": "Forbidden: bot was blocked by the user"})])
    assert type(out) is resilience.BaleError and n == 1


def test_connection_failures_are_retried_with_backoff_and_then_reported_as_transient():
    out, n, sl = run([httpx.ConnectError("down"), httpx.ConnectError("down"), OK()])
    assert out == {"id": 1} and n == 3 and sl == [0.5, 1.5]
    out, n, sl = run([httpx.ConnectError("down")])
    assert isinstance(out, resilience.TransientError) and n == 3 and sl == [0.5, 1.5]
    out, n, _ = run([httpx.ConnectTimeout("slow")])
    assert isinstance(out, resilience.TransientError) and n == 3


def test_rate_limits_wait_the_servers_time_capped_without_double_waiting():
    out, n, sl = run([httpx.Response(429, json={"ok": False, "parameters": {"retry_after": 2}}), OK()])
    assert out == {"id": 1} and n == 2 and sl == [2.0]
    out, n, sl = run([httpx.Response(429, json={"ok": False, "parameters": {"retry_after": 99}}), OK()])
    assert sl == [resilience.MAX_RETRY_AFTER]
    out, n, sl = run([httpx.Response(429, headers={"retry-after": "1"}, json={"ok": False})])
    assert isinstance(out, resilience.TransientError) and n == 3


def test_gateway_errors_are_retried_but_a_read_timeout_never_is():
    out, n, _ = run([httpx.Response(502, text="bad gateway"), httpx.Response(503, text="x"), OK()])
    assert out == {"id": 1} and n == 3
    out, n, _ = run([httpx.Response(504, text="x")])
    assert isinstance(out, resilience.TransientError) and n == 3
    out, n, sl = run([httpx.ReadTimeout("slow")])                     # the message may have been delivered: resending would duplicate it
    assert isinstance(out, resilience.UncertainError) and n == 1 and sl == []
    out, n, _ = run([httpx.RemoteProtocolError("reset")])
    assert isinstance(out, resilience.UncertainError) and n == 1
    out, n, _ = run([httpx.Response(200, text="not json")])
    assert type(out) is resilience.BaleError


def test_health_goes_degraded_then_down_and_recovers_on_the_first_success():
    for i in range(2):
        run([httpx.ConnectError("x")])
    assert resilience.health("bale")["status"] == "degraded"
    run([httpx.ConnectError("x")])
    h = resilience.health("bale")
    assert h["status"] == "down" and h["failures"] == 3 and "cannot connect" in h["error"] and h["last_fail"]
    run([OK()])
    assert resilience.health("bale")["status"] == "ok" and resilience.health("bale")["failures"] == 0
    assert resilience.health("tg")["status"] == "unknown"             # a messenger that was never used
    run([httpx.ConnectError("x")], name="tg")
    assert resilience.health("bale")["status"] == "ok"                # messengers are tracked separately


def test_the_real_api_calls_use_the_wrapper_for_bale_and_the_telegram_relay(monkeypatch):
    seen = []
    monkeypatch.setattr(httpx, "post", lambda url, **kw: (seen.append(url), OK())[1])
    monkeypatch.setattr(settings, "telegram_relay_url", "https://relay.example")
    monkeypatch.setattr(settings, "telegram_relay_key", "k")
    assert bale.api_call("TOK", "getMe") == {"id": 1} and telegram.api_call("TGTOK", "getMe") == {"id": 1}
    assert seen == ["https://tapi.bale.ai/botTOK/getMe", "https://relay.example/botTGTOK/getMe"]
    assert resilience.health("bale")["status"] == "ok" and resilience.health("tg")["status"] == "ok"
    monkeypatch.setattr(httpx, "post", lambda url, **kw: (_ for _ in ()).throw(httpx.ConnectError("relay down")))
    with pytest.raises(resilience.TransientError):
        telegram.api_call("TGTOK", "sendMessage", {"chat_id": 1, "text": "x"})
    assert resilience.health("tg")["failures"] == 1
    monkeypatch.setattr(settings, "telegram_relay_url", "")
    with pytest.raises(bale.BaleError):
        telegram.api_call("TGTOK", "getMe")


# ---------------- outbox ----------------
class FakeCh:
    name = "bale"

    def __init__(self, exc=None):
        self.exc, self.calls = exc, []

    def call(self, token, method, payload=None, timeout=15):
        self.calls.append((method, payload))
        if self.exc:
            raise self.exc
        return True


@pytest.fixture()
def db_world(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(settings, "public_base_url", "https://example.test")
    monkeypatch.setattr(settings, "bale_shared_bot_token", "SHAREDTOKEN")
    state = {"down": False, "calls": [], "fail_for": set()}

    def fake(token, method, payload=None, timeout=15):
        state["calls"].append((method, dict(payload or {})))
        if state["down"] and method == "sendMessage":
            raise resilience.TransientError("cannot connect")
        if method == "sendMessage" and str((payload or {}).get("chat_id")) in state["fail_for"]:
            raise resilience.BaleError("Forbidden: bot was blocked by the user")
        return {"username": "botyar_test_bot", "id": 9} if method == "getMe" else True

    monkeypatch.setattr(bale, "api_call", fake)
    with TestClient(app) as c:
        tok = c.post("/api/auth/register", json={"username": "r_x.com", "password": "123456"}).json()["token"]
        H = {"Authorization": f"Bearer {tok}"}
        spec = {"name": "کافه", "welcome": "سلام", "menu": [{"label": "درباره", "block": "a"}], "blocks": [{"type": "message", "id": "a", "text": "ما کافه‌ایم"}]}
        with SessionLocal() as db:
            uid = db.query(User).filter(User.username == "r_x.com").one().id
            bot = Bot(user_id=uid, name="کافه")
            db.add(bot); db.flush()
            db.add(BotVersion(bot_id=bot.id, version=1, spec=spec, note=""))
            db.add(VersionTests(bot_id=bot.id, version=1, scenarios=[], results=[{"name": "t", "passed": True, "failures": [], "transcript": []}]))
            db.commit()
            bid = bot.id
        pub = c.post(f"/api/bots/{bid}/publish", json={"mode": "shared"}, headers=H).json()
        yield c, H, bid, pub, state


def rows():
    with SessionLocal() as db:
        return [(r.chat_id, r.status, r.attempts, r.payload.get("text")) for r in db.query(OutboxMessage).order_by(OutboxMessage.id)]


def test_outbox_send_queues_only_unreachable_plain_messages_and_never_stores_a_token(db_world):
    ch = FakeCh(resilience.TransientError("cannot connect"))
    assert outbox.send(FakeCh(), "T", "sendMessage", {"chat_id": "5", "text": "hi"}, 1) is True
    assert outbox.send(ch, "SECRET-TOKEN", "sendMessage", {"chat_id": "5", "text": "hi"}, 1) is False
    assert rows() == [("5", "pending", 0, "hi")]
    with SessionLocal() as db:
        assert "SECRET-TOKEN" not in str(db.query(OutboxMessage).one().payload) and db.query(OutboxMessage).one().last_error == "cannot connect"
    with pytest.raises(resilience.TransientError):
        outbox.send(ch, "T", "sendPhoto", {"chat_id": "5"}, 1)                    # files are tied to a moment that has passed
    with pytest.raises(resilience.TransientError):
        outbox.send(ch, "T", "sendMessage", {"chat_id": "5", "text": "x"}, None)  # no bot to retry it for
    for exc in (resilience.UncertainError("timed out"), resilience.BaleError("Forbidden: bot was blocked")):
        with pytest.raises(type(exc)):
            outbox.send(FakeCh(exc), "T", "sendMessage", {"chat_id": "5", "text": "x"}, 1)   # may be delivered / will never work: no queue
    assert len(rows()) == 1


def test_the_queue_has_a_cap_per_bot(db_world, monkeypatch):
    monkeypatch.setattr(outbox, "PENDING_CAP", 2)
    ch = FakeCh(resilience.TransientError("x"))
    assert [outbox.send(ch, "T", "sendMessage", {"chat_id": str(i), "text": "m"}, 1) is False for i in range(2)] == [True, True]
    with pytest.raises(resilience.TransientError):
        outbox.send(ch, "T", "sendMessage", {"chat_id": "9", "text": "m"}, 1)


def test_customer_reply_during_an_outage_is_queued_and_delivered_when_the_messenger_is_back(db_world):
    c, H, bid, pub, state = db_world
    n = [90000]

    def msg(chat, text):
        n[0] += 1
        return c.post(f"/api/hook/shared/{bale.shared_hook_secret()}", json={"update_id": n[0], "message": {
            "message_id": 1, "from": {"id": chat, "first_name": "سارا"}, "chat": {"id": chat, "type": "private"}, "text": text}})

    state["down"] = True
    assert msg(31, f"/start {pub['code']}").status_code == 200                       # the webhook still answers 200: nothing is lost
    pending = rows()
    assert pending and all(r[1] == "pending" and r[0] == "31" for r in pending)
    texts = [r[3] for r in pending]
    state["down"] = False
    state["calls"].clear()
    with SessionLocal() as db:
        res = outbox.process(db, datetime.now(timezone.utc) + timedelta(minutes=2))
    assert res["sent"] == len(pending) and [p["text"] for m, p in state["calls"] if m == "sendMessage"] == texts   # same order
    assert all(r[1] == "sent" for r in rows())
    with SessionLocal() as db:
        assert outbox.process(db, datetime.now(timezone.utc) + timedelta(minutes=5)) == {"sent": 0, "failed": 0, "retry": 0}   # nothing is sent twice


def test_retry_schedule_order_per_chat_and_give_up(db_world):
    c, H, bid, pub, state = db_world
    ch = FakeCh(resilience.TransientError("cannot connect"))
    for chat, text in (("1", "a1"), ("1", "a2"), ("2", "b1")):
        outbox.send(ch, "T", "sendMessage", {"chat_id": chat, "text": text}, bid)
    state["down"] = True
    t0 = datetime.now(timezone.utc)
    with SessionLocal() as db:
        res = outbox.process(db, t0 + timedelta(minutes=2))
    assert res == {"sent": 0, "failed": 0, "retry": 1}                              # one probe only: the messenger is still down, the rest waits
    assert [(r[0], r[2]) for r in rows()] == [("1", 1), ("1", 0), ("2", 0)]
    t = t0 + timedelta(minutes=2)
    for _ in range(outbox.MAX_ATTEMPTS):
        t += timedelta(minutes=20)
        with SessionLocal() as db:
            outbox.process(db, t)
    st = {(r[0], r[3]): r[1] for r in rows()}
    assert st[("1", "a1")] == "failed"                                              # gave up after the attempts / 30 minutes
    state["down"] = False
    with SessionLocal() as db:
        outbox.process(db, t + timedelta(minutes=20))
    assert {(r[0], r[3]): r[1] for r in rows()}[("2", "b1")] in ("sent", "failed")


def test_permanent_errors_and_unpublished_bots_fail_at_once_and_old_entries_are_purged(db_world):
    c, H, bid, pub, state = db_world
    ch = FakeCh(resilience.TransientError("x"))
    outbox.send(ch, "T", "sendMessage", {"chat_id": "77", "text": "to a blocker"}, bid)
    state["fail_for"].add("77")
    with SessionLocal() as db:
        assert outbox.process(db, datetime.now(timezone.utc) + timedelta(minutes=2))["failed"] == 1
    assert rows()[0][1] == "failed"
    outbox.send(ch, "T", "sendMessage", {"chat_id": "78", "text": "after unpublish"}, bid)
    c.post(f"/api/bots/{bid}/unpublish", headers=H)
    with SessionLocal() as db:
        assert outbox.process(db, datetime.now(timezone.utc) + timedelta(minutes=2))["failed"] == 1
        assert outbox.purge(db, datetime.now(timezone.utc) + timedelta(days=4)) == 2
    assert rows() == []


def test_broadcast_and_owner_notifications_use_the_outbox(db_world, monkeypatch):
    c, H, bid, pub, state = db_world
    monkeypatch.setattr(outreach, "PACE_SECONDS", 0)
    n = [91000]

    def msg(chat, text):
        n[0] += 1
        c.post(f"/api/hook/shared/{bale.shared_hook_secret()}", json={"update_id": n[0], "message": {
            "message_id": 1, "from": {"id": chat, "first_name": "x"}, "chat": {"id": chat, "type": "private"}, "text": text}})

    msg(41, f"/start {pub['code']}"); msg(42, f"/start {pub['code']}")
    state["down"] = True
    import time

    r = c.post(f"/api/bots/{bid}/broadcasts", json={"text": "اطلاعیه"}, headers=H)
    assert r.status_code == 200
    time.sleep(0.5)
    assert sorted(x[0] for x in rows() if x[3].startswith("اطلاعیه")) == ["41", "42"]
    st = c.get(f"/api/bots/{bid}/delivery", headers=H).json()
    assert st["outbox"]["pending"] == 2 and st["messengers"][0]["messenger"] == "bale"


def test_delivery_status_endpoint_shape_and_authorisation(db_world):
    c, H, bid, pub, state = db_world
    for _ in range(3):
        resilience.record("bale", False, "cannot connect")
    st = c.get(f"/api/bots/{bid}/delivery", headers=H).json()
    assert st["messengers"][0]["status"] == "down" and st["outbox"] == {"pending": 0, "sent_24h": 0, "failed_24h": 0}
    other = {"Authorization": "Bearer " + c.post("/api/auth/register", json={"username": "z_x.com", "password": "123456"}).json()["token"]}
    assert c.get(f"/api/bots/{bid}/delivery", headers=other).status_code == 404
    c.post(f"/api/bots/{bid}/unpublish", headers=H)
    assert c.get(f"/api/bots/{bid}/delivery", headers=H).json()["messengers"] == []


def test_an_outage_while_publishing_is_never_reported_as_a_wrong_token(db_world, monkeypatch):
    c, H, bid, pub, state = db_world

    def down(token, method, payload=None, timeout=15):
        raise resilience.TransientError("cannot connect")

    monkeypatch.setattr(bale, "api_call", down)
    r = c.post(f"/api/bots/{bid}/publish", json={"mode": "own", "token": "123:abc"}, headers=H)
    assert r.status_code == 503 and "در دسترس نیست" in r.json()["detail"] and "توکن معتبر نیست" not in r.json()["detail"]

    def bad_token(token, method, payload=None, timeout=15):
        raise resilience.BaleError("Unauthorized")

    monkeypatch.setattr(bale, "api_call", bad_token)
    r = c.post(f"/api/bots/{bid}/publish", json={"mode": "own", "token": "123:abc"}, headers=H)
    assert r.status_code == 400 and "توکن معتبر نیست" in r.json()["detail"]


def test_webhook_refresh_reregisters_shared_and_own_bots_and_survives_failures(db_world, monkeypatch):
    c, H, bid, pub, state = db_world
    monkeypatch.setattr(settings, "telegram_relay_url", "https://relay.example")
    monkeypatch.setattr(settings, "telegram_relay_key", "k")
    monkeypatch.setattr(settings, "telegram_shared_bot_token", "123:TG")
    with SessionLocal() as db:
        db.add(Publication(bot_id=bid + 100, mode="own", version=1, code="OWNCOD", admin_code="OWNADMIN", token_enc=bale.encrypt("OWNTOKEN"), hook_secret="s" * 8))
        db.commit()
    tg_calls = []
    state["calls"].clear()
    monkeypatch.setattr(telegram, "api_call", lambda token, method, payload=None, timeout=15: tg_calls.append((token, method, payload)) or True)
    with SessionLocal() as db:
        res = webhooks.refresh(db)
    urls = [p["url"] for m, p in state["calls"] if m == "setWebhook"]
    assert res == {"ok": 3, "failed": 0}
    assert any("/api/hook/shared/" in u for u in urls) and any("/api/hook/own/" in u for u in urls)
    assert tg_calls[0][1] == "setWebhook" and "channel_post" in tg_calls[0][2]["allowed_updates"] and tg_calls[0][2]["url"].startswith("https://relay.example/hook/shared/")

    def boom(token, method, payload=None, timeout=15):
        raise resilience.TransientError("cannot connect")

    monkeypatch.setattr(bale, "api_call", boom)
    with SessionLocal() as db:
        assert webhooks.refresh(db)["failed"] >= 2                                    # failures are counted, never raised
    monkeypatch.setattr(settings, "public_base_url", "")
    with SessionLocal() as db:
        assert webhooks.refresh(db) == {"ok": 0, "failed": 0}                         # local dev: nothing to register


def test_one_failing_background_job_does_not_stop_the_others(monkeypatch):
    ran = []
    monkeypatch.setattr(outreach, "due_reminders", lambda db, now: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(outbox, "process", lambda db, now: ran.append("outbox"))
    monkeypatch.setattr(webhooks, "refresh", lambda db: ran.append("webhooks"))
    monkeypatch.setattr(outbox, "purge", lambda db, now: ran.append("purge"))
    outreach._jobs(1440 * 15)       # a tick on which every periodic job is due
    assert ran == ["outbox", "webhooks", "purge"]
