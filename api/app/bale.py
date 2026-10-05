"""Messenger adapter (Bale, and Telegram via app.telegram): thin HTTP client + the glue that feeds updates to the deterministic engine.

Facts from docs.bale.ai (verified 2026-10-04): Telegram-style Bot API at tapi.bale.ai; no webhook secret
(so our webhook URLs carry an unguessable secret); callback_data max 64 bytes; answerCallbackQuery is
mandatory after a button press; webhook ports 443/88; /start parameters are not documented."""
from __future__ import annotations

import copy

import base64
from dataclasses import dataclass
from typing import Callable
import hashlib
import hmac
import logging
import re
import secrets
import threading
from collections import defaultdict

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import anon, billing, communities, dates, engine, faq_index, gate, media, referral
from .config import settings
from .db import SessionLocal
from .models import Bot, BotListing, BotVersion, ChatLink, BannedCustomer, ChatSession, CustomerSeen, PaymentConfig, Publication, Record
from .spec import BotSpec
from .store import SqlStore

log = logging.getLogger("botyar.bale")
API = "https://tapi.bale.ai"
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O/1/I confusion


class BaleError(Exception):
    pass


def api_call(token: str, method: str, payload: dict | None = None, timeout: float = 15):
    r = httpx.post(f"{API}/bot{token}/{method}", json=payload or {}, timeout=timeout)
    try:
        d = r.json()
    except Exception:
        raise BaleError(f"HTTP {r.status_code}")
    if not d.get("ok"):
        raise BaleError(d.get("description") or f"HTTP {r.status_code}")
    return d.get("result")


# ---------- channels ----------
@dataclass(frozen=True)
class Channel:
    """A Telegram-style messenger. Bale and Telegram share one Bot API shape, so everything below serves both;
    a customer's key ("bale:123", "tg:123") says which messenger to answer them on."""
    name: str                          # customer-key prefix and webhook namespace
    call: Callable                     # (token, method, payload=None, timeout=15) -> result
    pub_model: type                    # Publication | TgPublication
    link_model: type                   # ChatLink | TgChatLink (shared bot: chat -> published bot)
    shared_token: Callable[[], str]
    payments: bool                     # Bale wallet invoices; Telegram has no payment provider that serves Iran


# a lambda, not api_call itself: tests replace bale.api_call and the channel must follow
BALE = Channel("bale", lambda *a, **k: api_call(*a, **k), Publication, ChatLink, lambda: settings.bale_shared_bot_token, True)
CHANNELS: dict[str, Channel] = {"bale": BALE}  # telegram.py adds itself


def pub_token(ch: Channel, pub) -> str:
    return ch.shared_token() if pub.mode == "shared" else decrypt(pub.token_enc)


# ---------- secrets ----------
def _fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(settings.jwt_secret.encode()).digest()))


def encrypt(s: str) -> str:
    return _fernet().encrypt(s.encode()).decode()


def decrypt(s: str) -> str:
    try:
        return _fernet().decrypt(s.encode()).decode()
    except InvalidToken:
        raise BaleError("token cannot be decrypted (JWT_SECRET changed?)")


def new_code(n: int) -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(n))


def shared_hook_secret() -> str:
    return hmac.new(settings.jwt_secret.encode(), b"bale-shared-hook", hashlib.sha256).hexdigest()[:32]


_username_cache: dict[str, str] = {}


def shared_username() -> str:
    t = settings.bale_shared_bot_token
    if not t:
        return ""
    if t not in _username_cache:
        try:
            _username_cache[t] = api_call(t, "getMe").get("username", "")
        except Exception as e:  # noqa: BLE001
            log.warning("getMe failed: %s", e)
            return ""
    return _username_cache[t]


def ensure_shared_webhook():
    """Register the shared bot's webhook. Only when PUBLIC_BASE_URL is set (production), never from local dev."""
    if not (settings.bale_shared_bot_token and settings.public_base_url):
        return
    url = f"{settings.public_base_url.rstrip('/')}/api/hook/shared/{shared_hook_secret()}"
    try:
        api_call(settings.bale_shared_bot_token, "setWebhook", {"url": url})
        log.info("shared webhook registered")
    except Exception as e:  # noqa: BLE001
        log.warning("setWebhook failed: %s", e)


# ---------- sending ----------
def to_markup(buttons: list[dict], cb: dict) -> dict:
    """One button per row. callback_data over 64 bytes (long Persian labels) is replaced by a short token."""
    rows = []
    for b in buttons:
        data = b["data"]
        if data.startswith("url:"):  # a link button (e.g. "join our channel")
            rows.append([{"text": engine.fa_digits(b["text"]), "url": data[4:]}])
            continue
        if len(data.encode()) > 64:
            key = f"~{len(cb)}"
            cb[key] = data
            data = key
        rows.append([{"text": engine.fa_digits(b["text"]), "callback_data": data}])
    return {"inline_keyboard": rows}


def api_upload(token: str, method: str, fields: dict, file_field: str, filename: str, data: bytes, mime: str, timeout: float = 60):
    """Multipart upload of a photo/document (Bale accepts multipart/form-data; JSON cannot carry file bytes)."""
    r = httpx.post(f"{API}/bot{token}/{method}", data={k: str(v) for k, v in fields.items()},
                   files={file_field: (filename, data, mime)}, timeout=timeout)
    try:
        d = r.json()
    except Exception:
        raise BaleError(f"HTTP {r.status_code}")
    if not d.get("ok"):
        raise BaleError(d.get("description") or f"HTTP {r.status_code}")
    return d.get("result")


def deliver(token: str, chat_id: str, actions: list[dict], session: dict, admin_chat_id: str = "", edit_message_id: int | None = None,
            wallet: str = "", ch: Channel = BALE, others: list[dict] | None = None, files=None) -> list[int]:
    """Send the actions. Returns the record ids whose invoice could not be sent.
    Messages for customers on the OTHER messenger are appended to `others` for send_customer_actions."""
    cb: dict = {}
    failed_invoices: list[int] = []
    mine = f"{ch.name}:"
    for n, a in enumerate(actions):
        try:
            if a["type"] == "send" and n == 0 and a.get("edit") and edit_message_id:
                # in-place navigation (e.g. next page): edit the clicked message; fall back to a new message if refused
                payload = {"chat_id": chat_id, "message_id": edit_message_id, "text": engine.fa_digits(a["text"])[:4096] or "…"}
                if a.get("buttons"):
                    payload["reply_markup"] = to_markup(a["buttons"], cb)
                try:
                    ch.call(token, "editMessageText", payload)
                    continue
                except Exception as e:  # noqa: BLE001
                    log.warning("edit failed, sending a new message: %s", e)
                    payload.pop("message_id")
                    ch.call(token, "sendMessage", payload)
                    continue
            if a["type"] == "send":
                payload = {"chat_id": chat_id, "text": engine.fa_digits(a["text"])[:4096] or "…"}
                if a.get("buttons"):
                    payload["reply_markup"] = to_markup(a["buttons"], cb)
                ch.call(token, "sendMessage", payload)
            elif a["type"] == "media":
                f = files(a["block"]) if files else None
                if f is None:
                    continue  # the owner has not uploaded the file yet: the text above still went out
                if ch.name != "bale":  # the Telegram relay carries JSON only
                    ch.call(token, "sendMessage", {"chat_id": chat_id, "text": "📎 ارسال فایل فعلاً فقط در بله پشتیبانی می‌شود."})
                    continue
                name, mime, data = f
                method, field = ("sendPhoto", "photo") if a["kind"] == "image" else ("sendDocument", "document")
                api_upload(token, method, {"chat_id": chat_id}, field, name, data, mime)
            elif a["type"] == "location":
                ch.call(token, "sendLocation", {"chat_id": chat_id, "latitude": a["latitude"], "longitude": a["longitude"]})
            elif a["type"] == "invoice":
                if not wallet:
                    raise BaleError("no wallet token")
                ch.call(token, "sendInvoice", {"chat_id": chat_id, "title": a["title"], "description": engine.fa_digits(a["text"])[:255] or "سفارش",
                                               "payload": f"o:{a['rid']}", "provider_token": wallet,
                                               "prices": [{"label": a["title"], "amount": int(a["amount"]) * 10}]})  # Bale amounts are rials
            elif a["type"] == "notify_customer":
                # a message for ANOTHER customer (e.g. promoted from the waitlist), possibly on the other messenger
                cust = str(a.get("cust", ""))
                if cust.startswith(mine):
                    payload = {"chat_id": cust[len(mine):], "text": engine.fa_digits(a["text"])[:4096]}
                    if a.get("buttons"):
                        payload["reply_markup"] = to_markup(a["buttons"], {})
                    ch.call(token, "sendMessage", payload)
                elif others is not None:
                    others.append(a)
            elif a["type"] == "notify_admin" and admin_chat_id:
                ch.call(token, "sendMessage", {"chat_id": admin_chat_id, "text": ("🔔 " + a["text"])[:4096]})
        except Exception as e:  # noqa: BLE001
            log.warning("send failed: %s", e)
            if a["type"] == "invoice":
                failed_invoices.append(a["rid"])
    session["_cb"] = cb
    return failed_invoices


def wallet_token(db: Session, pub: Publication) -> str:
    """The owner's wallet token, or "" when payments are not available for this bot.
    On the shared bot only Bale's published TEST token is allowed: real money must reach the owner's own wallet, never Botyar's."""
    cfg = db.scalars(select(PaymentConfig).where(PaymentConfig.bot_id == pub.bot_id)).first()
    if cfg is None:
        return ""
    try:
        tok = decrypt(cfg.token_enc)
    except BaleError:
        return ""
    return tok if pub.mode == "own" or tok.startswith("WALLET-TEST-") else ""


def _payload_record(db: Session, payload: str) -> Record | None:
    if not isinstance(payload, str) or not re.fullmatch(r"o:\d{1,12}", payload):
        return None
    rec = db.get(Record, int(payload[2:]))
    return rec if rec is not None and not rec.sandbox else None


def _pre_checkout(db: Session, token: str, q: dict):
    """Bale asks (10 s limit) whether this payment may go ahead: only for a live, unpaid order of this very customer and amount."""
    rec = _payload_record(db, q.get("invoice_payload"))
    ok = bool(rec) and rec.data.get("status") == "awaiting_payment" and rec.data.get("_cust") == f"bale:{(q.get('from') or {}).get('id')}" \
        and q.get("total_amount") == int(rec.data.get("total", -1)) * 10 and q.get("currency", "IRR") == "IRR"
    body = {"pre_checkout_query_id": q.get("id"), "ok": ok}
    if not ok:
        body["error_message"] = "این سفارش دیگر معتبر نیست؛ لطفاً دوباره سفارش دهید."
    try:
        api_call(token, "answerPreCheckoutQuery", body)
    except Exception as e:  # noqa: BLE001
        log.warning("answerPreCheckoutQuery failed: %s", e)


def _paid(db: Session, token: str, msg: dict):
    pay = msg["successful_payment"]
    chat_id = str((msg.get("chat") or {}).get("id", ""))
    rec = _payload_record(db, pay.get("invoice_payload"))
    if rec is None or rec.data.get("_cust") != f"bale:{chat_id}":
        log.warning("payment for an unknown order: %s", pay.get("invoice_payload"))
        return
    pub = db.scalars(select(Publication).where(Publication.bot_id == rec.bot_id)).first()
    ver = db.scalars(select(BotVersion).where(BotVersion.bot_id == rec.bot_id, BotVersion.version == (pub.version if pub else 0))).first()
    if pub is None or ver is None:
        return
    spec = BotSpec.model_validate(ver.spec)
    with _locks[rec.bot_id]:
        store = SqlStore(db, rec.bot_id, sandbox=False)
        row = store.find(rec.collection, id=rec.id)[0]
        if pay.get("total_amount") != int(row.get("total", -1)) * 10:
            log.error("payment amount mismatch for record %s", rec.id)
            return
        block = spec.block(rec.collection)
        actions = engine.mark_paid(spec, store, dates.now_tehran(), block, row, str(pay.get("provider_payment_charge_id") or pay.get("telegram_payment_charge_id") or ""))
        db.commit()
    if actions:
        deliver(token, chat_id, actions + [engine.menu_actions(spec)], {}, pub.admin_chat_id)


def shared_username_for(ch: Channel) -> str:
    if ch.name == "bale":
        return shared_username()
    from . import telegram

    return telegram.shared_username()


def say(token: str, chat_id: str, text: str, ch: Channel = BALE):
    try:
        ch.call(token, "sendMessage", {"chat_id": chat_id, "text": text})
    except Exception as e:  # noqa: BLE001
        log.warning("send failed: %s", e)


def send_customer_actions(db: Session, bot_id: int, actions: list[dict]) -> int:
    """Deliver notify_customer messages outside a live chat turn (owner dashboard, reminders, or a customer on the
    other messenger), each on the messenger its customer key names. Returns how many were sent."""
    sent = 0
    for ch in CHANNELS.values():
        mine = f"{ch.name}:"
        wanted = [a for a in actions if a["type"] == "notify_customer" and str(a.get("cust", "")).startswith(mine)]
        if not wanted:
            continue
        pub = db.scalars(select(ch.pub_model).where(ch.pub_model.bot_id == bot_id)).first()
        if pub is None:
            continue  # not published on this messenger: there is nobody there to tell
        try:
            token = pub_token(ch, pub)
        except BaleError:
            continue
        for a in wanted:
            try:
                payload = {"chat_id": a["cust"][len(mine):], "text": engine.fa_digits(a["text"])[:4096]}
                if a.get("buttons"):
                    payload["reply_markup"] = to_markup(a["buttons"], {})
                ch.call(token, "sendMessage", payload)
                sent += 1
            except Exception as e:  # noqa: BLE001 - e.g. the customer blocked the bot
                log.warning("customer message failed: %s", e)
    return sent


# ---------- shared bot directory ----------
DIRECTORY_PAGE = 8


def _hidden(db: Session, bot_id: int) -> bool:
    row = db.scalars(select(BotListing).where(BotListing.bot_id == bot_id)).first()
    return bool(row and row.hidden)


def directory(db: Session, ch: Channel, page: int, edit: bool = False) -> dict:
    """The list a customer sees on a shared bot without a business picked: every bot published there whose owner did
    not hide it, newest first, DIRECTORY_PAGE per page. Buttons: bdir:<publication id>, paging bdirp:<page>."""
    Pub = ch.pub_model
    hidden = select(BotListing.bot_id).where(BotListing.hidden.is_(True))
    q = (select(Pub.id, Bot.name).join(Bot, Bot.id == Pub.bot_id)
         .where(Pub.mode == "shared", Pub.bot_id.not_in(hidden)).order_by(Pub.id.desc()))
    rows = db.execute(q.offset(page * DIRECTORY_PAGE).limit(DIRECTORY_PAGE + 1)).all()
    if not rows and page == 0:
        return {"type": "send", "text": "سلام! 👋 هنوز کسب‌وکاری در این ربات فهرست نشده است. اگر لینک یک کسب‌وکار را دارید، روی همان لینک بزنید.", "buttons": []}
    buttons = [{"text": name[:48], "data": f"bdir:{pid}"} for pid, name in rows[:DIRECTORY_PAGE]]
    if len(rows) > DIRECTORY_PAGE:
        buttons.append({"text": "بعدی ◀", "data": f"bdirp:{page + 1}"})
    if page > 0:
        buttons.append({"text": "▶ قبلی", "data": f"bdirp:{page - 1}"})
    text = "سلام! 👋 با کدام کسب‌وکار کار دارید؟ یکی را انتخاب کنید." + (f"\n(صفحه‌ی {page + 1})" if page else "") + \
        "\nبرای برگشتن به همین فهرست در هر زمان: /switch"
    return {"type": "send", "text": text, "buttons": buttons, **({"edit": True} if edit else {})}


# ---------- update handling ----------
_gate_notice: dict[int, object] = {}  # bot id -> day the owner was last told the join check cannot be made
_cap_notice: dict[int, object] = {}  # bot id -> day the owner was last told the customer cap is full
_locks: dict[int, threading.Lock] = defaultdict(threading.Lock)  # serialise a bot's bookings (capacity checks)
_seen: dict[str, int] = {}


def process_update(kind: str, pub_id: int | None, update: dict, ch: Channel = BALE):
    db = SessionLocal()
    try:
        _process(db, kind, pub_id, update, ch)
    except Exception:  # noqa: BLE001
        log.exception("update failed")
        db.rollback()
    finally:
        db.close()


def _process(db: Session, kind: str, pub_id: int | None, update: dict, ch: Channel = BALE):
    key = f"{ch.name}:{kind}:{pub_id}"
    uid = update.get("update_id")
    if isinstance(uid, int):
        if uid <= _seen.get(key, -1):
            return  # the messenger retried a delivery we already handled
        _seen[key] = uid

    own_pub = db.get(ch.pub_model, pub_id) if kind == "own" else None
    if kind == "own" and own_pub is None:
        return
    token = ch.shared_token() if kind == "shared" else decrypt(own_pub.token_enc)

    if ch.payments and update.get("pre_checkout_query"):
        _pre_checkout(db, token, update["pre_checkout_query"])
        return
    if ch.payments and (update.get("message") or {}).get("successful_payment"):
        _paid(db, token, update["message"])
        return

    chat_obj = (update.get("channel_post") or update.get("message") or {}).get("chat") or {}
    if "channel_post" in update or chat_obj.get("type") in ("group", "supergroup", "channel"):
        communities.handle_update(db, ch, kind, own_pub, update, token)  # groups and channels: forwarding, moderation, linking
        return

    cq, msg = update.get("callback_query"), update.get("message")
    if cq:
        chat = (cq.get("message") or {}).get("chat", {}).get("id") or (cq.get("from") or {}).get("id")
        text, cq_id = cq.get("data") or "", cq.get("id")
    elif msg:
        if (msg.get("chat") or {}).get("type", "private") != "private":
            return
        chat, text, cq_id = msg["chat"]["id"], msg.get("text"), None
    else:
        return
    if chat is None:
        return
    chat_id = str(chat)
    clicked_message_id = ((cq or {}).get("message") or {}).get("message_id") if cq else None
    if cq_id:  # mandatory per Bale docs (and stops Telegram's loading spinner)
        try:
            ch.call(token, "answerCallbackQuery", {"callback_query_id": cq_id})
        except Exception as e:  # noqa: BLE001
            log.warning("answerCallbackQuery failed: %s", e)
    if not text:
        say(token, chat_id, "لطفاً فقط پیام متنی بفرستید یا از دکمه‌ها استفاده کنید.", ch)
        return
    t = engine.norm(text)
    Pub, Link = ch.pub_model, ch.link_model

    # owner links their chat to receive notifications
    if t.startswith("/admin"):
        code = t[6:].strip().upper()
        target = db.scalars(select(Pub).where(Pub.admin_code == code)).first() if code else None
        if target is None or (own_pub is not None and target.id != own_pub.id):
            say(token, chat_id, "کد مدیر نامعتبر است. کد را از صفحه‌ی «انتشار» در بات‌یار کپی کنید: /admin CODE", ch)
        else:
            target.admin_chat_id = chat_id
            db.commit()
            say(token, chat_id, "✅ انجام شد. از این به بعد ثبت‌های جدید همین‌جا برای شما ارسال می‌شود.", ch)
        return

    pub = own_pub
    welcome_now = False
    refrow = None
    if kind == "own" and t.startswith("/start"):
        refrow = referral.resolve(db, t[6:].strip())
    if kind == "shared":
        # A customer reaches a business's bot through its link (ble.ir/<bot>?start=CODE, t.me/<bot>?start=CODE: the
        # messenger sends "/start CODE") or by picking it from the directory. A code typed as a message is NOT accepted.
        link = db.scalars(select(Link).where(Link.chat_id == chat_id)).first()
        if t == "/switch":
            if link:
                db.delete(link)
                db.commit()
            deliver(token, chat_id, [directory(db, ch, 0)], {}, ch=ch)
            return
        page = re.fullmatch(r"bdirp:(\d{1,4})", t)
        if page:
            deliver(token, chat_id, [directory(db, ch, int(page.group(1)), edit=True)], {}, edit_message_id=clicked_message_id, ch=ch)
            return
        found = None
        payload = t[6:].strip() if t.startswith("/start") else ""
        picked = re.fullmatch(r"bdir:(\d{1,12})", t)
        refrow = referral.resolve(db, payload)
        if refrow is not None:  # an invite link: it names the business through the inviter
            found = db.scalars(select(Pub).where(Pub.bot_id == refrow.bot_id, Pub.mode == "shared")).first()
        elif re.fullmatch(r"[A-Za-z0-9]{4,12}", payload):
            found = db.scalars(select(Pub).where(Pub.code == payload.upper(), Pub.mode == "shared")).first()
        elif picked:
            cand = db.get(Pub, int(picked.group(1)))
            found = cand if cand is not None and cand.mode == "shared" and not _hidden(db, cand.bot_id) else None
        if found:
            if link:
                link.pub_id = found.id
            else:
                db.add(Link(chat_id=chat_id, pub_id=found.id))
            db.commit()
            pub, welcome_now = found, True
        elif link:
            pub = db.get(Pub, link.pub_id)
        if pub is None:
            deliver(token, chat_id, [directory(db, ch, 0)], {}, ch=ch)
            return

    ver = db.scalars(select(BotVersion).where(BotVersion.bot_id == pub.bot_id, BotVersion.version == pub.version)).first()
    if ver is None:
        say(token, chat_id, "این ربات فعلاً در دسترس نیست.", ch)
        return
    spec = BotSpec.model_validate(ver.spec)
    skey = f"{ch.name}:{chat_id}"
    with _locks[pub.bot_id]:
        row = db.scalars(select(ChatSession).where(ChatSession.bot_id == pub.bot_id, ChatSession.key == skey)).first()
        if row is None:
            row = ChatSession(bot_id=pub.bot_id, key=skey, state=engine.new_session())
            db.add(row)
        state = copy.deepcopy(row.state)  # a shallow copy would hide in-place edits from SQLAlchemy's change detection
        if t.startswith("~"):
            t = state.get("_cb", {}).get(t, t)
        if t in ("/stop", "/resume"):  # announcements and reminders opt-out
            state["muted"] = t == "/stop"
            row.state = state
            db.commit()
            say(token, chat_id, "اطلاعیه‌های این ربات دیگر برایتان نمی‌آید (یادآوری نوبت‌ها همچنان ارسال می‌شود). برای فعال‌سازی دوباره: /resume" if t == "/stop" else "اطلاعیه‌ها دوباره فعال شد ✅", ch)
            return
        if welcome_now:
            muted = state.get("muted")
            state, t = engine.new_session(), "/start"
            if muted:
                state["muted"] = True
        elif kind == "shared" and t.startswith("/start"):
            t = "/start"
        frm = (msg or cq or {}).get("from") or {}
        if frm.get("first_name"):
            state["cust_name"] = str(frm["first_name"])[:40]
        state["cust"] = skey  # stable customer identity (set last: the welcome path above replaces the whole state)
        if spec.gate is not None and not (t in ("/stop", "/resume")):
            verdict = gate.verify(ch, token, spec, state, chat_id)
            if state.get("gate_error") and pub.admin_chat_id and _gate_notice.get(pub.bot_id) != dates.now_tehran().date():
                _gate_notice[pub.bot_id] = dates.now_tehran().date()
                say(token, pub.admin_chat_id, "⚠️ بررسی عضویت در کانال انجام نشد (ربات را در کانال ادمین کنید و نام کانال را بررسی کنید)؛ فعلاً مشتری‌ها بدون بررسی وارد می‌شوند.", ch)
            if verdict == "blocked":
                row.state = state
                db.commit()
                deliver(token, chat_id, [gate.prompt(spec, ch.name)], state, ch=ch)
                row.state = state
                db.commit()
                return
            if t == "gate:check":
                t = "/start"
        if db.scalars(select(BannedCustomer).where(BannedCustomer.bot_id == pub.bot_id, BannedCustomer.key == skey)).first():
            row.state = state
            db.commit()
            say(token, chat_id, "دسترسی شما به این ربات مسدود شده است.", ch)
            return
        bot = db.get(Bot, pub.bot_id)
        was_new = db.scalars(select(CustomerSeen).where(CustomerSeen.bot_id == pub.bot_id, CustomerSeen.key == skey)).first() is None
        if bot is not None and not billing.track_customer(db, bot, skey, state.get("cust_name", "")):
            row.state = state  # a NEW customer beyond the plan's monthly cap: politely refused, the owner is told once a day
            db.commit()
            say(token, chat_id, billing.FULL_TEXT, ch)
            today = dates.now_tehran().date()
            if pub.admin_chat_id and _cap_notice.get(pub.bot_id) != today:
                _cap_notice[pub.bot_id] = today
                say(token, pub.admin_chat_id, "⚠️ ظرفیت ماهانه‌ی مشتری‌های پلن شما پر شده و مشتری جدید پذیرفته نمی‌شود. برای ظرفیت بیشتر از بخش «پلن‌ها» در بات‌یار ارتقا دهید.", ch)
            return
        ref_block = next((b for b in spec.blocks if b.type == "referral"), None)
        if refrow is not None and was_new and refrow.bot_id == pub.bot_id:
            owed = referral.convert(db, pub.bot_id, refrow, skey, ref_block.goal if ref_block else None)
            if owed:
                others_ref = list(owed)
                db.flush()
            else:
                others_ref = []
        else:
            others_ref = []
        if ref_block is not None:  # this customer's personal link and invite count, for the referral block
            code = referral.code_for(db, pub.bot_id, skey)
            username = pub.bot_username or (shared_username_for(ch) if pub.mode == "shared" else "")
            state["ref"] = {"link": referral.link(ch.name, username, code), "count": referral.count_for(db, pub.bot_id, skey)}
        wallet = wallet_token(db, pub) if ch.payments else ""
        state["pay_ok"], state["pay_sim"] = bool(wallet), False  # pay_sim (the fake pay button) must never be on in a real chat
        store = SqlStore(db, pub.bot_id, sandbox=False)
        actions = engine.handle(spec, state, t, store, matcher=faq_index.matcher_for(db, pub.bot_id, spec))
        anon_others: list[dict] = []
        if any(a["type"].startswith("anon_") for a in actions):
            actions, anon_others = anon.run(db, bot, spec, state, skey, actions)
        others: list[dict] = []  # e.g. a waitlisted customer on the other messenger who just got the freed place
        for rid in deliver(token, chat_id, actions, state, pub.admin_chat_id, clicked_message_id, wallet, ch, others,
                           files=lambda block_id: media.get_file(db, pub.bot_id, block_id)):
            rec = db.get(Record, rid)  # the invoice could not be sent: keep the order as an ordinary one and tell both sides
            if rec:
                rec.data = {**rec.data, "status": "new", "_pay_failed": True}
                say(token, chat_id, "ارسال فاکتور پرداخت ناموفق بود؛ سفارش شما ثبت شد و مدیر درباره‌ی پرداخت با شما هماهنگ می‌کند.", ch)
                if pub.admin_chat_id:
                    say(token, pub.admin_chat_id, f"⚠️ فاکتور پرداخت سفارش {rid} ارسال نشد؛ سفارش بدون پرداخت آنلاین ثبت شد.", ch)
        row.state = state
        db.commit()
        if others:
            send_customer_actions(db, pub.bot_id, others)
        if anon_others:
            send_customer_actions(db, pub.bot_id, anon_others)
        if others_ref:
            send_customer_actions(db, pub.bot_id, others_ref)
            if ref_block is not None and pub.admin_chat_id and any("به هدف رسیدید" in a["text"] for a in others_ref):
                say(token, pub.admin_chat_id, "🏆 یکی از مشتری‌ها به هدف دعوت رسید؛ جایزه‌اش را از بخش مشتریان/دعوت‌ها ببینید.", ch)
