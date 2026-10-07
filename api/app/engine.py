"""Deterministic runtime: engine.handle(spec, session, text, store) -> list[Action].

No LLM here. The same engine drives the web simulator, the test runner and the Bale adapter.
Actions: {"type": "send", "text", "buttons": [{"text","data"}]} | {"type": "notify_admin", "text"}
"""
from __future__ import annotations

import random
import re
import logging
import math
from datetime import date, datetime, time, timedelta
from typing import Any, Protocol

from . import dates
from .engine_text import fa_digits, fa_norm, norm  # noqa: F401  (re-exported: engine.norm / engine.fa_norm / engine.fa_digits)
from .faq_match import LexicalMatcher, MatcherUnavailable, RateLimited, decide
from .spec import PLACEHOLDER, jalali_date, norm_code, BotSpec, BookingBlock, CatalogOrderBlock, ContactBlock, FaqBlock, FeedbackBlock, MenuBlock, QuizBlock, ReferralBlock, AnonChatBlock, FormBlock, FormField, MessageBlock

log = logging.getLogger("botyar.engine")
STALE_RESETS = {"count": 0}  # tests assert this stays 0 unless a bot really changed under a conversation
MY_LABEL = "ثبت‌های من"  # fallback only: the real label is my_label(spec), named after what the bot takes (orders, appointments, sign-ups)
CODES_LABEL = "کدهای تخفیف"  # built-in menu entry, present when a shop has discount codes that are visible to customers
MY_BLOCK = "__my__"
STATUS_FA = {"confirmed": "تأیید شده", "waitlisted": "در لیست انتظار", "new": "سفارش جدید", "preparing": "در حال آماده‌سازی", "ready": "آماده", "done": "تحویل داده شد", "cancelled": "لغو شده", "unanswered": "بدون پاسخ", "awaiting_payment": "در انتظار پرداخت", "handled": "رسیدگی شد", "no_show": "حاضر نشد", "awaiting_transfer": "منتظر واریز", "transfer_sent": "واریز شد، منتظر تأیید",
             "received": "دریافت شد", "reviewing": "در حال بررسی", "accepted": "پذیرفته شد", "rejected": "رد شد"}
FORM_DECISIONS = {"reviewing": "🔎 درخواست شما در حال بررسی است.", "accepted": "✅ درخواست شما پذیرفته شد.", "rejected": "متأسفانه درخواست شما پذیرفته نشد."}
FILE_EXT = {".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".webp"}
FILE_MAX = 10 * 1024 * 1024
ORDER_FLOW = ["new", "preparing", "ready", "done"]  # the owner moves an order forward; the customer is told at each step
MENU_WORDS = {"/start", "/menu", "منو", "منوی اصلی", "شروع"}
CANCEL_WORDS = {"/cancel", "انصراف", "لغو"}









def catalog_categories(rows: list[dict]) -> list[str]:
    out: list[str] = []
    for r in rows:
        c = (r.get("category") or "").strip()
        if c and c not in out:
            out.append(c)
    return out


def catalog_filter(rows: list[dict], category: str | None, query: str | None) -> list[dict]:
    q = fa_norm(query) if query else ""
    return [r for r in rows if (not category or r.get("category") == category) and (not q or q in fa_norm(r["name"]))]


def total_per_product(lines: list[tuple[int, int]]) -> dict[int, int]:
    need: dict[int, int] = {}
    for pid, qty in lines:
        need[pid] = need.get(pid, 0) + qty
    return need


class Store(Protocol):
    def add(self, collection: str, data: dict) -> dict: ...
    def count(self, collection: str, **where: Any) -> int: ...
    def categories(self, block_id: str) -> list[str]: ...
    def products(self, block_id: str, category: str | None, query: str | None, offset: int, limit: int) -> tuple[list[dict], int]: ...
    def product(self, block_id: str, pid: int) -> dict | None: ...
    def reserve(self, block_id: str, lines: list[tuple[int, int]]) -> list[int]: ...
    def release(self, block_id: str, lines: list[tuple[int, int]]) -> None: ...
    def find(self, collection: str, **where: Any) -> list[dict]: ...
    def update(self, collection: str, row_id: int, **fields: Any) -> None: ...
    def time_off(self, block_id: str) -> list[dict]: ...  # [{date, start, end, staff}] closed by the owner


class MemoryStore:
    def __init__(self):
        self.rows: dict[str, list[dict]] = {}
        self.catalog: dict[str, list[dict]] = {}
        self.closed: dict[str, list[dict]] = {}  # block id -> hours the owner closed

    def load_catalog(self, block_id: str, products: list[dict]):
        self.catalog[block_id] = [{**p, "id": i} for i, p in enumerate(products, 1)]

    def time_off(self, block_id):
        return self.closed.get(block_id, [])

    def add(self, collection, data):
        row = {"id": len(self.rows.setdefault(collection, [])) + 1, **data}
        self.rows[collection].append(row)
        return row

    def count(self, collection, **where):
        return sum(all(r.get(k) == v for k, v in where.items()) for r in self.rows.get(collection, []))

    def categories(self, block_id):
        return catalog_categories(self.catalog.get(block_id, []))

    def products(self, block_id, category, query, offset, limit):
        rows = catalog_filter(self.catalog.get(block_id, []), category, query)
        return rows[offset:offset + limit], len(rows)

    def product(self, block_id, pid):
        return next((p for p in self.catalog.get(block_id, []) if p["id"] == pid), None)

    def find(self, collection, **where):
        return [r for r in self.rows.get(collection, []) if all(r.get(k) == v for k, v in where.items())]

    def update(self, collection, row_id, **fields):
        for r in self.rows.get(collection, []):
            if r["id"] == row_id:
                r.update(fields)

    def release(self, block_id, lines):
        rows = {p["id"]: p for p in self.catalog.get(block_id, [])}
        for pid, qty in total_per_product(lines).items():
            if pid in rows and rows[pid]["stock"] is not None:
                rows[pid]["stock"] += qty

    def reserve(self, block_id, lines):
        rows = {p["id"]: p for p in self.catalog.get(block_id, [])}
        need = total_per_product(lines)  # the same product on two cart lines must be checked as one quantity
        failed = [pid for pid, qty in need.items() if pid not in rows or (rows[pid]["stock"] is not None and rows[pid]["stock"] < qty)]
        if not failed:
            for pid, qty in need.items():
                if rows[pid]["stock"] is not None:
                    rows[pid]["stock"] -= qty
        return failed


def new_session() -> dict:
    return {"block": None, "step": None, "data": {}, "cust": None}


def send(text, buttons=None, edit=False):
    """edit=True asks the channel to replace the message the user just clicked on (in-place navigation)."""
    a = {"type": "send", "text": text, "buttons": buttons or []}
    if edit:
        a["edit"] = True
    return a


def _btn(text, data=None):
    return {"text": text, "data": data or text}


def validate(field: FormField, raw: str) -> tuple[bool, Any, str]:
    value = norm(raw)
    if not value:
        return (not field.required, "", "این مورد الزامی است.")
    if field.kind == "phone":
        v = value.replace(" ", "").replace("-", "")
        if v.startswith("+98"):
            v = "0" + v[3:]
        elif v.startswith("98") and len(v) == 12:
            v = "0" + v[2:]
        if re.fullmatch(r"09\d{9}", v):
            return True, v, ""
        return False, None, "شماره موبایل معتبر نیست. مثال: 09123456789"
    if field.kind == "number":
        if not re.fullmatch(r"\d+", value):
            return False, None, "لطفاً فقط عدد وارد کنید."
        n = int(value)
        lo, hi = field.min_value, field.max_value
        if (lo is not None and n < lo) or (hi is not None and n > hi):
            rng = f"بین {lo} و {hi}" if lo is not None and hi is not None else (f"دست‌کم {lo}" if lo is not None else f"حداکثر {hi}")
            return False, None, fa_digits(f"لطفاً عددی {rng} وارد کنید.")
        return True, n, ""
    if field.kind == "choice":
        for c in field.choices:
            if c == raw.strip() or norm(c) == value:
                return True, c, ""
        return False, None, "لطفاً یکی از گزینه‌ها را انتخاب کنید."
    if field.kind == "multi":  # typed instead of tapped: «الف، ب»
        picked = [c for part in re.split(r"[،,]", raw) if part.strip() for c in field.choices if norm(c) == norm(part)]
        if picked and len(picked) == len([p for p in re.split(r"[،,]", raw) if p.strip()]):
            return True, "، ".join(c for c in field.choices if c in picked), ""
        return False, None, "لطفاً گزینه‌ها را با دکمه‌ها انتخاب کنید و سپس «تمام» را بزنید."
    if field.kind == "email":
        v = value.replace(" ", "").lower()
        if re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", v):
            return True, v, ""
        return False, None, "نشانی ایمیل معتبر نیست. مثال: name@example.com"
    if field.kind == "national_id":
        v = value.replace(" ", "").replace("-", "")
        if re.fullmatch(r"\d{10}", v) and len(set(v)) > 1:
            s = sum(int(v[i]) * (10 - i) for i in range(9)) % 11
            if int(v[9]) == (s if s < 2 else 11 - s):
                return True, v, ""
        return False, None, "کد ملی معتبر نیست؛ لطفاً ۱۰ رقم کد ملی را درست وارد کنید."
    if field.kind == "date":
        d = dates.parse_jalali(raw)
        if d is not None:
            return True, dates.jalali_str(d), ""
        return False, None, "تاریخ معتبر نیست. لطفاً به شکل ۱۴۰۳/۰۸/۱۵ یا «۱۵ آبان ۱۴۰۳» بنویسید."
    if field.kind == "file":  # "file:<file id>|<size>|<name>" from a document message, or "photo:<file id>"
        if value.startswith("photo:") and len(value) > 6:
            return True, {"id": value[6:], "name": "عکس.jpg", "size": 0, "photo": True}, ""
        m = re.fullmatch(r"file:([^|]+)\|(\d*)\|(.*)", value, re.S)
        if not m:
            return False, None, "لطفاً فایل را از 📎 بفرستید (PDF، Word یا عکس)."
        name, size = m.group(3).strip() or "file", int(m.group(2) or 0)
        if "." + name.rsplit(".", 1)[-1].lower() not in FILE_EXT:
            return False, None, "فقط فایل PDF، Word یا عکس پذیرفته می‌شود."
        if size > FILE_MAX:
            return False, None, "حجم فایل بیشتر از ۱۰ مگابایت است."
        return True, {"id": m.group(1), "name": name[:120], "size": size}, ""
    if value.startswith("file:"):
        return False, None, "در این مرحله فایل لازم نیست؛ لطفاً پاسخ را بنویسید."
    if field.kind == "location":
        m = re.fullmatch(r"loc:(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)", value)
        if m:
            return True, map_link(float(m.group(1)), float(m.group(2))), ""
        if value.startswith(("loc:", "photo:")) or len(value) < 5:
            return False, None, "لطفاً موقعیت را از 📎 و گزینه‌ی «موقعیت مکانی» بفرستید، یا نشانی را کامل بنویسید."
        return True, raw.strip(), ""
    if value.startswith(("photo:", "loc:")):
        return False, None, "لطفاً پاسخ را به صورت متن بنویسید."
    return True, raw.strip(), ""


def map_link(lat: float, lon: float) -> str:
    """A shared map location as a link the owner can open (stored as the answer)."""
    return f"https://www.google.com/maps?q={lat:.6f},{lon:.6f}"


SKIP = "رد کردن"  # the button of an optional question (a messenger cannot send an empty message)


def _ask(field: FormField, d: dict | None = None, edit: bool = False):
    skip = [] if field.required else [_btn(SKIP, "skip")]
    if field.kind == "choice":
        return send(field.label, [_btn(c) for c in field.choices] + skip)
    if field.kind == "multi":
        picked = (d or {}).get(f"_m_{field.key}", [])
        buttons = [_btn(("✅ " if c in picked else "") + c, f"mt:{i}") for i, c in enumerate(field.choices)]
        return send(field.label + "\n(یک یا چند گزینه را انتخاب کنید و سپس «تمام» را بزنید)", buttons + [_btn("تمام", "mt:done")] + skip, edit)
    hint = {"date": "\n(برای مثال ۱۴۰۳/۰۸/۱۵)",
            "location": "\n(از 📎 گزینه‌ی «موقعیت مکانی» را بزنید و موقعیت را بفرستید، یا نشانی را بنویسید)",
            "file": "\n(فایل را از 📎 بفرستید: PDF، Word یا عکس، تا ۱۰ مگابایت)"}.get(field.kind, "")
    return send(field.label + hint, skip)


def _next_field(fields: list[FormField], d: dict, start: int) -> int | None:
    """The next question to ask from `start`, skipping conditional ones whose condition is not met
    and the details the customer chose to reuse («با همین مشخصات»)."""
    for i in range(start, len(fields)):
        f = fields[i]
        if f.key in d.get("_prefilled", ()):
            continue
        if f.show_if:
            given = {p.strip() for p in str(d.get(f.show_if.field, "")).split("،")}
            if not given & set(f.show_if.equals):
                d.pop(f.key, None)
                continue
        return i
    return None


NAME_KEYS = {"name", "full_name", "fullname", "first_name", "last_name", "family", "family_name"}


def _identity(f: FormField) -> bool:
    """Details that describe the person (worth reusing next time), not answers about this particular booking/order."""
    return f.kind in ("phone", "email", "national_id") or (f.kind == "text" and (f.key in NAME_KEYS or f.key.endswith("_name")))


def _known_details(spec: BotSpec, store, session, fields: list[FormField]) -> dict:
    """The latest answer this customer gave, anywhere in this bot, to each identity question of `fields`."""
    cust = session.get("cust")
    want = {f.key for f in fields if _identity(f) and not f.show_if}
    if not cust or not want or session.get("test"):  # automated tests replay one customer many times: keep them literal
        return {}
    latest: dict[str, tuple[tuple, Any]] = {}
    for b in spec.blocks:
        if not getattr(b, "fields", None):
            continue
        for r in store.find(b.id, _cust=cust):
            when = (str(r.get("_at", "")), r.get("id", 0))  # newest first; the record number breaks a tie
            for k in want:
                v = r.get(k)
                if v not in (None, "") and (k not in latest or when > latest[k][0]):
                    latest[k] = (when, v)
    return {k: v for k, (_, v) in latest.items()}


def _reuse_prompt(fields: list[FormField], known: dict):
    lines = "\n".join(f"{f.label.rstrip('؟?:').strip()}: {known[f.key]}" for f in fields if f.key in known)
    return send("با همین مشخصات ادامه می‌دهید؟\n" + lines, [_btn("✅ بله", "ru:yes"), _btn("✏️ مشخصات جدید", "ru:no")])


def _first_question(spec: BotSpec, session, store, fields: list[FormField]) -> list:
    """Start the questions; a returning customer is first offered their saved name/number/… in one tap."""
    d = session["data"]
    known = _known_details(spec, store, session, fields)
    if known:
        d["_known"], session["step"] = known, "reuse"
        return [_reuse_prompt(fields, known)]
    nxt = _next_field(fields, d, 0)
    session["step"] = nxt
    return [_ask(fields[nxt], d)]


def _field_step(session, fields: list[FormField], text: str) -> tuple[bool, list]:
    """One answer to the current question (form, booking or order). Returns (all answered, actions to send)."""
    d = session["data"]
    if session["step"] == "reuse":
        t = norm(text)
        if t not in ("ru:yes", "ru:no"):
            return False, [send("لطفاً یکی از دکمه‌ها را بزنید."), _reuse_prompt(fields, d["_known"])]
        known = d.pop("_known", {})
        if t == "ru:yes":
            d.update(known)
            d["_prefilled"] = list(known)
        nxt = _next_field(fields, d, 0)
        if nxt is None:
            d.pop("_prefilled", None)
            return True, []
        session["step"] = nxt
        return False, [_ask(fields[nxt], d)]
    field = fields[session["step"]]
    t = norm(text)
    if field.kind == "multi" and t.startswith("mt:"):
        picked = d.setdefault(f"_m_{field.key}", [])
        if t != "mt:done":
            i = int(t[3:]) if t[3:].isdigit() else -1
            if 0 <= i < len(field.choices):
                c = field.choices[i]
                picked.remove(c) if c in picked else picked.append(c)
            return False, [_ask(field, d, edit=True)]
        if not picked and field.required:
            return False, [send("دست‌کم یک گزینه را انتخاب کنید."), _ask(field, d)]
        value = "، ".join(c for c in field.choices if c in picked)
        d.pop(f"_m_{field.key}", None)
    elif t in ("skip", norm(SKIP)) and not field.required:
        value = ""
    else:
        ok, value, err = validate(field, text)
        if not ok:
            return False, [send(err), _ask(field, d)]
        if isinstance(value, dict):  # a file: the record shows its name; the file id stays internal
            d.setdefault("_files", {})[field.key] = value
            value = "📎 " + value["name"]
    d[field.key] = value
    nxt = _next_field(fields, d, session["step"] + 1)
    if nxt is None:
        d.pop("_prefilled", None)  # internal: never saved with the record
        return True, []
    session["step"] = nxt
    return False, [_ask(fields[nxt], d)]


def _is_appointment(spec: BotSpec, b) -> bool:
    """A calendar bot, or one the owner themself calls a «نوبت» (a dentist with fixed weekly times): its records are نوبت, not ثبت‌نام."""
    return bool(b.schedule) or "نوبت" in b.title or any("نوبت" in m.label and m.block == b.id for m in spec.menu)


def my_label(spec: BotSpec) -> str:
    """«سفارش‌های من» for a shop, «نوبت‌های من» for appointments, «ثبت‌نام‌های من» for classes; several kinds are named together."""
    nouns = []
    blocks = [b for _, b in _cancel_blocks(spec)]
    if any(b.type == "catalog_order" for b in blocks):
        nouns.append("سفارش")
    bookings = [b for b in blocks if b.type == "booking"]
    if any(_is_appointment(spec, b) for b in bookings):
        nouns.append("نوبت")
    if any(not _is_appointment(spec, b) for b in bookings):
        nouns.append("ثبت‌نام")
    if not nouns:
        return MY_LABEL
    last = nouns[-1] + "‌های من"
    return last if len(nouns) == 1 else "، ".join(n + "‌ها" for n in nouns[:-1]) + " و " + last


def _visible_codes(spec: BotSpec) -> list[tuple[int, int, object, object]]:
    """(block index, code index, block, code) for every discount code customers may see."""
    return [(bi, ci, b, c) for bi, b in enumerate(spec.blocks) if b.type == "catalog_order" for ci, c in enumerate(b.discount_codes) if c.visible]


def builtin_entries(spec: BotSpec) -> list[tuple[str, str]]:
    """The menu entries the engine adds after the owner's own: (key, label), in order. Their data is m:<len(menu)+position>."""
    out = []
    if _cancel_blocks(spec):
        out.append(("mine", my_label(spec)))
    if _visible_codes(spec):
        out.append(("codes", CODES_LABEL))
    return out


def menu_actions(spec: BotSpec, prefix: str | None = None):
    text = prefix if prefix is not None else "از منوی زیر یکی را انتخاب کنید:"
    buttons = [_btn(m.label, f"m:{i}") for i, m in enumerate(spec.menu)]
    for pos, (_, label) in enumerate(builtin_entries(spec)):
        buttons.append(_btn(label, f"m:{len(spec.menu) + pos}"))
    return send(text, buttons)


def _reset(session):
    session.update(block=None, step=None, data={})


def _staff_notice(r: dict, text: str) -> list[dict]:
    """A message for the staff member a booking belongs to (delivered only if they linked their chat with /staff)."""
    return [{"type": "notify_staff", "staff": r["staff"], "text": text}] if r.get("staff") else []


def _notify(spec: BotSpec, block_id: str, summary: str, actions: list, prefix: str | None = None, total: int | None = None, rating: int | None = None):
    """Tell the owner, through every admin_notify that watches this block and whose condition holds
    (min_total: orders of at least that amount; max_rating: feedback of that rating or lower)."""
    for b in spec.blocks:
        if b.type != "admin_notify" or b.on != block_id:
            continue
        if b.min_total and total is not None and total < b.min_total:
            continue
        if b.max_rating and rating is not None and rating > b.max_rating:
            continue
        actions.append({"type": "notify_admin", "text": f"{prefix or b.text}\n{summary}"})


def _summary(data: dict) -> str:
    return "\n".join(f"{k}: {v}" for k, v in data.items() if not k.startswith("_"))


class Cycle:
    """Deterministic stand-in for the random generator: 0, 1, 2, ... (used by the agent's tests)."""

    def __init__(self):
        self.n = -1

    def randrange(self, k: int) -> int:
        self.n += 1
        return self.n % k


_RNG = random.SystemRandom()


def pick_text(block, session: dict, rng) -> str:
    """The message to send: the block's text, or one of its variants chosen at random but never the one shown last time."""
    opts = block.variants or [block.text]
    last = session.setdefault("last", {}).get(block.id)
    idx = rng.randrange(len(opts))
    if len(opts) > 1 and idx == last:
        idx = (idx + 1) % len(opts)
    session["last"][block.id] = idx
    return opts[idx]


# A screen made only of choices ends here: «بازگشت به منو» is added to every other one that offers buttons but no way out,
# so no flow of any bot can strand a customer. Yes/no questions, skips and the notices the bot sends by itself are left alone.
_NO_EXIT_NEEDED = {"ru:yes", "ru:no", "xy", "xn", "sk", "ac:end", "dc:no"}
_NOTICE_PREFIXES = ("rc:", "fbr:", "pay:", "tr:", "tx:", "url:", "go:")


def _with_exit(actions: list[dict]) -> list[dict]:
    for a in actions:
        buttons = a.get("buttons") if a.get("type") == "send" else None
        if not buttons:
            continue
        datas = [b["data"] for b in buttons]
        if any(d == "/menu" or d.startswith("m:") or d in _NO_EXIT_NEEDED or d.startswith(_NOTICE_PREFIXES) for d in datas):
            continue
        a["buttons"] = [*buttons, _btn("بازگشت به منو", "/menu")]
    return actions


def _in_place(actions: list[dict], session: dict) -> list[dict]:
    """A button press answers by REPLACING the message it was on, so the chat holds one living screen instead of a pile of old menus.
    Kept as new messages (the good reasons not to edit): a reply that finishes something (a confirmation followed by the menu is a record
    the customer keeps), and anything with a photo / location / contact / invoice, which cannot replace a text message.
    A step that is still going (a title and the question under it) is merged into the one edited message."""
    visible = [a for a in actions if a["type"] in ("send", "media", "location", "contact", "invoice")]
    if any(a["type"] != "send" for a in visible):
        return actions
    if len(visible) >= 2 and session.get("block") is not None and not any(a.get("buttons") for a in visible[:-1]):
        last = visible[-1]  # a title / notice and the question under it become one message
        last["text"] = "\n\n".join(a["text"] for a in visible)[:4000]
        for a in visible[:-1]:
            actions.remove(a)
        visible = [last]
    if len(visible) == 1:
        visible[0]["edit"] = True
    return actions


def handle(spec: BotSpec, session: dict, text: str, store: Store, now=None, matcher=None, rng=None, clicked: bool = False) -> list[dict]:
    """`clicked`: the customer pressed a button (so there is a message to replace); typed text always gets a new message."""
    if clicked and norm(text) in MENU_WORDS:
        leave = _leave_anon(spec, session)  # «بازگشت به منو» turns the screen back into the main menu in place
        _reset(session)
        return _in_place(_with_exit([*leave, menu_actions(spec)]), session)
    out = _with_exit(_handle(spec, session, text, store, now, matcher, rng))
    return _in_place(out, session) if clicked else out


def _handle(spec: BotSpec, session: dict, text: str, store: Store, now=None, matcher=None, rng=None) -> list[dict]:
    now = now or dates.now_tehran()  # injectable so tests run on a fixed clock
    rng = rng or _RNG
    text_n = norm(text)
    if text_n in MENU_WORDS:
        leave = _leave_anon(spec, session)
        _reset(session)
        return [*leave, send(spec.welcome), menu_actions(spec)]
    if text_n in CANCEL_WORDS:
        leave = _leave_anon(spec, session)
        _reset(session)
        return [*leave, menu_actions(spec, "انصراف انجام شد.")]

    m = re.fullmatch(r"pay:(\d+)", text_n)
    if m and session.get("pay_sim"):  # test payment button: the simulator and the agent's tests only, never a real chat
        return _test_pay(spec, session, int(m.group(1)), store, now)

    m = re.fullmatch(r"rc:(y|n):(\d+):(\d+)", text_n)  # the answer to a reminder's «می‌آیم / نمی‌توانم بیایم»
    if m:
        _reset(session)
        return _attendance(spec, session, store, now, m.group(1) == "y", int(m.group(2)), int(m.group(3)))

    m = re.fullmatch(r"fbr:(\d+):(\d+):([1-5])", text_n)  # a star under an automatic «راضی بودید؟»
    if m:
        _reset(session)
        return _rated_from_request(spec, session, store, now, int(m.group(1)), int(m.group(2)), int(m.group(3)))

    m = re.fullmatch(r"tr:(\d+):(\d+)", text_n)  # «ارسال رسید»: back to the receipt question (e.g. after visiting the menu)
    if m and not (session.get("step") == "ref" and session["data"].get("_rid") == int(m.group(2))):
        bi, rid = int(m.group(1)), int(m.group(2))
        b = spec.blocks[bi] if 0 <= bi < len(spec.blocks) else None
        rows = store.find(b.id, id=rid, _cust=session.get("cust")) if b is not None and b.type == "catalog_order" and session.get("cust") else []
        _reset(session)
        if not rows or rows[0].get("status") != "awaiting_transfer":
            return [send("برای این سفارش رسیدی لازم نیست."), menu_actions(spec)]
        session.update(block=b.id, step="ref", data={"_rid": rid})
        return [send("شماره‌ی پیگیری واریز یا عکس رسید را بفرستید:")]

    m = re.fullmatch(r"tx:(\d+):(\d+)", text_n)  # «انصراف از سفارش» under the card-to-card details
    if m:
        _reset(session)
        return _cancel_transfer(spec, session, store, now, int(m.group(1)), int(m.group(2)))

    m = re.fullmatch(r"go:([a-z0-9_]+)", text_n)  # a button that jumps straight into another part of the bot
    target = next((b for b in spec.blocks if m and b.id == m.group(1) and b.type != "admin_notify"), None)
    if target is not None:
        leave = _leave_anon(spec, session)
        _reset(session)
        return [*leave, *_start_block(spec, session, target, store, now, rng)]

    if text_n.startswith(("photo:", "loc:", "file:")):  # a photo, file or map location: only where the bot asked for one
        here = next((b for b in spec.blocks if b.id == session["block"]), None)
        fields = getattr(here, "fields", None) or []
        step = session.get("step")
        asks_file = isinstance(step, int) and step < len(fields) and fields[step].kind == "file"
        wanted = (session.get("step") == "ref" or asks_file) if text_n.startswith("photo:") else asks_file if text_n.startswith("file:") else bool(fields)
        if not wanted:
            return [send("لطفاً پیام متنی بفرستید یا از دکمه‌ها استفاده کنید.")]

    if session["block"] is None:
        return _from_menu(spec, session, text_n, store, now, rng)

    try:
        if session["block"] == MY_BLOCK:
            return _mine(spec, session, text, store, now)
        block = spec.block(session["block"])
        if block.type == "form":
            return _form(spec, session, block, text, store, now)
        if block.type == "booking":
            return _booking(spec, session, block, text, store, now)
        if block.type == "catalog_order":
            return _order(spec, session, block, text, store, now)
        if block.type == "faq":
            return _faq(spec, session, block, text, store, now, matcher or LexicalMatcher())
        if block.type == "contact":
            return _contact(spec, session, block, text, store, now)
        if block.type == "feedback":
            return _feedback(spec, session, block, text, store, now)
        if block.type == "menu":
            return _submenu(spec, session, block, text, store, now, rng)
        if block.type == "quiz":
            return _quiz(spec, session, block, text, store, now)
        if block.type == "anon_chat":
            return _anon(spec, session, block, text, now)
    except (StopIteration, IndexError, KeyError) as e:
        # The saved state belongs to an older version of the bot (the owner republished mid-conversation:
        # a block, field, slot or option it points to is gone). Never leave the customer in silence.
        STALE_RESETS["count"] += 1
        log.warning("stale chat state reset (%s: %s)", type(e).__name__, e)
        _reset(session)
        return [menu_actions(spec, "ربات به‌تازگی به‌روزرسانی شده است؛ لطفاً از منوی زیر دوباره شروع کنید:")]
    _reset(session)
    return [menu_actions(spec)]


# ---------- menu ----------
def message_actions(block, session, rng, tail, now=None) -> list[dict]:
    """A message block: its text (or a random variant) with «open now» from its hours, then the attached photo/file or album,
    the map pin and the contact card if it has them, then `tail`."""
    text = pick_text(block, session, rng)
    if block.hours:
        text += "\n\n" + open_status(block.hours, now or dates.now_tehran())
    out = [send(text, [_btn(link.label, "url:" + link.url) for link in block.links])]
    if block.media == "album":
        out += [{"type": "media", "block": album_key(block.id, k), "kind": "image"} for k in range(block.album_size)]
    elif block.media != "none":
        out.append({"type": "media", "block": block.id, "kind": block.media})
    if block.location is not None:
        out.append({"type": "location", "latitude": block.location.latitude, "longitude": block.location.longitude})
    if block.contact is not None:
        out.append({"type": "contact", "phone": norm(block.contact.phone).replace(" ", "").replace("-", ""), "name": block.contact.name})
    return [*out, tail]


def album_key(block_id: str, k: int) -> str:
    return f"{block_id}@{k + 1}"


def quiz_media_key(block_id: str, i: int) -> str:
    return f"{block_id}~{i + 1}"


def _from_menu(spec, session, text_n, store, now, rng=_RNG):
    for pos, (key, label) in enumerate(builtin_entries(spec)):
        if text_n in (f"m:{len(spec.menu) + pos}", label):
            return _my_start(spec, session, store, now) if key == "mine" else _codes_view(spec, session, store)
    item = None
    m = re.fullmatch(r"m:(\d+)", text_n)
    if m and int(m.group(1)) < len(spec.menu):
        item = spec.menu[int(m.group(1))]
    else:
        item = next((i for i in spec.menu if i.label == text_n), None)
    if item is None:
        return [menu_actions(spec, "متوجه نشدم. لطفاً یکی از گزینه‌های منو را انتخاب کنید:")]
    return _start_block(spec, session, spec.block(item.block), store, now, rng)


def _start_block(spec, session, block, store, now, rng):
    """Begin a block (reached from the main menu or from a sub-menu)."""
    if block.type == "message":
        return message_actions(block, session, rng, menu_actions(spec), now)
    session.update(block=block.id, step=0, data={})
    if block.type == "referral":
        _reset(session)
        return _referral(spec, session, block)
    if block.type == "anon_chat":
        session["step"] = "idle"
        return [send(block.title), send(block.intro_text, _anon_find_buttons(block))]
    if block.type == "menu":
        session["step"] = "pick"
        return [_submenu_prompt(block)]
    if block.type == "quiz":
        if block.one_attempt and session.get("cust"):
            prev = store.find(block.id, _cust=session["cust"])
            if prev:
                _reset(session)
                was = f"نتیجه‌ی شما: {prev[0].get('result', '')}" if block.personality else _fill(block.result_text, prev[0])
                return [send("شما قبلاً در این آزمون شرکت کرده‌اید.\n" + was), menu_actions(spec)]
        order = list(range(len(block.questions)))
        if block.shuffle or block.pick:  # Fisher-Yates with the injectable generator (deterministic in the agent's tests)
            for k in range(len(order) - 1, 0, -1):
                j = rng.randrange(k + 1)
                order[k], order[j] = order[j], order[k]
        session["data"] = {"score": 0, "order": order[:block.pick] if block.pick else order}
        return [send(block.title), *_quiz_ask(block, session["data"], 0)]
    if block.type == "form":
        why = _form_closed(block, session, store, now)
        if why:
            _reset(session)
            return [send(why), menu_actions(spec)]
        return [send(block.title), *_first_question(spec, session, store, block.fields)]
    if block.type == "faq":
        return _faq_start(session, block)
    if block.type == "feedback":
        session.update(block=block.id, step="rate", data={})
        if block.aspects:
            return [send(block.title), send(block.prompt_text), _rate_prompt(block, block.aspects[0])]
        return [send(block.title), _rate_prompt(block)]
    if block.type == "contact":
        session.update(block=block.id, step="topic" if block.topics else "msg", data={})
        if block.topics:
            return [send(block.title), _topic_prompt(block)]
        return [send(block.title), send(block.prompt_text, _faq_nav())]
    if block.type == "booking" and block.no_show_limit and session.get("cust"):
        missed = sum(1 for r in store.find(block.id, _cust=session["cust"]) if r.get("status") == "no_show")
        if missed >= block.no_show_limit:
            _reset(session)
            return [send(fa_digits(f"به دلیل {missed} بار حاضر نشدن در نوبت، رزرو آنلاین برای شما فعال نیست. لطفاً برای گرفتن نوبت با ما تماس بگیرید.")), menu_actions(spec)]
    if block.type == "booking" and block.max_active_per_customer and session.get("cust"):
        n = sum(1 for r in store.find(block.id, _cust=session["cust"]) if _active(block, r, now))
        if n >= block.max_active_per_customer:
            _reset(session)
            hint = f" برای نوبت تازه، ابتدا یکی را از «{my_label(spec)}» لغو کنید." if block.allow_cancel else ""
            return [send(fa_digits(f"شما در حال حاضر {n} نوبت فعال دارید و بیش از این ممکن نیست.") + hint), menu_actions(spec)]
    if block.type == "booking" and block.schedule:
        return _appt_start(spec, session, block, store, now)
    if block.type == "booking":
        session["step"] = "slot"
        return [send(block.title), _slot_prompt(block, store, now)]
    if block.type == "catalog_order":
        return _order_start(spec, session, block, store, now)
    return [menu_actions(spec)]


# ---------- form ----------
def _fill(text: str, data: dict) -> str:
    """Put the customer's own answers into a confirmation text ({name} -> what they typed)."""
    return PLACEHOLDER.sub(lambda m: str(data.get(m.group(1), m.group(0))), text)


def _form(spec, session, block: FormBlock, text, store, now):
    if session["step"] == "confirm":
        t = norm(text)
        if t == "fc:redo":
            session.update(step=0, data={})
            return [send("از اول شروع می‌کنیم."), _ask(block.fields[0])]
        if t != "fc:yes":
            return [_form_review(block, session["data"])]
        return _form_save(spec, session, block, store, now)
    done, actions = _field_step(session, block.fields, text)
    if not done:
        return actions
    if block.confirm_before_submit:
        session["step"] = "confirm"
        return [_form_review(block, session["data"])]
    return _form_save(spec, session, block, store, now)


def _form_review(block: FormBlock, d: dict):
    lines = [f"{f.label.rstrip('؟?:')}: {d[f.key] if d[f.key] != '' else '—'}" for f in block.fields if f.key in d]
    return send("لطفاً اطلاعات را بررسی کنید:\n" + "\n".join(lines), [_btn("✅ تأیید و ثبت", "fc:yes"), _btn("✏️ از اول", "fc:redo")])


def _form_closed(block: FormBlock, session, store, now) -> str | None:
    """Why this customer cannot fill the form now (deadline, capacity, already submitted), or None."""
    if block.closes_on:
        last = jalali_date(block.closes_on)
        if last and now.date() > last:
            return block.closed_text
    if block.max_submissions and store.count(block.id) >= block.max_submissions:
        return block.closed_text
    if block.one_per_customer and session.get("cust") and store.find(block.id, _cust=session["cust"]):
        return block.already_text
    return None


def _form_save(spec, session, block: FormBlock, store, now):
    why = _form_closed(block, session, store, now)  # the last place may have gone while this customer was typing
    if why:
        _reset(session)
        return [send(why), menu_actions(spec)]
    d = session["data"]
    extra: dict = {}
    if block.review:
        extra["status"] = "received"
    score = _score(block, d)
    if score is not None:
        extra["score"] = score
    if d.get("_files"):
        extra["_files"] = d["_files"]
    row = store.add(block.id, {**{k: v for k, v in d.items() if not k.startswith("_")}, **extra, **_ident(session, now)})
    actions = [send(_fill(block.done_text, row))]
    hot = bool(block.hot_score and score is not None and score >= block.hot_score)
    _notify(spec, block.id, _summary(row), actions, prefix=f"🔥 مشتری داغ (امتیاز {score}) · {block.title}" if hot else None)
    for key, f in (d.get("_files") or {}).items():  # the files themselves, straight into the owner's chat
        label = next((x.label for x in block.fields if x.key == key), key)
        actions.append({"type": "notify_admin", "text": f"📎 {label} · ثبت #{row['id']} ({row.get('name', '') or block.title})",
                        "photo" if f.get("photo") else "document": f["id"]})
    _reset(session)
    actions.append(menu_actions(spec))
    return actions


def _score(block: FormBlock, d: dict) -> int | None:
    """Lead score: the points of the chosen answers (None when the form has no scored questions)."""
    scored = [f for f in block.fields if f.scores]
    if not scored:
        return None
    total = 0
    for f in scored:
        given = {p.strip() for p in str(d.get(f.key, "")).split("،")}
        total += sum(s for c, s in zip(f.choices, f.scores) if c in given)
    return total


def set_form_status(store, now, b, r: dict, status: str, note: str = "") -> list[dict]:
    """The owner's decision on an application/request; the customer is told in the bot (with the owner's note)."""
    if b.type != "form" or not b.review:
        raise ValueError("برای این فرم، بررسی و پاسخ فعال نیست.")
    if status not in FORM_DECISIONS:
        raise ValueError("وضعیت نامعتبر است.")
    if r.get("status") in ("accepted", "rejected"):
        raise ValueError("درباره‌ی این درخواست قبلاً تصمیم گرفته شده است.")
    store.update(b.id, r["id"], status=status, **{f"_{status}_at": now.isoformat()}, **({"owner_note": note.strip()} if note.strip() else {}))
    if not r.get("_cust"):
        return []
    text = f"درباره‌ی «{b.title}» (شماره‌ی {r['id']}):\n{FORM_DECISIONS[status]}" + (f"\n{note.strip()}" if note.strip() else "")
    return [{"type": "notify_customer", "cust": r["_cust"], "text": text}]


# ---------- booking ----------
def _remaining(block: BookingBlock, slot, store, day=None):
    """Free places. A weekly slot is counted per date (so it resets by itself); a one-off slot counts for ever."""
    where = {"slot": slot.id}
    if day is not None:
        where["date"] = day.isoformat()
    # a booking waiting for its deposit holds its place until it is paid or expires
    return slot.capacity - sum(_party(r) for r in store.find(block.id, **where) if r.get("status") in ("confirmed", "awaiting_payment"))


def _party(r: dict) -> int:
    """Places one booking takes: its group size (bookings made before max_party existed count as 1)."""
    return int(r.get("party") or 1)


def _closed_days(block: BookingBlock) -> set:
    return {d for d in (jalali_date(x) for x in block.closed_dates) if d}


def _starts_ok(block: BookingBlock, day: date, hhmm: str | None, now) -> bool:
    """A dated start far enough ahead for min_notice_hours (and not on a closed day)."""
    if day in _closed_days(block):
        return False
    if not hhmm:
        return True
    start = datetime.combine(day, time(int(hhmm[:2]), int(hhmm[3:])), tzinfo=now.tzinfo)
    return start > now and start >= now + timedelta(hours=block.min_notice_hours)


def _options(block: BookingBlock, now, store=None):
    """Everything the customer can pick right now: (slot, date-or-None, button data, display name).
    A weekly session is skipped on closed days, too soon (min notice), or when it starts inside hours the owner closed."""
    out = []
    for s in block.slots:
        days = [d for d in dates.next_occurrences(now, s.weekday, s.time, block.occurrences + 8)
                if _starts_ok(block, d, s.time, now) and not (store is not None and _off(store, block, d, _hm(s.time), _hm(s.time) + 1))][:block.occurrences] \
            if s.weekday is not None else [None]
        for day in days:
            name = s.label + (f" — {dates.jalali_str(day)}" if day else "")
            out.append((s, day, f"s:{s.id}" + (f"@{day:%Y%m%d}" if day else ""), name))
    return out


def _slot_prompt(block: BookingBlock, store, now):
    buttons = []
    for s, day, data, name in _options(block, now, store):
        left = _remaining(block, s, store, day)
        name += f" · {s.price:,} تومان" if s.price else ""
        if left > 0:
            buttons.append(_btn(f"{name} ({left} جای خالی)", data))
        elif block.waitlist:
            buttons.append(_btn(f"{name} (تکمیل - لیست انتظار)", data))
        else:
            buttons.append(_btn(f"{name} (تکمیل)", data))
    return send("زمان مورد نظر را انتخاب کنید:", buttons + [_btn("بازگشت به منو", "/menu")])


def _booking(spec, session, block: BookingBlock, text, store, now):
    text_n = norm(text)
    if block.schedule:
        return _appt(spec, session, block, text, store, now)
    if session["step"] == "weeks":
        return _weeks_step(spec, session, block, text_n, store, now)
    if session["step"] == "party":
        d = session["data"]
        m = re.fullmatch(r"(?:pz:)?(\d+)", text_n)
        n = int(m.group(1)) if m else 0
        if not 1 <= n <= block.max_party:
            return [send(fa_digits(f"لطفاً تعداد را بین ۱ و {block.max_party} انتخاب کنید.")), _party_prompt(block)]
        slot = next(s for s in block.slots if s.id == d["slot"])
        left = _remaining(block, slot, store, date.fromisoformat(d["date"]) if "date" in d else None)
        if left < n and not block.waitlist:
            session["step"] = "slot"
            return [send(fa_digits(f"برای {n} نفر جای کافی نیست؛ فقط {max(left, 0)} جای خالی مانده است.")), _slot_prompt(block, store, now)]
        d["party"] = n
        return _after_pick(spec, session, block, store, now)
    if session["step"] == "slot":
        opts = _options(block, now, store)
        # exact button data first; typed text may start with the display name or (for the nearest date) the bare label
        # (labels are compared in normalised form: text_n has ASCII digits, labels like «ساعت ۱۰» have Persian ones)
        pick = next((o for o in opts if text_n == o[2]), None) or next((o for o in opts if text_n.startswith(norm(o[3]))), None) \
            or next((o for o in opts if text_n.startswith(norm(o[0].label))), None)
        if pick is None:
            return [send("لطفاً یکی از زمان‌ها را انتخاب کنید."), _slot_prompt(block, store, now)]
        slot, day, _, name = pick
        if _remaining(block, slot, store, day) <= 0 and (not block.waitlist or session["data"].get("_replace")):
            return [send(block.full_text), _slot_prompt(block, store, now)]  # moving to a full date would lose the customer's place
        session["data"]["slot"] = slot.id
        session["data"]["slot_label"] = name
        if day is not None:
            session["data"]["date"] = day.isoformat()
        if block.max_party > 1 and not session["data"].get("_replace"):
            session["step"] = "party"
            return [_party_prompt(block)]
        return _after_pick(spec, session, block, store, now)
    done, actions = _field_step(session, block.fields, text)
    if not done:
        return actions
    return _commit_slot(spec, session, block, store, now)


def _party_prompt(block: BookingBlock):
    return send("چند نفر هستید؟", [_btn(str(i), f"pz:{i}") for i in range(1, min(block.max_party, 10) + 1)])


def _commit_slot(spec, session, block: BookingBlock, store, now):
    slot = next(s for s in block.slots if s.id == session["data"]["slot"])
    day = date.fromisoformat(session["data"]["date"]) if "date" in session["data"] else None
    # re-check capacity at commit time (another customer may have taken the last place meanwhile)
    full = _remaining(block, slot, store, day) < _party(session["data"])
    if full and not block.waitlist:
        _reset(session)
        return [send(block.full_text), menu_actions(spec)]
    if full and session["data"].get("_replace"):  # the date filled up while the customer was choosing: keep the old place
        session["step"] = "slot"
        return [send(block.full_text), _slot_prompt(block, store, now)]
    if not full and _deposit_due(block, session):
        return _await_deposit(spec, session, block, store, now)
    status = "waitlisted" if full else "confirmed"
    row = store.add(block.id, {**session["data"], "status": status, **_ident(session, now)})
    more = _series(spec, block, store, now, row)
    return _finish_booking(spec, session, block, store, now, row, status, (block.waitlist_text if full else block.confirm_text) + more + _deposit_note(block, session["data"]))


def _finish_booking(spec, session, block, store, now, row, status, text):
    """Confirmation + owner notice; for a reschedule the old booking is released only now that the new place is certain."""
    actions = [send(_fill(text, row))]
    old_id = session["data"].get("_replace")
    if old_id and status == "confirmed":
        old = next(iter(store.find(block.id, id=old_id)), None)
        if old and old.get("status") in ("confirmed", "waitlisted"):
            more, _ = cancel_record(spec, store, now, block, old, by="customer")
            actions += more
            actions.append(send(f"✅ زمان شما تغییر کرد؛ ثبت قبلی ({old.get('slot_label', block.title)}) لغو شد."))
    _notify(spec, block.id, f"[{status}] " + _summary(row) + ("\n(تغییر زمان توسط مشتری)" if old_id else ""), actions)
    actions += _staff_notice(row, f"📅 نوبت تازه برای شما · {block.title}\n{_summary(row)}")
    _reset(session)
    actions.append(menu_actions(spec))
    return actions


def _after_pick(spec, session, block: BookingBlock, store, now):
    """The customer chose the time. A reschedule reuses the contact details of the old booking and commits at once."""
    d = session["data"]
    old = next(iter(store.find(block.id, id=d["_replace"])), None) if d.get("_replace") else None
    if old:
        if (old.get("slot"), old.get("date"), old.get("time")) == (d.get("slot"), d.get("date"), d.get("time")):
            for k in ("slot", "slot_label", "date", "time"):
                d.pop(k, None)
            if block.schedule:
                return [send("این همان زمان فعلی شماست؛ زمان دیگری انتخاب کنید."), *_appt_day_prompt(spec, session, block, store, now)]
            session["step"] = "slot"
            return [send("این همان زمان فعلی شماست؛ زمان دیگری انتخاب کنید."), _slot_prompt(block, store, now)]
        for f in block.fields:
            if f.key in old:
                d[f.key] = old[f.key]
        if old.get("party"):
            d["party"] = old["party"]
        if old.get("paid"):  # the deposit travels with the booking: never charged twice
            d.update(paid=True, total=old.get("total"))
        return _commit_appt(spec, session, block, store, now) if block.schedule else _commit_slot(spec, session, block, store, now)
    if block.repeat_weeks > 1 and "_weeks" not in d and _weekly_pick(block, d):
        session["step"] = "weeks"
        return [_weeks_prompt(block)]
    return _first_question(spec, session, store, block.fields)


def _weekly_pick(block: BookingBlock, d: dict) -> bool:
    """A dated pick that repeats every week: an appointment, or a weekly class session."""
    if block.schedule:
        return True
    slot = next((s for s in block.slots if s.id == d.get("slot")), None)
    return bool(slot and slot.weekday is not None and d.get("date"))


def _weeks_prompt(block: BookingBlock):
    return send("چند هفته پشت سر هم رزرو شود؟", [_btn("فقط همین جلسه" if n == 1 else f"{n} هفته", f"rw:{n}") for n in range(1, min(block.repeat_weeks, 8) + 1)])


def _weeks_step(spec, session, block, text_n, store, now):
    m = re.fullmatch(r"(?:rw:)?(\d+)", text_n)
    n = int(m.group(1)) if m else 0
    if not 1 <= n <= block.repeat_weeks:
        return [send(fa_digits(f"لطفاً عددی بین ۱ و {block.repeat_weeks} انتخاب کنید.")), _weeks_prompt(block)]
    session["data"]["_weeks"] = n
    return _after_pick(spec, session, block, store, now)


def _series(spec, block: BookingBlock, store, now, row: dict) -> str:
    """Book the following weeks of a repeating booking at the same time (and staff/service), where there is room.
    Returns the lines that tell the customer which weeks were booked and which were not."""
    weeks = int(row.get("_weeks") or 1)
    if weeks <= 1 or row.get("status") != "confirmed":
        return ""
    first = date.fromisoformat(row["date"])
    slot = next((s for s in block.slots if s.id == row.get("slot")), None)
    got, missed = [], []
    for k in range(1, weeks):
        day = first + timedelta(weeks=k)
        when = dates.jalali_str(day)
        if block.schedule:
            hhmm, dur, staff = row["time"], row.get("_dur") or block.schedule.duration_minutes, row.get("staff", "")
            ok = (hhmm in _appt_times(block, day, now, row.get("_dur"), staff) and not _off(store, block, day, _hm(hhmm), _hm(hhmm) + dur, staff)
                  and _appt_free(block, store, staff, day, hhmm, row.get("_dur")) > 0)
            label = _appt_label(day, hhmm, staff, row.get("service", ""))
        else:
            ok = (_starts_ok(block, day, slot.time, now) and not _off(store, block, day, _hm(slot.time), _hm(slot.time) + 1)
                  and _remaining(block, slot, store, day) >= _party(row))
            label = f"{slot.label} — {when}"
        if not ok:
            missed.append(when)
            continue
        data = {k2: v for k2, v in row.items() if k2 not in ("id", "_weeks")}
        store.add(block.id, {**data, "date": day.isoformat(), "slot_label": label, "_series": row["id"]})
        got.append(when)
    store.update(block.id, row["id"], _series=row["id"])
    out = f"\nجلسه‌های بعدی هم رزرو شد: {'، '.join(got)}" if got else ""
    if missed:
        out += f"\nاین هفته‌ها جای خالی نداشت و رزرو نشد: {'، '.join(missed)}"
    return fa_digits(out)


# ---------- appointments generated from working hours (booking block with a `schedule`) ----------
PAGE_TIMES = 8


def _hm(t: str) -> int:
    return int(t[:2]) * 60 + int(t[3:])


def _fmt(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _days_for(sch, staff: str):
    """A staff member's own working days (staff_hours), or the schedule's."""
    return next((h.days for h in sch.staff_hours if h.staff == staff), sch.days)


def _appt_times(block: BookingBlock, day: date, now, dur: int | None = None, staff: str = "") -> list[str]:
    """Every start time of that day (on the schedule's grid) where an appointment of `dur` minutes fits the working
    hours (that staff member's own, if set), misses the daily break, and starts far enough ahead; none on a closed day."""
    sch, out = block.schedule, []
    dur = dur or sch.duration_minutes
    for w in _days_for(sch, staff):
        if w.weekday != dates.persian_weekday(day):
            continue
        t = _hm(w.start)
        while t + dur <= _hm(w.end):
            in_break = sch.break_start and t < _hm(sch.break_end) and t + dur > _hm(sch.break_start)
            if not in_break and _starts_ok(block, day, _fmt(t), now):
                out.append(_fmt(t))
            t += sch.duration_minutes
    return out


def _appt_free(block: BookingBlock, store, staff: str, day: date, hhmm: str, dur: int | None = None) -> int:
    """Places left for an appointment [hhmm, hhmm+dur): capacity minus the most bookings running at once inside it
    (bookings last their own service length). With one fixed length this is simply «bookings at that time»."""
    sch = block.schedule
    dur = dur or sch.duration_minutes
    where = {"slot": "appt", "date": day.isoformat()}
    if staff:
        where["staff"] = staff
    booked = [(_hm(r["time"]), _hm(r["time"]) + int(r.get("_dur") or sch.duration_minutes)) for r in store.find(block.id, **where)
              if r.get("status") in ("confirmed", "awaiting_payment")]
    t0, t1 = _hm(hhmm), _hm(hhmm) + dur
    points = [t0] + [s for s, _ in booked if t0 < s < t1]
    busiest = max(sum(1 for s, e in booked if s <= p < e) for p in points)
    return sch.capacity - busiest


def _off(store, block, day: date, start: int, end: int, staff: str = "") -> bool:
    """Does [start, end) on that day overlap hours the owner closed (for everyone, or for this staff member)?"""
    return any(o["date"] == day.isoformat() and (not o.get("staff") or o["staff"] == staff) and start < _hm(o["end"]) and end > _hm(o["start"])
               for o in getattr(store, "time_off", lambda _b: [])(block.id))


def _appt_free_times(block, store, staff, day, now, dur=None) -> list[str]:
    length = dur or block.schedule.duration_minutes
    return [t for t in _appt_times(block, day, now, dur, staff)
            if not _off(store, block, day, _hm(t), _hm(t) + length, staff) and _appt_free(block, store, staff, day, t, dur) > 0]


def _appt_days(block, store, staff, now, dur=None) -> list[tuple[date, int]]:
    out = []
    for i in range(block.schedule.days_ahead + 1):
        day = now.date() + timedelta(days=i)
        n = len(_appt_free_times(block, store, staff, day, now, dur))
        if n:
            out.append((day, n))
    return out


def _appt_label(day: date, hhmm: str | None = None, staff: str = "", service: str = "") -> str:
    base = f"{dates.WEEKDAYS[dates.persian_weekday(day)]} {dates.jalali_str(day)}" + (f" ساعت {hhmm}" if hhmm else "")
    return base + (f" — {service}" if service else "") + (f" — {staff}" if staff else "")


def _service_prompt(block: BookingBlock):
    return send("کدام خدمت را می‌خواهید؟", [_btn(f"{s.name} — {s.duration_minutes} دقیقه" + (f" — {s.price:,} تومان" if s.price else ""), f"sv:{i}")
                                         for i, s in enumerate(block.schedule.services)] + [_btn("بازگشت به منو", "/menu")])


def _allowed_staff(block: BookingBlock, d: dict) -> list[str]:
    """The staff who can take this booking: those who do the chosen service, or everyone."""
    sv = next((s for s in block.schedule.services if s.name == d.get("service")), None)
    return [n for n in block.schedule.staff if not sv or not sv.staff or n in sv.staff]


def _staff_prompt(block: BookingBlock, d: dict | None = None):
    allowed = _allowed_staff(block, d or {})
    return send("با چه کسی؟", [_btn(n, f"f:{i}") for i, n in enumerate(block.schedule.staff) if n in allowed] + [_btn("بازگشت به منو", "/menu")])


def _appt_start(spec, session, block, store, now):
    session.update(block=block.id, step="day", data={})
    if block.schedule.services:
        session["step"] = "service"
        return [send(block.title), _service_prompt(block)]
    if block.schedule.staff:
        session["step"] = "staff"
        return [send(block.title), _staff_prompt(block)]
    return _appt_day_prompt(spec, session, block, store, now, [send(block.title)])


def _appt_day_prompt(spec, session, block, store, now, head=()):
    staff = session["data"].get("staff", "")
    days = _appt_days(block, store, staff, now, session["data"].get("_dur"))
    if not days:
        _reset(session)
        return [*head, send("در حال حاضر نوبت خالی وجود ندارد. لطفاً بعداً دوباره سر بزنید."), menu_actions(spec)]
    session["step"] = "day"
    buttons = [_btn(f"{_appt_label(d)} ({n} نوبت خالی)", f"d:{d:%Y%m%d}") for d, n in days]
    return [*head, send("روز مورد نظر را انتخاب کنید:", buttons + [_btn("بازگشت به منو", "/menu")])]


def _appt_time_prompt(block, store, session, now, page=0, edit=False):
    d = session["data"]
    day = date.fromisoformat(d["date"])
    times = _appt_free_times(block, store, d.get("staff", ""), day, now, d.get("_dur"))
    pages = max(1, math.ceil(len(times) / PAGE_TIMES))
    page = min(max(page, 0), pages - 1)
    buttons = [_btn(t, f"t:{t.replace(':', '')}") for t in times[page * PAGE_TIMES:(page + 1) * PAGE_TIMES]]
    if page > 0:
        buttons.append(_btn("‹ قبلی", f"tp:{page - 1}"))
    if page + 1 < pages:
        buttons.append(_btn("بعدی ›", f"tp:{page + 1}"))
    buttons.append(_btn("بازگشت به انتخاب روز", "back"))
    buttons.append(_btn("بازگشت به منو", "/menu"))
    session["step"] = "time"
    head = f"ساعت مورد نظر برای {_appt_label(day, None, d.get('staff', ''))}" + (f" — صفحه {page + 1} از {pages}" if pages > 1 else "") + ":"
    return send(head, buttons, edit)


def _appt(spec, session, block: BookingBlock, text, store, now):
    text_n = norm(text)
    d = session["data"]
    step = session["step"]
    sch = block.schedule

    if step == "weeks":
        return _weeks_step(spec, session, block, text_n, store, now)

    if step == "service":
        m = re.fullmatch(r"sv:(\d+)", text_n)
        idx = int(m.group(1)) if m else next((i for i, s in enumerate(sch.services) if text_n.startswith(fa_norm(s.name))), -1)
        if not 0 <= idx < len(sch.services):
            return [send("لطفاً یکی از خدمت‌ها را انتخاب کنید."), _service_prompt(block)]
        sv = sch.services[idx]
        d.update(service=sv.name, _dur=sv.duration_minutes)
        if sv.price:
            d["price"] = sv.price
        allowed = _allowed_staff(block, d)
        if len(allowed) == 1 and sch.staff:  # only one person does this service: no question
            d["staff"] = allowed[0]
        elif sch.staff:
            session["step"] = "staff"
            return [_staff_prompt(block, d)]
        return _appt_day_prompt(spec, session, block, store, now)

    if step == "staff":
        m = re.fullmatch(r"f:(\d+)", text_n)
        idx = int(m.group(1)) if m else next((i for i, n in enumerate(sch.staff) if fa_norm(n) == fa_norm(text_n)), -1)
        if not 0 <= idx < len(sch.staff) or sch.staff[idx] not in _allowed_staff(block, d):
            return [send("لطفاً یکی از گزینه‌ها را انتخاب کنید."), _staff_prompt(block, d)]
        d["staff"] = sch.staff[idx]
        return _appt_day_prompt(spec, session, block, store, now)

    if step == "day":
        m = re.fullmatch(r"d:(\d{8})", text_n)
        offered = {f"{x:%Y%m%d}": x for x, _ in _appt_days(block, store, d.get("staff", ""), now, d.get("_dur"))}
        if not m or m.group(1) not in offered:
            return _appt_day_prompt(spec, session, block, store, now, [send("لطفاً یکی از روزها را انتخاب کنید.")])
        d["date"] = offered[m.group(1)].isoformat()
        return [_appt_time_prompt(block, store, session, now)]

    if step == "time":
        if text_n == "back":
            d.pop("date", None)
            return _appt_day_prompt(spec, session, block, store, now)
        mp = re.fullmatch(r"tp:(\d+)", text_n)
        if mp:
            return [_appt_time_prompt(block, store, session, now, int(mp.group(1)), edit=True)]
        mt = re.fullmatch(r"t:(\d{4})", text_n)
        day = date.fromisoformat(d["date"])
        hhmm = f"{mt.group(1)[:2]}:{mt.group(1)[2:]}" if mt else None
        if not hhmm or hhmm not in _appt_free_times(block, store, d.get("staff", ""), day, now, d.get("_dur")):
            return [send("این ساعت دیگر خالی نیست. لطفاً ساعت دیگری انتخاب کنید."), _appt_time_prompt(block, store, session, now)]
        d["time"] = hhmm
        d["slot"] = "appt"
        d["slot_label"] = _appt_label(day, hhmm, d.get("staff", ""), d.get("service", ""))
        return _after_pick(spec, session, block, store, now)

    # contact fields
    done, actions = _field_step(session, block.fields, text)
    if not done:
        return actions
    return _commit_appt(spec, session, block, store, now)


def _commit_appt(spec, session, block: BookingBlock, store, now):
    d = session["data"]
    day = date.fromisoformat(d["date"])
    if _appt_free(block, store, d.get("staff", ""), day, d["time"], d.get("_dur")) <= 0:  # someone took it while this customer was typing
        d.pop("time", None)
        return [send(block.full_text), _appt_time_prompt(block, store, session, now)]
    if _deposit_due(block, session):
        return _await_deposit(spec, session, block, store, now)
    row = store.add(block.id, {**d, "status": "confirmed", **_ident(session, now)})
    more = _series(spec, block, store, now, row)
    return _finish_booking(spec, session, block, store, now, row, "confirmed", block.confirm_text + more + _deposit_note(block, d))


# ---------- catalog order (inline menu, or products from the database table) ----------
PAGE = 5


def _is_table(block: CatalogOrderBlock) -> bool:
    return block.source == "table"


def _item_prompt(block: CatalogOrderBlock):
    return send("آیتم مورد نظر را انتخاب کنید:", [_btn(f"{i.name} - {i.price:,} تومان", f"i:{i.id}") for i in block.items])


def _short(text: str, n: int = 38) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _cat_prompt(block, store, edit=False):
    buttons = [_btn(_short(c), f"c:{i}") for i, c in enumerate(store.categories(block.id))]
    buttons += [_btn("همه‌ی محصولات", "all"), _btn("🔎 جستجو", "search")]
    return send("دسته‌بندی را انتخاب کنید:", buttons, edit)


def _list_prompt(block, store, d, edit=False):
    cats = store.categories(block.id)
    cat, q, page = d.get("_cat"), d.get("_q"), d.get("_page", 0)
    items, total = store.products(block.id, cat, q, page * PAGE, PAGE)
    back = [_btn("بازگشت به دسته‌ها", "back")] if len(cats) > 1 else []
    if total == 0:
        return send("محصولی پیدا نشد.", [_btn("🔎 جستجوی دیگر", "search")] + back, edit)
    pages = math.ceil(total / PAGE)
    if not items:  # page out of range -> last page
        page = pages - 1
        items, _ = store.products(block.id, cat, q, page * PAGE, PAGE)
    d["_page"] = page
    head = f"نتیجه‌ی جستجو برای «{q}»" if q else (cat or "همه‌ی محصولات")
    buttons = [_btn(f"{_short(p['name'])} - {p['price']:,} تومان", f"p:{p['id']}") for p in items]
    if page > 0:
        buttons.append(_btn("‹ قبلی", f"pg:{page - 1}"))
    if page + 1 < pages:
        buttons.append(_btn("بعدی ›", f"pg:{page + 1}"))
    buttons += [_btn("🔎 جستجو", "search")] + back
    return send(f"{head} — صفحه {page + 1} از {pages}", buttons, edit)


def _within(days, now) -> bool:
    """Is `now` inside one of these weekly hours ({weekday, start, end})?"""
    wd, m = dates.persian_weekday(now.date()), now.hour * 60 + now.minute
    return any(w.weekday == wd and _hm(w.start) <= m < _hm(w.end) for w in days)


def _hours_text(days) -> str:
    return "؛ ".join(f"{dates.WEEKDAYS[w.weekday]} {fa_digits(w.start)} تا {fa_digits(w.end)}" for w in sorted(days, key=lambda w: (w.weekday, w.start)))


def open_status(days, now) -> str:
    """«🟢 الان باز هستیم (تا ۲۲:۰۰)» or «🔴 الان بسته‌ایم؛ از فردا ساعت ۸:۰۰ باز هستیم»."""
    wd, m = dates.persian_weekday(now.date()), now.hour * 60 + now.minute
    here = [w for w in days if w.weekday == wd and _hm(w.start) <= m < _hm(w.end)]
    if here:
        return fa_digits(f"🟢 الان باز هستیم (تا {max(w.end for w in here)})")
    for k in range(0, 8):  # the next opening, today included
        day_wd = (wd + k) % 7
        starts = sorted(w.start for w in days if w.weekday == day_wd and (k > 0 or _hm(w.start) > m))
        if starts:
            when = "امروز" if k == 0 else "فردا" if k == 1 else dates.WEEKDAYS[day_wd]
            return fa_digits(f"🔴 الان بسته‌ایم؛ {when} از ساعت {starts[0]} باز هستیم.")
    return "🔴 الان بسته‌ایم."


def _open_now(block: CatalogOrderBlock, now, session=None) -> bool:
    if not block.order_hours or (session or {}).get("test"):
        return True
    return _within(block.order_hours, now)


def _closed_msg(block: CatalogOrderBlock) -> str:
    return f"{block.closed_text}\nساعت سفارش‌گیری: {_hours_text(block.order_hours)}"


def _order_start(spec, session, block: CatalogOrderBlock, store, now):
    if not _open_now(block, now, session):
        _reset(session)
        return [send(block.title), send(_closed_msg(block)), menu_actions(spec)]
    d: dict = {"_cart": []}
    session.update(block=block.id, step="item", data=d)
    again = _repeat_offer(block, store, session)
    if not _is_table(block):
        return [send(block.title), *again, _item_prompt(block)]
    if store.products(block.id, None, None, 0, 1)[1] == 0:
        _reset(session)
        return [send(block.title), send("فعلاً محصولی ثبت نشده است."), menu_actions(spec)]
    if len(store.categories(block.id)) > 1:
        session["step"] = "cat"
        return [send(block.title), *again, _cat_prompt(block, store)]
    session["step"], d["_page"] = "list", 0
    return [send(block.title), *again, _list_prompt(block, store, d)]


def _cart_total(cart):
    return sum(c["price"] * c.get("qty", 1) for c in cart)


def _price(block: CatalogOrderBlock, subtotal: int, code, zone=None) -> dict:
    """goods - discount + delivery. The delivery fee is the chosen zone's, or the block's single fee; it is free once
    the goods total AFTER the discount reaches free_delivery_over."""
    disc = 0
    if code is not None:
        disc = min(subtotal, round(subtotal * code.percent / 100) if code.percent else code.amount)
    goods = subtotal - disc
    base = zone.fee if zone is not None else block.delivery_fee
    fee = 0 if (block.free_delivery_over and goods >= block.free_delivery_over) else base
    return {"subtotal": subtotal, "discount": disc, "delivery_fee": fee, "total": goods + fee}


def _code_error(block: CatalogOrderBlock, store, subtotal: int, code) -> str | None:
    if code is None:
        return "این کد تخفیف معتبر نیست."
    if code.min_total and subtotal < code.min_total:
        return f"این کد برای سفارش‌های حداقل {code.min_total:,} تومان است."
    if code.max_uses:
        used = sum(1 for r in store.find(block.id) if norm_code(fa_norm(str(r.get("discount_code") or ""))) == norm_code(fa_norm(code.code)) and r.get("status") != "cancelled")
        if used >= code.max_uses:
            return "ظرفیت استفاده از این کد تمام شده است."
    return None


def _find_code(block: CatalogOrderBlock, text: str):
    want = norm_code(fa_norm(text))
    return next((c for c in block.discount_codes if norm_code(fa_norm(c.code)) == want), None)


def _zone(block: CatalogOrderBlock, d: dict):
    i = d.get("_zone")
    return block.delivery_zones[i] if i is not None and 0 <= i < len(block.delivery_zones) else None


def _zone_prompt(block: CatalogOrderBlock):
    return send("محل ارسال را انتخاب کنید:", [_btn(f"{z.label} - {z.fee:,} تومان" if z.fee else f"{z.label} (ارسال رایگان)", f"z:{i}")
                                              for i, z in enumerate(block.delivery_zones)])


def _after_zone(spec, session, block: CatalogOrderBlock, store, now=None):
    """Checkout continues with the delivery time (when the block has windows), the discount code (when it has codes),
    then the contact questions."""
    if block.time_windows:
        now = now or dates.now_tehran()
        prompt = _window_prompt(block, store, now, session)
        if prompt is None:
            session["step"] = "more"
            return [_no_window(block), _more_prompt()]
        session["step"] = "when"
        return [prompt]
    return _after_window(spec, session, block, store)


def _code_uses(store, block: CatalogOrderBlock, code) -> int:
    return sum(1 for r in store.find(block.id) if norm_code(fa_norm(str(r.get("discount_code") or ""))) == norm_code(fa_norm(code.code)) and r.get("status") != "cancelled")


def _code_line(block, code, store) -> str | None:
    """One line describing a code for customers, or None when it can no longer be used."""
    left = None
    if code.max_uses:
        left = code.max_uses - _code_uses(store, block, code)
        if left <= 0:
            return None
    what = f"{code.percent}٪ تخفیف" if code.percent else f"{code.amount:,} تومان تخفیف"
    cond = f" · برای سفارش بالای {code.min_total:,} تومان" if code.min_total else ""
    rest = f" · {left} بار دیگر قابل استفاده است" if left is not None else ""
    return f"• {code.code} — {what}{cond}{rest}"


def _codes_view(spec, session, store):
    """The built-in «کدهای تخفیف» entry: every visible code that still works, and a way to start an order."""
    _reset(session)
    lines, jump = [], []
    for bi, ci, b, c in _visible_codes(spec):
        line = _code_line(b, c, store)
        if line:
            lines.append(line)
            if b.id not in [j[0] for j in jump]:
                jump.append((b.id, b.title))
    if not lines:
        return [send("فعلاً کد تخفیف فعالی نداریم."), menu_actions(spec)]
    text = "🎁 کدهای تخفیف فعال:\n" + "\n".join(lines) + "\n\nهنگام ثبت سفارش، کد را وارد کنید."
    return [send(text, [_btn("ثبت سفارش", f"go:{jump[0][0]}"), _btn("بازگشت به منو", "/menu")])]


def _code_prompt(block: CatalogOrderBlock | None = None):
    buttons = [_btn(f"🎁 {c.code}", f"dc:{i}") for i, c in enumerate(block.discount_codes) if c.visible][:6] if block is not None else []
    return send("کد تخفیف دارید؟ آن را بنویسید یا از کدهای زیر یکی را بزنید؛ وگرنه «ندارم» را بزنید." if buttons else "کد تخفیف دارید؟ آن را بنویسید، وگرنه «ندارم» را بزنید.", [*buttons, _btn("ندارم", "dc:no")])


def _more_prompt():
    return send("آیتم دیگری اضافه می‌کنید؟", [_btn("افزودن آیتم دیگر", "more"), _btn("🛒 سبد خرید", "cart"), _btn("ثبت سفارش", "checkout")])


def _line(c: dict) -> str:
    opts = " ".join(c.get("options", {}).values())
    return f"{c['name']}{' ' + opts if opts else ''}" + (f" × {c['qty']}" if "qty" in c else "")


def _cart_view(d: dict, edit=False):
    cart = d["_cart"]
    if not cart:
        return send("سبد سفارش خالی است.", [_btn("افزودن آیتم دیگر", "more")], edit)
    lines = [f"{i + 1}. {_line(c)} — {c['price'] * c.get('qty', 1):,} تومان" for i, c in enumerate(cart)]
    buttons = [_btn(f"❌ {_short(_line(c), 30)}", f"rm:{i}") for i, c in enumerate(cart)]
    return send("🛒 سبد خرید شما:\n" + "\n".join(lines) + f"\nجمع کالاها: {_cart_total(cart):,} تومان",
                buttons + [_btn("افزودن آیتم دیگر", "more"), _btn("ثبت سفارش", "checkout")], edit)


def _qty_prompt(pend):
    return send("تعداد را انتخاب کنید (یا عدد بنویسید):", [_btn(str(n), f"n:{n}") for n in (1, 2, 3)])


def _option_prompt(name, choices, prices):
    def extra(j):
        p = prices[j] if prices else 0
        return f" (+{p:,} تومان)" if p > 0 else (f" (−{-p:,} تومان)" if p < 0 else "")
    return send(name, [_btn(c + extra(j), c) for j, c in enumerate(choices)])


def _next_option(session, block):
    d = session["data"]
    groups = d["_pending"]["_groups"]
    i = d.get("_opt_idx", 0)
    if i < len(groups):
        session["step"] = "option"
        return [_option_prompt(*groups[i])]
    d.pop("_opt_idx", None)
    if _is_table(block) or block.ask_quantity:
        session["step"] = "qty"
        return [_qty_prompt(d["_pending"])]
    return _add_to_cart(session, block, 1)


def _add_to_cart(session, block, qty):
    d = session["data"]
    pend = d.pop("_pending")
    pend.pop("_groups", None)
    pend.pop("stock", None)
    if _is_table(block) or block.ask_quantity:
        pend["qty"] = qty
    session["step"] = "more"
    if len(d["_cart"]) + 1 > block.max_items:
        return [send(f"حداکثر {block.max_items} آیتم در هر سفارش مجاز است."), _more_prompt()]
    d["_cart"].append(pend)
    shown = f"«{pend['name']}»" + (f" × {qty}" if "qty" in pend else "")
    return [send(f"{shown} به سفارش اضافه شد."), _more_prompt()]


def _pick_product(session, block, store, pid):
    d = session["data"]
    p = store.product(block.id, pid)
    if p is None:
        return [send("این محصول دیگر موجود نیست."), _list_prompt(block, store, d)]
    in_cart = sum(c.get("qty", 1) for c in d.get("_cart", []) if c["id"] == p["id"])
    if p["stock"] is not None and p["stock"] <= 0:
        if block.restock_alerts and session.get("cust"):
            return [send(f"«{p['name']}» فعلاً موجود نیست. می‌خواهید وقتی موجود شد خبرتان کنیم؟",
                         [_btn("🔔 موجود شد خبرم کن", f"ns:{p['id']}")]), _list_prompt(block, store, d)]
        return [send(f"«{p['name']}» فعلاً موجود نیست."), _list_prompt(block, store, d)]
    if p["stock"] is not None and in_cart >= p["stock"]:
        return [send(f"همه‌ی موجودی «{p['name']}» ({p['stock']} عدد) همین الان در سبد شماست."), _list_prompt(block, store, d)]
    d["_pending"] = {"id": p["id"], "name": p["name"], "price": p["price"], "options": {}, "stock": p["stock"],
                     "_groups": [[o["name"], o["choices"], o.get("prices") or []] for o in p["options"] if o["choices"]]}
    d["_opt_idx"] = 0
    about = (p.get("description") or "").strip()
    photo = [{"type": "media", "block": f"product:{p['id']}", "kind": "image"}] if p.get("photo") else []
    head = [send(f"«{p['name']}» — {p['price']:,} تومان" + (f"\n{about}" if about else ""))] if about or photo else []  # what the product is, before its options
    return photo + head + _next_option(session, block)


def _restock_request(session, block, store, now, pid: int):
    """«موجود شد خبرم کن»: remembered once per customer and product; the scheduler sends the news when stock comes back."""
    p = store.product(block.id, pid)
    cust = session.get("cust")
    if p is None or not cust:
        return [send("این محصول دیگر در فهرست نیست.")]
    if p["stock"] is None or p["stock"] > 0:
        return [send(f"«{p['name']}» همین حالا موجود است.")]
    if not store.find(RESTOCK, _cust=cust, product=pid, status="waiting"):
        store.add(RESTOCK, {"block": block.id, "product": pid, "name": p["name"], "status": "waiting", **_ident(session, now)})
    return [send(f"✅ باشد؛ به محض موجود شدن «{p['name']}» خبرتان می‌کنیم.")]


RESTOCK = "_restock"  # internal collection: who wants to hear when a product is back


def restock_notices(spec: BotSpec, store, now) -> list[dict]:
    """Products that are back in stock: tell everyone who asked (once), with a button into the shop."""
    out: list[dict] = []
    for r in store.find(RESTOCK, status="waiting"):
        b = next((x for x in spec.blocks if x.id == r.get("block") and x.type == "catalog_order"), None)
        p = store.product(b.id, r["product"]) if b is not None else None
        if p is None:
            store.update(RESTOCK, r["id"], status="gone")
            continue
        if p["stock"] is not None and p["stock"] <= 0:
            continue
        store.update(RESTOCK, r["id"], status="sent", _sent_at=now.isoformat())
        if r.get("_cust"):
            out.append({"type": "notify_customer", "cust": r["_cust"], "text": f"🔔 «{p['name']}» دوباره موجود شد!",
                        "buttons": [_btn(f"🛍 {b.title}", f"go:{b.id}")]})
    return out


def _stock_alerts(block, store, cart) -> list[str]:
    """Before stock is taken for an order: the products this order brings down to the owner's low_stock_alert."""
    if not block.low_stock_alert or not _is_table(block):
        return []
    out = []
    for pid, qty in total_per_product([(c["id"], c.get("qty", 1)) for c in cart]).items():
        p = store.product(block.id, pid)
        if p is None or p["stock"] is None:
            continue
        before, after = p["stock"], p["stock"] - qty
        if after <= block.low_stock_alert < before or (after <= 0 < before):
            out.append(f"⚠️ موجودی «{p['name']}» تمام شد." if after <= 0 else f"⚠️ موجودی «{p['name']}» به {after} عدد رسید.")
    return out


# ---------- repeat the last order ----------
def _last_order(block, store, session) -> dict | None:
    cust = session.get("cust")
    if not block.repeat_order or not cust:
        return None
    rows = [r for r in store.find(block.id, _cust=cust) if r.get("items") and r.get("status") in ("new", "preparing", "ready", "done")]
    return max(rows, key=lambda r: r["id"]) if rows else None


def _repeat_offer(block, store, session):
    last = _last_order(block, store, session)
    if last is None:
        return []
    items = "، ".join(_line(c) for c in last["items"])
    return [send(f"سفارش قبلی شما: {_short(items, 120)}", [_btn("🔁 تکرار همین سفارش", "ro")])]


def _repeat(session, block, store):
    """Put the last order back in the cart at TODAY's prices; what is gone or out of stock is left out (and named)."""
    d = session["data"]
    last = _last_order(block, store, session)
    if last is None:
        return None
    cart, missing = [], []
    for c in last["items"]:
        if _is_table(block):
            p = store.product(block.id, c["id"])
            groups = {o["name"]: (o["choices"], o.get("prices") or []) for o in (p or {}).get("options", [])}
            base = p["price"] if p else 0
        else:
            item = next((i for i in block.items if i.id == c["id"]), None)
            p = {"name": item.name, "stock": None} if item else None
            groups = {g.name: (g.choices, g.prices) for g in (item.options if item else [])}
            base = item.price if item else 0
        opts = c.get("options", {})
        if p is None or any(n not in groups or v not in groups[n][0] for n, v in opts.items()):
            missing.append(c["name"])
            continue
        price = base + sum((groups[n][1][groups[n][0].index(v)] if groups[n][1] else 0) for n, v in opts.items())
        qty = c.get("qty", 1)
        if p["stock"] is not None:
            qty = min(qty, p["stock"] - sum(x.get("qty", 1) for x in cart if x["id"] == c["id"]))
        if qty < 1:
            missing.append(c["name"])
            continue
        line = {"id": c["id"], "name": p["name"], "price": max(0, price), "options": dict(opts)}
        if "qty" in c:
            line["qty"] = qty
        cart.append(line)
    d["_cart"] = cart[: block.max_items]
    session["step"] = "more"
    note = [send("این موارد دیگر موجود نیست و کنار گذاشته شد: " + "، ".join(missing))] if missing else []
    return note + [_cart_view(d)]


# ---------- delivery / pickup time ----------
def _windows(block, store, now, session) -> list[tuple[int, int]]:
    """(day offset, window index) still open: in the future (with the lead time), on a day the shop takes orders, not full."""
    out = []
    for k in range(block.window_days):
        day = now.date() + timedelta(days=k)
        if block.order_hours and not session.get("test") and not any(w.weekday == dates.persian_weekday(day) for w in block.order_hours):
            continue
        taken = [r for r in store.find(block.id, _tw_day=day.isoformat()) if r.get("status") != "cancelled"] if block.per_window else []
        for i, w in enumerate(block.time_windows):
            if k == 0 and _hm(w.start) < now.hour * 60 + now.minute + block.min_lead_minutes:
                continue
            if block.per_window and sum(1 for r in taken if r.get("_tw") == i) >= block.per_window:
                continue
            out.append((k, i))
    return out


def _window_label(block, now, k: int, i: int) -> str:
    w, day = block.time_windows[i], now.date() + timedelta(days=k)
    name = "امروز" if k == 0 else "فردا" if k == 1 else f"{dates.WEEKDAYS[dates.persian_weekday(day)]} {dates.jalali_str(day)[5:]}"
    return fa_digits(f"{name} {w.start} تا {w.end}")


def _window_prompt(block, store, now, session):
    open_ = _windows(block, store, now, session)
    if not open_:
        return None
    return send(block.window_question, [_btn(_window_label(block, now, k, i), f"tw:{k}:{i}") for k, i in open_[:24]])


def _no_window(block):
    when = "امروز" if block.window_days == 1 else "روزهای پیش رو"
    return send(f"متأسفانه برای {when} زمان تحویل خالی نمانده است.")


def _after_window(spec, session, block, store):
    if block.discount_codes:
        session["step"] = "code"
        return [_code_prompt(block)]
    return _first_question(spec, session, store, block.fields)


# ---------- card-to-card ----------
def _card_text(block, row) -> str:
    holder = f"\nبه نام {block.card_holder}" if block.card_holder else ""
    return (f"مبلغ {row['total']:,} تومان را به این کارت واریز کنید:\n{block.card_number}{holder}\n\n"
            f"سپس شماره‌ی پیگیری یا عکس رسید را همین‌جا بفرستید (تا {block.card_wait_minutes} دقیقه؛ پس از آن سفارش لغو می‌شود).")


def _card_buttons(bi: int, rid: int):
    return [_btn("📨 ارسال رسید", f"tr:{bi}:{rid}"), _btn("❌ انصراف از سفارش", f"tx:{bi}:{rid}")]


def _transfer(spec, session, block, store, now, text):
    """The customer sends the reference number or a photo of the receipt; the owner confirms it in the dashboard."""
    d = session["data"]
    rid = d.get("_rid")
    rows = store.find(block.id, id=rid)
    if not rows or rows[0].get("status") != "awaiting_transfer":
        _reset(session)
        return [menu_actions(spec)]
    row = rows[0]
    v = norm(text)
    photo = session.pop("_photo", None)
    if re.fullmatch(r"tr:\d+:\d+", v):
        return [send("شماره‌ی پیگیری واریز یا عکس رسید را بفرستید:")]
    if v.startswith("photo:"):
        ref = "📷 عکس رسید"
        photo = photo or v[6:]
    elif v.startswith("loc:") or len(v) < 4 or re.fullmatch(r"[a-z]{1,3}:[\w:]*", v):  # a stray button tap is not a reference
        return [send("لطفاً شماره‌ی پیگیری واریز (دست‌کم ۴ رقم) یا عکس رسید را بفرستید.")]
    else:
        ref = v[:60]
    store.update(block.id, row["id"], status="transfer_sent", transfer_ref=ref, _ref_at=now.isoformat())
    actions = [send(f"✅ رسید شما دریافت شد. پس از بررسی واریز، سفارش {row['id']} ثبت نهایی می‌شود و همین‌جا خبرتان می‌کنیم.")]
    note = {"type": "notify_admin", "text": f"💳 کارت‌به‌کارت · {block.title}\nسفارش #{row['id']} - {row['total']:,} تومان\n"
                                            f"پیگیری: {ref}\n{_order_lines(row)}\nپس از دیدن واریز، در بات‌یار بخش «ثبت‌ها» آن را تأیید کنید."}
    if photo:
        note["photo"] = photo
    actions.append(note)  # always: the owner must check the money, whatever admin_notify says
    _reset(session)
    actions.append(menu_actions(spec))
    return actions


def _cancel_transfer(spec, session, store, now, bi: int, rid: int):
    b = spec.blocks[bi] if 0 <= bi < len(spec.blocks) else None
    cust = session.get("cust")
    rows = store.find(b.id, id=rid, _cust=cust) if b is not None and b.type == "catalog_order" and cust else []
    if not rows or rows[0].get("status") not in ("awaiting_transfer", "transfer_sent"):
        return [send("این سفارش دیگر قابل لغو نیست."), menu_actions(spec)]
    if rows[0]["status"] == "transfer_sent":
        return [send("رسید این سفارش فرستاده شده است؛ برای لغو با مدیر تماس بگیرید."), menu_actions(spec)]
    actions, _ = cancel_record(spec, store, now, b, rows[0], by="system")
    return [send("سفارش لغو شد."), *actions, menu_actions(spec)]


def confirm_transfer(store, now, b, r: dict) -> list[dict]:
    """The owner saw the money: the order becomes a normal new order and the customer is told."""
    if b.type != "catalog_order" or r.get("status") not in ("awaiting_transfer", "transfer_sent"):
        raise ValueError("این سفارش منتظر تأیید واریز نیست.")
    store.update(b.id, r["id"], status="new", paid=True, _paid_at=now.isoformat(), _charge="card")
    if r.get("_cust"):
        return [{"type": "notify_customer", "cust": r["_cust"], "text": f"✅ واریز شما تأیید شد. {b.confirm_text}\nشماره‌ی سفارش: {r['id']}"}]
    return []


def _order(spec, session, block: CatalogOrderBlock, text, store, now):
    text_n = norm(text)
    d = session["data"]
    step = session["step"]
    table = _is_table(block)

    if step == "ref":
        return _transfer(spec, session, block, store, now, text)
    if text_n == "ro" and step in ("item", "cat", "list", "q", "more"):
        out = _repeat(session, block, store)
        if out is not None:
            return out
    mn = re.fullmatch(r"ns:(\d+)", text_n)
    if mn and table and step in ("cat", "list", "q", "more"):
        return _restock_request(session, block, store, now, int(mn.group(1)))

    if step == "item":  # inline menu
        item = next((i for i in block.items if text_n == f"i:{i.id}" or text_n.startswith(i.name)), None)
        if item is None:
            return [send("لطفاً یکی از آیتم‌ها را انتخاب کنید."), _item_prompt(block)]
        d["_pending"] = {"id": item.id, "name": item.name, "price": item.price, "options": {},
                         "_groups": [[g.name, g.choices, g.prices] for g in item.options]}
        d["_opt_idx"] = 0
        return _next_option(session, block)

    if step == "cat":
        cats = store.categories(block.id)
        m = re.fullmatch(r"c:(\d+)", text_n)
        if text_n == "search":
            session["step"] = "q"
            return [send("نام یا بخشی از نام محصول را بنویسید:")]
        if text_n == "all":
            d["_cat"] = None
        elif m and int(m.group(1)) < len(cats):
            d["_cat"] = cats[int(m.group(1))]
        else:
            hit = next((c for c in cats if fa_norm(c) == fa_norm(text_n)), None)
            if hit is None:
                return [send("لطفاً یکی از دسته‌ها را انتخاب کنید."), _cat_prompt(block, store)]
            d["_cat"] = hit
        d["_q"], d["_page"], session["step"] = None, 0, "list"
        return [_list_prompt(block, store, d, edit=bool(m) or text_n == "all")]  # a clicked category replaces the category menu

    if step == "q":
        d["_q"], d["_cat"], d["_page"], session["step"] = text.strip(), None, 0, "list"
        return [_list_prompt(block, store, d)]

    if step == "list":
        m = re.fullmatch(r"p:(\d+)", text_n)
        if m:
            return _pick_product(session, block, store, int(m.group(1)))
        pg = re.fullmatch(r"pg:(\d+)", text_n)
        if pg:
            d["_page"] = int(pg.group(1))
            return [_list_prompt(block, store, d, edit=True)]  # next/previous page edits the same message
        if text_n == "search":
            session["step"] = "q"
            return [send("نام یا بخشی از نام محصول را بنویسید:")]
        if text_n == "back" and len(store.categories(block.id)) > 1:
            d["_q"] = None
            session["step"] = "cat"
            return [_cat_prompt(block, store, edit=True)]
        d["_q"], d["_cat"], d["_page"] = text.strip(), None, 0  # free text = quick search
        return [_list_prompt(block, store, d)]

    if step == "option":
        name, choices, prices = d["_pending"]["_groups"][d.get("_opt_idx", 0)]
        j = next((k for k, c in enumerate(choices) if c == text.strip() or norm(c) == text_n), None)
        if j is None:
            return [send("لطفاً یکی از گزینه‌ها را انتخاب کنید."), _option_prompt(name, choices, prices)]
        d["_pending"]["options"][name] = choices[j]
        if prices:
            d["_pending"]["price"] = max(0, d["_pending"]["price"] + prices[j])
        d["_opt_idx"] = d.get("_opt_idx", 0) + 1
        return _next_option(session, block)

    if step == "qty":
        m = re.fullmatch(r"(?:n:)?(\d+)", text_n)
        n = int(m.group(1)) if m else 0
        stock = d["_pending"].get("stock")
        already = sum(c.get("qty", 1) for c in d["_cart"] if c["id"] == d["_pending"]["id"])
        top = min(99, stock - already) if stock is not None else 99
        if n < 1:
            return [send("لطفاً تعداد را به صورت عدد وارد کنید."), _qty_prompt(d["_pending"])]
        if n > top:
            return [send(f"حداکثر {top} عدد دیگر از این محصول موجود است." if already else f"حداکثر موجودی این محصول {top} عدد است."), _qty_prompt(d["_pending"])]
        return _add_to_cart(session, block, n)

    if step == "code":
        if text_n in ("dc:no", "ندارم") or not block.discount_codes:
            d["_code"] = None
            return _first_question(spec, session, store, block.fields)
        subtotal = _cart_total(d["_cart"])
        pick = re.fullmatch(r"dc:(\d+)", text_n)
        code = block.discount_codes[int(pick.group(1))] if pick and int(pick.group(1)) < len(block.discount_codes) and block.discount_codes[int(pick.group(1))].visible else _find_code(block, text)
        err = _code_error(block, store, subtotal, code)
        if err:
            return [send(err), _code_prompt(block)]
        d["_code"] = code.code
        saved = _price(block, subtotal, code)["discount"]
        return [send(f"✅ کد تخفیف اعمال شد؛ {saved:,} تومان کمتر می‌پردازید."), *_first_question(spec, session, store, block.fields)]

    if step == "more":
        if text_n == "cart":
            return [_cart_view(d)]
        mr = re.fullmatch(r"rm:(\d+)", text_n)
        if mr:
            i = int(mr.group(1))
            if 0 <= i < len(d["_cart"]):
                d["_cart"].pop(i)
            return [_cart_view(d, edit=True)]
        if text_n == "more":
            if table:
                session["step"] = "list"
                return [_list_prompt(block, store, d)]
            session["step"] = "item"
            return [_item_prompt(block)]
        if text_n == "checkout":
            if not _open_now(block, now, session):  # the shop closed while this customer was choosing
                _reset(session)
                return [send(_closed_msg(block)), menu_actions(spec)]
            if not d["_cart"]:
                return [send("سبد سفارش خالی است."), _more_prompt()]
            if _cart_total(d["_cart"]) < block.min_total:
                return [send(f"حداقل مبلغ سفارش {block.min_total:,} تومان است. لطفاً آیتم بیشتری اضافه کنید."), _more_prompt()]
            d.pop("_code", None)
            d.pop("_zone", None)
            d.pop("_tw", None)
            if block.delivery_zones:
                session["step"] = "zone"
                return [_zone_prompt(block)]
            return _after_zone(spec, session, block, store, now)
        return [_more_prompt()]

    if step == "zone":
        i = None
        if text_n.startswith("z:") and text_n[2:].isdigit():
            i = int(text_n[2:])
        else:  # typed instead of tapped: the area's name
            i = next((k for k, z in enumerate(block.delivery_zones) if fa_norm(z.label) == fa_norm(text)), None)
        if i is None or not 0 <= i < len(block.delivery_zones):
            return [send("لطفاً یکی از گزینه‌ها را انتخاب کنید."), _zone_prompt(block)]
        d["_zone"] = i
        return _after_zone(spec, session, block, store, now)

    if step == "when":
        m = re.fullmatch(r"tw:(\d+):(\d+)", text_n)
        pick = (int(m.group(1)), int(m.group(2))) if m else None
        if pick is None or pick not in _windows(block, store, now, session):
            prompt = _window_prompt(block, store, now, session)
            if prompt is None:
                session["step"] = "more"
                return [_no_window(block), _more_prompt()]
            return [send("لطفاً یکی از زمان‌های خالی را انتخاب کنید." if pick is None else "این زمان دیگر خالی نیست؛ لطفاً زمان دیگری انتخاب کنید."), prompt]
        d["_tw"] = list(pick)
        return _after_window(spec, session, block, store)

    # contact fields
    done, actions = _field_step(session, block.fields, text)
    if not done:
        return actions
    cart = d["_cart"]
    tw = tuple(d["_tw"]) if d.get("_tw") else None
    if tw is not None and tw not in _windows(block, store, now, session):  # the window filled up while this customer typed
        prompt = _window_prompt(block, store, now, session)
        if prompt is None:
            session["step"] = "more"
            return [_no_window(block), _more_prompt()]
        session["step"] = "when"
        d.pop("_tw", None)
        return [send("زمانی که انتخاب کرده بودید همین حالا پر شد؛ لطفاً زمان دیگری انتخاب کنید."), prompt]
    low = _stock_alerts(block, store, cart)
    if table:  # reserve stock for all lines atomically (all or nothing)
        failed = store.reserve(block.id, [(c["id"], c.get("qty", 1)) for c in cart])
        if failed:
            gone = [c["name"] for c in cart if c["id"] in failed]
            d["_cart"] = [c for c in cart if c["id"] not in failed]
            session["step"] = "more"
            return [send("متأسفانه موجودی این مورد کافی نیست و از سفارش حذف شد: " + "، ".join(gone)), _more_prompt()]
    subtotal = _cart_total(cart)
    code = _find_code(block, d["_code"]) if d.get("_code") else None
    dropped = False
    if code is not None and _code_error(block, store, subtotal, code):
        code, dropped = None, True  # its last uses were taken while this customer filled in the form
    zone = _zone(block, d)
    price = _price(block, subtotal, code, zone)
    total = price["total"]
    contact = {f.key: d[f.key] for f in block.fields}
    extra = {"subtotal": subtotal, "discount": price["discount"], "discount_code": code.code if code else None, "delivery_fee": price["delivery_fee"]} if (code or dropped or block.delivery_fee or block.discount_codes or zone) else {}
    if zone is not None:
        extra["delivery_zone"] = zone.label
    if tw is not None:
        extra.update(delivery_time=_window_label(block, now, *tw), _tw_day=(now.date() + timedelta(days=tw[0])).isoformat(), _tw=tw[1])
    online = block.payment == "online" and bool(session.get("pay_ok")) and total > 0
    card = block.payment == "card" and total > 0
    status = "awaiting_payment" if online else "awaiting_transfer" if card else "new"
    row = store.add(block.id, {**contact, "items": cart, "total": total, "status": status, **extra, **_ident(session, now)})
    low_notes = [{"type": "notify_admin", "text": t} for t in low]
    lines = "\n".join(f"- {c['name']} {' '.join(c['options'].values())}".strip() + (f" × {c['qty']}" if "qty" in c else "") for c in cart)
    breakdown = ""
    if price["discount"] or price["delivery_fee"] or block.delivery_fee or zone is not None:
        breakdown = f"\nمبلغ کالاها: {subtotal:,} تومان"
        if price["discount"]:
            breakdown += f"\nتخفیف ({code.code}): {price['discount']:,} تومان"
        where = f" ({zone.label})" if zone is not None else ""
        breakdown += f"\nهزینه‌ی ارسال{where}: {price['delivery_fee']:,} تومان" if price["delivery_fee"] else f"\nهزینه‌ی ارسال{where}: رایگان"
    if tw is not None:
        breakdown += f"\nزمان تحویل: {extra['delivery_time']}"
    if dropped:
        breakdown += "\n⚠️ ظرفیت کد تخفیف در همین فاصله تمام شد و اعمال نشد."
    if card:  # the owner hears about it once the customer sends the receipt
        bi = next(i for i, b in enumerate(spec.blocks) if b.id == block.id)
        _reset(session)
        session.update(block=block.id, step="ref", data={"_rid": row["id"]})
        return [send(f"سفارش {row['id']}:\n{lines}{breakdown}\nمبلغ قابل پرداخت: {total:,} تومان"),
                send(_card_text(block, row), _card_buttons(bi, row["id"])), *low_notes]
    if online:  # the owner is notified when the money arrives, not when the cart is filled
        invoice_text = f"{lines}{breakdown}\nمبلغ قابل پرداخت: {total:,} تومان\nبرای ثبت نهایی سفارش، پرداخت را انجام دهید (تا {PAY_WINDOW_MINUTES} دقیقه فرصت دارید)."
        if session.get("pay_sim"):
            actions = [send(invoice_text + "\n(پرداخت آزمایشی؛ در بله فاکتور واقعی ارسال می‌شود)", [_btn("💳 پرداخت (آزمایشی)", f"pay:{row['id']}")])]
        else:
            actions = [{"type": "invoice", "rid": row["id"], "amount": total, "title": f"سفارش شماره {row['id']}"[:32], "text": invoice_text}]
        _reset(session)
        actions += low_notes
        actions.append(menu_actions(spec))
        return actions
    if block.payment == "online" and not session.get("pay_ok"):
        breakdown += "\nپرداخت آنلاین هنوز برای این ربات فعال نشده است؛ مدیر درباره‌ی پرداخت با شما هماهنگ می‌کند."
    actions = [send(f"{_fill(block.confirm_text, row)}\n{lines}{breakdown}\nجمع کل: {total:,} تومان")]
    _notify(spec, block.id, f"سفارش #{row['id']} - جمع {total:,} تومان" + (f" (کد {code.code})" if code else "") + f"\n{lines}"
            + (f"\nمحل ارسال: {zone.label}" if zone is not None else "")
            + (f"\nزمان تحویل: {extra['delivery_time']}" if tw is not None else ""), actions, total=total)
    _reset(session)
    actions += low_notes
    actions.append(menu_actions(spec))
    return actions



# ---------- FAQ (retrieval only: the customer always receives the owner's own answer text) ----------
FAQ_PAGE = 8


def _faq_nav():
    return [_btn("بازگشت به منو", "/menu")]


def _faq_prompt(block: FaqBlock):
    if len(block.entries) <= 6:
        return send(block.prompt_text, [_btn(_short(e.question, 50), f"fq:{i}") for i, e in enumerate(block.entries)] + _faq_nav())
    return send(block.prompt_text, [_btn("📋 فهرست سؤال‌ها", "fl")] + _faq_nav())


def _faq_start(session, block: FaqBlock):
    session.update(block=block.id, step="ask", data={})
    return [send(block.title), _faq_prompt(block)]


def _faq_cats(block: FaqBlock) -> list[str]:
    """The categories in order of first appearance; questions without one go under «سایر سؤال‌ها»."""
    cats: list[str] = []
    for e in block.entries:
        c = e.category.strip() or "سایر سؤال‌ها"
        if c not in cats:
            cats.append(c)
    return cats if len(cats) > 1 else []


def _faq_list(block: FaqBlock, page: int, edit: bool = False, cat: int | None = None):
    cats = _faq_cats(block)
    if cats and cat is None:  # many questions in groups: pick a group first
        return send("موضوع سؤال را انتخاب کنید:", [_btn(_short(c, 40), f"fk:{i}") for i, c in enumerate(cats)] + [_btn("بازگشت", "fa")], edit)
    idx = list(range(len(block.entries)))
    if cats and cat is not None and 0 <= cat < len(cats):
        idx = [i for i in idx if (block.entries[i].category.strip() or "سایر سؤال‌ها") == cats[cat]]
    pages = max(1, math.ceil(len(idx) / FAQ_PAGE))
    page = min(max(page, 0), pages - 1)
    chunk = idx[page * FAQ_PAGE:(page + 1) * FAQ_PAGE]
    buttons = [_btn(_short(block.entries[i].question, 50), f"fq:{i}") for i in chunk]
    tail = f":{cat}" if cats and cat is not None else ""
    if page > 0:
        buttons.append(_btn("‹ قبلی", f"fp:{page - 1}{tail}"))
    if page + 1 < pages:
        buttons.append(_btn("بعدی ›", f"fp:{page + 1}{tail}"))
    head = cats[cat] if cats and cat is not None and 0 <= cat < len(cats) else "فهرست سؤال‌ها"
    back = _btn("بازگشت به موضوع‌ها", "fl") if cats else _btn("بازگشت", "fa")
    return send(f"{head} — صفحه {page + 1} از {pages}", buttons + [back], edit)


def _faq_answer(session, block: FaqBlock, i: int):
    session["data"]["_last_i"] = i
    e = block.entries[i]
    then = [_btn(e.then_label, f"go:{e.then}")] if e.then else []
    extras = []
    if e.media == "image":  # the photo the owner uploaded for this answer («فایل‌ها»)
        extras.append({"type": "media", "block": faq_media_key(block.id, i), "kind": "image"})
    if e.location is not None:
        extras.append({"type": "location", "latitude": e.location.latitude, "longitude": e.location.longitude})
    buttons = then + [_btn("👍 مفید بود", "fh1"), _btn("👎 مفید نبود", "fh0"), _btn("سؤال دیگر", "fa")] + _faq_nav()
    if extras:  # text first, then the photo / map, then the buttons (so they stay at the bottom of the chat)
        return [send(e.answer), *extras, send("آیا این پاسخ به کارتان آمد؟", buttons)]
    return [send(e.answer, buttons)]


def faq_media_key(block_id: str, i: int) -> str:
    return f"{block_id}#{i}"


def _faq_unanswered(spec, session, block: FaqBlock, store, now, question: str, note: str = ""):
    cust = session.get("cust")
    duplicate = cust and store.find(block.id, question=question, status="unanswered", _cust=cust)
    actions = [send(block.not_found_text, [_btn("📋 فهرست سؤال‌ها", "fl"), _btn("سؤال دیگر", "fa")] + _faq_nav())]  # the list rescues a valid question that was worded unusually
    if not duplicate:  # the same customer repeating a question must not spam the owner
        row = store.add(block.id, {"question": question, "status": "unanswered", **({"note": note} if note else {}), **_ident(session, now)})
        _notify(spec, block.id, f"سؤال: {question}" + (f"\n({note})" if note else ""), actions, prefix=f"❓ سؤال بدون پاسخ · {block.title}")
    return actions


def _faq(spec, session, block: FaqBlock, text, store, now, matcher):
    text_n = norm(text)
    d = session["data"]
    m = re.fullmatch(r"fq:(\d+)", text_n)
    if m and int(m.group(1)) < len(block.entries):
        return _faq_answer(session, block, int(m.group(1)))
    if text_n == "fl":
        return [_faq_list(block, 0)]
    mp = re.fullmatch(r"fp:(\d+)(?::(\d+))?", text_n)
    if mp:
        return [_faq_list(block, int(mp.group(1)), edit=True, cat=int(mp.group(2)) if mp.group(2) else None)]
    mk = re.fullmatch(r"fk:(\d+)", text_n)
    if mk:
        return [_faq_list(block, 0, edit=True, cat=int(mk.group(1)))]
    if text_n == "fa":
        return [_faq_prompt(block)]
    if text_n == "fh1":
        return [send("خوشحالیم که پاسخ به کارتان آمد 🌟", [_btn("سؤال دیگر", "fa")] + _faq_nav())]
    if text_n in ("fh0", "fn"):  # the answer did not help / none of the suggestions was right
        q = d.get("_last_q")
        if not q:
            return [_faq_prompt(block)]
        return _faq_unanswered(spec, session, block, store, now, q, note="پاسخ پیشنهادی کمک نکرد")
    query = text.strip()[:300]
    if len(query) < 2 or re.fullmatch(r"(?:fq|fp|fk)(?::\S*)?|fh\d|fl|fa|fn", text_n) or text_n.startswith(("photo:", "file:", "loc:")):  # a stale / forged button is never a customer's question
        return [_faq_prompt(block)]
    try:
        ranked, th = matcher.rank(block.id, block.entries, query, session.get("cust")), matcher.thresholds
    except RateLimited:
        return [send("تعداد جست‌وجوها در این ساعت زیاد شده است؛ کمی بعد دوباره امتحان کنید یا از فهرست سؤال‌ها استفاده کنید.", [_btn("📋 فهرست سؤال‌ها", "fl")] + _faq_nav())]
    except MatcherUnavailable:  # provider down / index not ready: degrade to word matching instead of failing
        lex = LexicalMatcher()
        ranked, th = lex.rank(block.id, block.entries, query), lex.thresholds
    d["_last_q"] = query
    kind, idx = decide(ranked, th)
    if kind == "answer":
        return _faq_answer(session, block, idx[0])
    if kind == "suggest":
        return [send("منظورتان یکی از این سؤال‌هاست؟", [_btn(_short(block.entries[i].question, 50), f"fq:{i}") for i in idx] + [_btn("هیچ‌کدام", "fn")])]
    return _faq_unanswered(spec, session, block, store, now, query)


# ---------- sub-menus ----------
def _submenu_prompt(block: MenuBlock, up: list | None = None):
    """A nested sub-menu also gets «بازگشت» to the menu it was opened from."""
    back = [_btn("‹ بازگشت", "s:up")] if up else []
    return send(block.title, [_btn(it.label, f"s:{n}") for n, it in enumerate(block.items)] + back + [_btn("بازگشت به منو", "/menu")])


def _submenu(spec, session, block: MenuBlock, text, store, now, rng):
    text_n = norm(text)
    up = list(session["data"].get("_up") or [])  # the sub-menus above this one, outermost first
    if text_n == "s:up" and up:
        parent = next((b for b in spec.blocks if b.id == up[-1] and b.type == "menu"), None)
        if parent is not None:
            session.update(block=parent.id, step="pick", data={"_up": up[:-1]})
            return [_submenu_prompt(parent, up[:-1])]
    m = re.fullmatch(r"s:(\d+)", text_n)
    if m and int(m.group(1)) < len(block.items):
        item = block.items[int(m.group(1))]
    else:
        item = next((i for i in block.items if fa_norm(i.label) == fa_norm(text_n)), None)
    if item is None:
        return [send("لطفاً یکی از گزینه‌ها را انتخاب کنید."), _submenu_prompt(block, up)]
    child = spec.block(item.block)
    if child.type == "menu":  # deeper: remember the way back
        _start_block(spec, session, child, store, now, rng)
        session["data"]["_up"] = [*up, block.id]
        return [_submenu_prompt(child, session["data"]["_up"])]
    if child.type == "message":  # reading a text keeps the customer in the sub-menu so they can browse its siblings
        return message_actions(child, session, rng, _submenu_prompt(block, session["data"].get("_up")), now)
    return _start_block(spec, session, child, store, now, rng)


# ---------- anonymous chat (pairing and relaying are done by the channel adapter, see anon.py) ----------
def _leave_anon(spec, session) -> list[dict]:
    """Going back to the menu while waiting or chatting must also release the partner / the queue place."""
    if session.get("block") is None:
        return []
    b = next((x for x in spec.blocks if x.id == session["block"]), None)
    if b is not None and b.type == "anon_chat" and session.get("step") in ("waiting", "chat"):
        return [{"type": "anon_end", "block": b.id}]
    return []


def _anon_buttons():
    return [_btn("⛔ پایان گفتگو", "ac:end"), _btn("🔄 شریک بعدی", "ac:next"), _btn("🚫 گزارش تخلف", "ac:report")]


def _anon_find_buttons(block: AnonChatBlock):
    """One search button, or one per topic room («درس»، «سرگرمی») when the block has topics."""
    if block.topics:
        return [_btn(f"🔍 {t}", f"ac:find:{i}") for i, t in enumerate(block.topics)] + [_btn("بازگشت به منو", "/menu")]
    return [_btn("🔍 پیدا کردن شریک گفتگو", "ac:find"), _btn("بازگشت به منو", "/menu")]


def _anon_find(session, block: AnonChatBlock):
    topic = session["data"].get("_topic", "")
    session["step"] = "waiting"
    where = f" در «{topic}»" if topic else ""
    return [send(f"در حال جستجوی شریک گفتگو{where}… به محض پیدا شدن، به شما خبر می‌دهیم.", [_btn("لغو جستجو", "ac:end")]),
            {"type": "anon_find", "block": block.id, "topic": topic}]


def _anon(spec, session, block: AnonChatBlock, text, now):
    text_n, step = norm(text), session.get("step")
    if step == "idle":
        mt = re.fullmatch(r"ac:find:(\d+)", text_n)
        if mt and int(mt.group(1)) < len(block.topics):
            session["data"]["_topic"] = block.topics[int(mt.group(1))]
            return _anon_find(session, block)
        if text_n == "ac:find" and not block.topics:
            return _anon_find(session, block)
        if text_n == "ac:find":  # a room is needed first
            return [send("موضوع گفت‌وگو را انتخاب کنید:", _anon_find_buttons(block))]
        return [send(block.intro_text, _anon_find_buttons(block))]
    if step == "waiting":
        if text_n == "ac:end":
            session["step"] = "idle"
            return [{"type": "anon_end", "block": block.id}, send("جستجو لغو شد.", [_btn("🔍 جستجوی دوباره", "ac:find"), _btn("بازگشت به منو", "/menu")])]
        return [send("هنوز کسی پیدا نشده است؛ منتظر بمانید یا جست‌وجو را لغو کنید.", [_btn("لغو جستجو", "ac:end")])]
    # step == "chat"
    if text_n == "ac:end":
        session["step"] = "idle"
        return [{"type": "anon_end", "block": block.id}, send("گفت‌وگو پایان یافت.", [_btn("🔍 جستجوی شریک جدید", "ac:find"), _btn("بازگشت به منو", "/menu")])]
    if text_n == "ac:next":
        session["step"] = "waiting"
        return [{"type": "anon_end", "block": block.id}, send("در حال جستجوی شریک جدید…", [_btn("لغو جستجو", "ac:end")]),
                {"type": "anon_find", "block": block.id, "topic": session["data"].get("_topic", "")}]
    if text_n == "ac:report":
        session["step"] = "idle"
        return [{"type": "anon_report", "block": block.id}, send("گزارش شما برای مدیر ثبت شد و گفت‌وگو پایان یافت. از همراهی شما متشکریم.", [_btn("🔍 جستجوی شریک جدید", "ac:find"), _btn("بازگشت به منو", "/menu")])]
    return [{"type": "anon_relay", "block": block.id, "text": text.strip()[:500]}]


# ---------- referral (invite links) ----------
def _referral(spec, session, block: ReferralBlock):
    """The channel adapter puts this customer's personal link and invite count into session["ref"] before every turn."""
    ref = session.get("ref") or {}
    count = int(ref.get("count", 0))
    lines = [block.text, ""]
    lines.append(f"لینک اختصاصی شما:\n{ref['link']}" if ref.get("link") else "(لینک اختصاصی فقط در بله و تلگرام ساخته می‌شود)")
    goals = [(block.goal, block.reward_text, block.reward_code), *((t.goal, t.reward_text, t.reward_code) for t in block.tiers)]
    nxt = next((g for g, _, _ in goals if g > count), None)
    lines.append(f"دعوت‌های موفق: {count} از {nxt or goals[-1][0]}")
    if block.count_after == "order":
        lines.append("(هر دعوت وقتی حساب می‌شود که دوستتان اولین سفارش یا نوبتش را ثبت کند)")
    for g, text, code in goals:  # every reward already earned, with its code
        if count >= g:
            lines += ["", f"🎁 {text}" + (f"\nکد تخفیف شما: {code}" if code else "")]
    if nxt and block.tiers:
        upcoming = "، ".join(f"{g} دعوت" for g, _, _ in goals if g > count)
        lines += ["", f"جایزه‌های بعدی: {upcoming}"]
    return [send("\n".join(lines)), menu_actions(spec)]


# ---------- quiz ----------
def _quiz_order(block: QuizBlock, d: dict) -> list[int]:
    return d.get("order") or list(range(len(block.questions)))  # sessions started before shuffle/pick existed


def _quiz_question(block: QuizBlock, d: dict, i: int):
    order = _quiz_order(block, d)
    q = block.questions[order[i]]
    return send(f"سؤال {i + 1} از {len(order)}:\n{q.question}", [_btn(o, f"qa:{j}") for j, o in enumerate(q.options)] + [_btn("بازگشت به منو", "/menu")])


def _quiz_ask(block: QuizBlock, d: dict, i: int) -> list:
    """The question, after its photo when it has one (so the answer buttons stay at the bottom)."""
    k = _quiz_order(block, d)[i]
    photo = [{"type": "media", "block": quiz_media_key(block.id, k), "kind": "image"}] if block.questions[k].media == "image" else []
    return [*photo, _quiz_question(block, d, i)]


def _personality(block: QuizBlock, d: dict):
    """The outcome most answers pointed to (a tie goes to the one listed first)."""
    counts = d.get("tally", {})
    return max(block.personality, key=lambda o: (counts.get(o.id, 0), -block.personality.index(o)))


def _quiz(spec, session, block: QuizBlock, text, store, now):
    text_n, d, i = norm(text), session["data"], session["step"]
    order = _quiz_order(block, d)
    q = block.questions[order[i]]  # IndexError here = the quiz changed under a running customer: the stale-state guard resets
    m = re.fullmatch(r"qa:(\d+)", text_n)
    idx = int(m.group(1)) if m else next((j for j, o in enumerate(q.options) if fa_norm(o) == fa_norm(text_n)), -1)
    if not 0 <= idx < len(q.options):
        return [send("لطفاً یکی از گزینه‌ها را انتخاب کنید."), *_quiz_ask(block, d, i)]
    actions = []
    if block.personality:  # no right answers: each option counts toward an outcome
        tally = d.setdefault("tally", {})
        tally[q.outcomes[idx]] = tally.get(q.outcomes[idx], 0) + 1
    else:
        right = idx == q.correct
        d["score"] += int(right)
        if block.show_answers:
            actions.append(send("✅ درست!" if right else f"❌ نادرست. پاسخ درست: {q.options[q.correct]}"))
    if i + 1 < len(order):
        session["step"] = i + 1
        return [*actions, *_quiz_ask(block, d, i + 1)]
    total, score = len(order), d["score"]
    who = session.get("cust_name") or "مشتری"
    if block.personality:
        o = _personality(block, d)
        store.add(block.id, {"result": o.title, "who": who, "status": "done", **_ident(session, now)})
        actions.append(send(f"نتیجه‌ی شما: {o.title}\n\n{o.text}"))
        _notify(spec, block.id, f"{who}: {o.title}", actions, prefix=f"🎯 نتیجه‌ی آزمون · {block.title}")
        _reset(session)
        actions.append(menu_actions(spec))
        return actions
    row = store.add(block.id, {"score": score, "total": total, "percent": round(100 * score / total), "who": who, "status": "done", **_ident(session, now)})
    result = _fill(block.result_text, row)
    if block.pass_percent:
        passed = row["percent"] >= block.pass_percent
        result += "\n" + (block.pass_text if passed else block.fail_text)
        if passed and block.pass_code:
            result += f"\n🎁 کد تخفیف شما: {block.pass_code}"
    actions.append(send(result))
    _notify(spec, block.id, f"{who}: {score} از {total}", actions, prefix=f"🎯 نتیجه‌ی آزمون · {block.title}")
    _reset(session)
    actions.append(menu_actions(spec))
    return actions


# ---------- feedback (1-5 stars + optional comment) ----------
FEEDBACK_PER_DAY = 5


def _rate_prompt(block: FeedbackBlock, aspect: str | None = None):
    return send(f"«{aspect}»" if aspect else block.prompt_text, [_btn("⭐" * n, f"r:{n}") for n in range(1, 6)] + [_btn("بازگشت به منو", "/menu")])


def _feedback(spec, session, block: FeedbackBlock, text, store, now):
    text_n, d = norm(text), session["data"]
    if session["step"] == "rate":
        i = len(d.get("ratings", {}))
        aspect = block.aspects[i] if block.aspects else None
        m = re.fullmatch(r"r:([1-5])", text_n)
        if not m:
            return [send("لطفاً با یکی از دکمه‌ها امتیاز دهید."), _rate_prompt(block, aspect)]
        if aspect:  # one score per aspect; the overall rating is their rounded mean
            d.setdefault("ratings", {})[aspect] = int(m.group(1))
            if i + 1 < len(block.aspects):
                return [_rate_prompt(block, block.aspects[i + 1])]
            d["rating"] = max(1, min(5, round(sum(d["ratings"].values()) / len(d["ratings"]))))
        else:
            d["rating"] = int(m.group(1))
        session["step"] = "comment"
        return [send(block.comment_text, [_btn("رد کردن", "sk"), _btn("بازگشت به منو", "/menu")])]
    if session["step"] == "phone":
        if text_n not in ("sk", norm(SKIP)):
            ok, phone, err = validate(FormField(key="phone", label="", kind="phone"), text)
            if not ok:
                return [send(err), send(block.follow_up_text, [_btn("رد کردن", "sk")])]
            d["phone"] = phone
        return _feedback_save(spec, session, block, store, now)
    d["comment"] = "" if text_n == "sk" else text.strip()[:500]
    if block.follow_up_below and d["rating"] < block.follow_up_below:  # an unhappy customer: offer a call back first
        session["step"] = "phone"
        return [send(block.follow_up_text, [_btn("رد کردن", "sk")])]
    return _feedback_save(spec, session, block, store, now)


def _feedback_save(spec, session, block: FeedbackBlock, store, now):
    d = session["data"]
    comment = d.get("comment", "")
    cust = session.get("cust")
    if cust:  # a customer can't flood the averages
        day_ago = now - timedelta(days=1)
        recent = sum(1 for r in store.find(block.id, _cust=cust) if datetime.fromisoformat(r["_at"]) > day_ago)
        if recent >= FEEDBACK_PER_DAY:
            _reset(session)
            return [send("امتیاز امروز شما قبلاً ثبت شده است؛ متشکریم!"), menu_actions(spec)]
    extra = {k: d[k] for k in ("ratings", "phone", "about") if d.get(k)}
    row = store.add(block.id, {"rating": d["rating"], "comment": comment, "status": "new", **extra, **_ident(session, now)})
    actions = [send(block.thanks_text)]
    low = bool(block.follow_up_below and d["rating"] < block.follow_up_below)
    details = (f" · {d['about']}" if d.get("about") else "") + "".join(f"\n{a}: {'⭐' * n}" for a, n in d.get("ratings", {}).items()) + (f"\n{comment}" if comment else "") + (f"\nموبایل برای تماس: {d['phone']}" if d.get("phone") else "")
    _notify(spec, block.id, f"{'⭐' * d['rating']}" + details, actions, prefix=f"{'⚠️ نظر با امتیاز پایین' if low else '⭐ نظر جدید'} · {block.title}",
            rating=d["rating"])
    _reset(session)
    actions.append(menu_actions(spec))
    return actions


def feedback_requests(spec: BotSpec, store, now) -> list[dict]:
    """Ask for a rating once, `after_hours` after a booking's time (or after an order was marked «تحویل شد»), with the stars in
    the message. Only recent ones (3 days), so turning the feature on never messages last month's customers."""
    out: list[dict] = []
    for fi, fb in enumerate(spec.blocks):
        if fb.type != "feedback" or not fb.after:
            continue
        src = next((b for b in spec.blocks if b.id == fb.after), None)
        if src is None:
            continue
        for r in store.find(src.id):
            if r.get("_fb_asked") or not r.get("_cust"):
                continue
            if src.type == "booking":
                if r.get("status") != "confirmed":
                    continue
                when = booking_start(src, r, now.tzinfo)
                what = r.get("service") or r.get("slot_label") or src.title
            else:
                if r.get("status") != "done" or not r.get("_done_at"):
                    continue
                when = datetime.fromisoformat(r["_done_at"])
                what = f"سفارش {r['id']}"
            if when is None or not (timedelta(hours=fb.after_hours) <= now - when <= timedelta(days=3)):
                continue
            store.update(src.id, r["id"], _fb_asked=now.isoformat())
            text = fb.ask_text.replace("{what}", str(what))
            out.append({"type": "notify_customer", "cust": r["_cust"], "text": text,
                        "buttons": [_btn("⭐" * n, f"fbr:{fi}:{r['id']}:{n}") for n in range(5, 0, -1)]})
    return out


def _rated_from_request(spec, session, store, now, fi: int, rid: int, n: int):
    """A star tapped under an automatic request: the rating is in, the comment question follows."""
    fb = spec.blocks[fi] if 0 <= fi < len(spec.blocks) else None
    if fb is None or fb.type != "feedback" or not 1 <= n <= 5:
        return [menu_actions(spec)]
    src = next((b for b in spec.blocks if b.id == fb.after), None)
    rows = store.find(src.id, id=rid, _cust=session.get("cust")) if src is not None and session.get("cust") else []
    if not rows:
        return [menu_actions(spec)]
    if rows[0].get("_fb_done"):
        return [send("امتیاز شما برای این مورد قبلاً ثبت شده است؛ متشکریم!"), menu_actions(spec)]
    store.update(src.id, rid, _fb_done=True)
    about = rows[0].get("service") or rows[0].get("slot_label") or (f"سفارش {rid}" if src.type == "catalog_order" else src.title)
    session.update(block=fb.id, step="comment", data={"rating": n, "about": about})
    return [send(fb.comment_text, [_btn("رد کردن", "sk"), _btn("بازگشت به منو", "/menu")])]


# ---------- talk to the owner (messages go to the dashboard inbox; the owner's replies come back to this chat) ----------
CONTACT_MAX_CHARS, CONTACT_PER_HOUR = 1000, 20


def thread_id(cust: str | None) -> str:
    import hashlib

    return hashlib.sha1((cust or "anon").encode()).hexdigest()[:12]


def _topic_prompt(block: ContactBlock):
    return send("موضوع پیام خود را انتخاب کنید:", [_btn(t, f"tp:{i}") for i, t in enumerate(block.topics)] + _faq_nav())


def _contact(spec, session, block: ContactBlock, text, store, now):
    if session["step"] == "topic":
        m = re.fullmatch(r"tp:(\d+)", norm(text))
        i = int(m.group(1)) if m else next((k for k, t in enumerate(block.topics) if fa_norm(t) == fa_norm(text)), -1)
        if not 0 <= i < len(block.topics):
            return [send("لطفاً یکی از موضوع‌ها را انتخاب کنید."), _topic_prompt(block)]
        session["data"]["topic"], session["step"] = block.topics[i], "msg"
        return [send(block.prompt_text, _faq_nav())]
    body = text.strip()[:CONTACT_MAX_CHARS]
    if not body:
        return [send(block.prompt_text, _faq_nav())]
    cust = session.get("cust")
    if cust:  # a flooding customer must not bury the owner
        hour_ago = now - timedelta(hours=1)
        recent = 0
        for r in store.find(block.id, _cust=cust):
            try:
                if r.get("from") == "customer" and datetime.fromisoformat(r["_at"]) > hour_ago:
                    recent += 1
            except (KeyError, ValueError):
                continue
        if recent >= CONTACT_PER_HOUR:
            return [send("تعداد پیام‌های این ساعت زیاد شده است؛ کمی بعد دوباره بنویسید.", _faq_nav())]
    who = session.get("cust_name") or "مشتری"
    topic = session["data"].get("topic")
    store.add(block.id, {"text": body, "from": "customer", "thread": thread_id(cust), "who": who, "status": "open",
                         **({"topic": topic} if topic else {}), **_ident(session, now)})
    away = ""
    if block.hours and not _within(block.hours, now) and not session["data"].get("_away"):  # once per visit, not after every message
        away = f"\n\n🕒 {block.away_text}\nساعت پاسخ‌گویی: {_hours_text(block.hours)}"
        session["data"]["_away"] = True
    actions = [send(block.sent_text + away, _faq_nav())]
    _notify(spec, block.id, f"{who}{f' ({topic})' if topic else ''}: {body}\n(برای پاسخ، بخش «پیام‌ها» در پنل بات‌یار را باز کنید)", actions,
            prefix=f"📩 پیام جدید از مشتری · {block.title}")
    return actions  # the customer stays in this step: a follow-up message goes to the owner as well


# ---------- customer cancellation («ثبت‌های من») ----------
def _cancel_blocks(spec: BotSpec):
    return [(i, b) for i, b in enumerate(spec.blocks) if b.type in ("booking", "catalog_order") and b.allow_cancel]


def _ident(session: dict, now) -> dict:
    """Who made a record and when (underscore keys are internal: never shown to the owner or exported)."""
    c = session.get("cust")
    return {"_cust": c, "_at": now.isoformat()} if c else {}


def _active(b, r: dict, now) -> bool:
    if b.type == "booking":
        if r.get("status") not in ("confirmed", "waitlisted"):
            return False
        if r.get("date") and r.get("time"):  # an appointment that already started is history
            return datetime.combine(date.fromisoformat(r["date"]), time(int(r["time"][:2]), int(r["time"][3:])), tzinfo=now.tzinfo) > now
        return not r.get("date") or date.fromisoformat(r["date"]) >= now.date()
    return r.get("status") == "new"


def _describe(b, r: dict) -> str:
    if b.type == "booking":
        return f"{r.get('slot_label', b.title)} — {STATUS_FA.get(r.get('status'), '')}"
    return f"سفارش {r['id']} — {r.get('total', 0):,} تومان"


def booking_start(b, r: dict, tz) -> datetime | None:
    """When the booked session starts, or None for one-off events without a clock time."""
    if not r.get("date"):
        return None
    slot = next((s for s in b.slots if s.id == r.get("slot")), None)
    hhmm = r.get("time") or (slot.time if slot else None)
    if not hhmm:
        return None
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime.combine(date.fromisoformat(r["date"]), time(h, m), tzinfo=tz)


def daily_summary(spec: BotSpec, store, today: date, tz) -> str | None:
    """The owner's morning brief: today's bookings in time order, open orders, questions and messages waiting
    for an answer, and tomorrow's count. None when there is nothing to report (no message is sent then)."""
    parts: list[str] = []
    tomorrow, n_tomorrow = today + timedelta(days=1), 0
    for b in spec.blocks:
        if b.type == "booking":
            today_rows = []
            for r in store.find(b.id):
                if r.get("status") not in ("confirmed", "waitlisted") or not r.get("date"):
                    continue
                d = date.fromisoformat(r["date"])
                if d == tomorrow and r["status"] == "confirmed":
                    n_tomorrow += 1
                if d == today:
                    today_rows.append(r)
            if not today_rows:
                continue
            lines = []
            if b.schedule:  # appointments: one line each, in time order
                for r in sorted((r for r in today_rows if r["status"] == "confirmed"), key=lambda r: r.get("time", "")):
                    who = " · ".join(str(r[k]) for k in ("name", "full_name", "phone") if r.get(k))
                    extra = " — ".join(x for x in (r.get("service"), r.get("staff")) if x)
                    lines.append(f"{r.get('time', '')} {who}" + (f" ({extra})" if extra else ""))
            else:  # classes/events: how many are coming to each session
                for s in b.slots:
                    rows = [r for r in today_rows if r.get("slot") == s.id]
                    came = sum(_party(r) for r in rows if r["status"] == "confirmed")
                    wait = sum(1 for r in rows if r["status"] == "waitlisted")
                    if rows:
                        lines.append(f"{s.label}: {came} از {s.capacity} نفر" + (f" · {wait} در لیست انتظار" if wait else ""))
            if lines:
                parts.append(f"📅 {b.title} — امروز:\n" + "\n".join(lines))
        elif b.type == "catalog_order":
            open_rows = [r for r in store.find(b.id) if r.get("status") in ("new", "preparing", "ready")]
            n_receipts = sum(1 for r in store.find(b.id) if r.get("status") == "transfer_sent")
            if n_receipts:
                parts.append(f"💳 {n_receipts} واریز کارت‌به‌کارت منتظر تأیید شما در «{b.title}»")
            if open_rows:
                by = {s: sum(1 for r in open_rows if r["status"] == s) for s in ("new", "preparing", "ready")}
                detail = "، ".join(f"{n} {STATUS_FA[s]}" for s, n in by.items() if n)
                parts.append(f"🛍 {b.title}: {len(open_rows)} سفارش باز ({detail})")
        elif b.type == "faq":
            n = sum(1 for r in store.find(b.id) if r.get("status") == "unanswered")
            if n:
                parts.append(f"❓ {n} سؤال بی‌پاسخ در «{b.title}»")
        elif b.type == "contact":
            last: dict = {}
            for r in sorted(store.find(b.id), key=lambda r: r.get("id", 0)):
                last[r.get("thread")] = r
            n = sum(1 for r in last.values() if r.get("from") == "customer")
            if n:
                parts.append(f"✉️ {n} گفت‌وگو منتظر پاسخ شما در «{b.title}»")
    if n_tomorrow:
        parts.append(f"فردا: {n_tomorrow} نوبت")
    if not parts:
        return None
    head = f"☀️ خلاصه‌ی امروز {dates.WEEKDAYS[dates.persian_weekday(today)]} {dates.jalali_str(today)} · {spec.name}"
    return fa_digits(head + "\n\n" + "\n\n".join(parts) + "\n\nجزئیات در پنل بات‌یار.")


PAY_WINDOW_MINUTES = 15


def _order_lines(r: dict) -> str:
    return "\n".join(f"- {c['name']} {' '.join(c['options'].values())}".strip() + (f" × {c['qty']}" if "qty" in c else "") for c in r.get("items", []))


def _deposit_note(block: BookingBlock, d: dict) -> str:
    """No wallet connected: the booking is confirmed and the owner arranges the deposit."""
    return "" if not block.deposit or d.get("paid") else fa_digits(f"\nپرداخت بیعانه ({block.deposit:,} تومان): مدیر درباره‌ی آن با شما هماهنگ می‌کند.")


def _deposit_due(block: BookingBlock, session) -> bool:
    """A deposit is collected online when the bot has a wallet (pay_ok) and this is not a reschedule of a paid booking."""
    d = session["data"]
    return bool(block.deposit and session.get("pay_ok") and not d.get("paid") and not d.get("_replace"))


def _await_deposit(spec, session, block: BookingBlock, store, now):
    """Hold the place and ask for the deposit; the booking is confirmed (and the owner told) only once it is paid."""
    d = session["data"]
    row = store.add(block.id, {**d, "status": "awaiting_payment", "total": block.deposit, **_ident(session, now)})
    text = fa_digits(f"بیعانه‌ی نوبت «{row.get('slot_label', block.title)}»: {block.deposit:,} تومان\n"
                     f"برای قطعی شدن نوبت، تا {PAY_WINDOW_MINUTES} دقیقه پرداخت کنید؛ پس از آن، نوبت آزاد می‌شود.")
    if session.get("pay_sim"):
        actions = [send(text + "\n(پرداخت آزمایشی؛ در بله فاکتور واقعی ارسال می‌شود)", [_btn("💳 پرداخت (آزمایشی)", f"pay:{row['id']}")])]
    else:
        actions = [{"type": "invoice", "rid": row["id"], "amount": block.deposit, "title": f"بیعانه نوبت {row['id']}"[:32], "text": text}]
    _reset(session)
    actions.append(menu_actions(spec))
    return actions


def mark_paid(spec: BotSpec, store, now, block, row: dict, charge: str = "") -> list[dict]:
    """Payment arrived: an order becomes a normal new order, a booking's deposit confirms it; the owner finds out.
    Idempotent (a repeated delivery does nothing)."""
    if row.get("status") != "awaiting_payment":
        return []
    if block.type == "booking":
        store.update(block.id, row["id"], status="confirmed", paid=True, _paid_at=now.isoformat(), _charge=charge)
        row = {**row, "status": "confirmed", "paid": True}
        actions = [send(f"✅ بیعانه پرداخت شد. {_fill(block.confirm_text, row)}")]
        _notify(spec, block.id, f"[confirmed · بیعانه پرداخت‌شده ✅] " + _summary(row), actions)
        actions += _staff_notice(row, f"📅 نوبت تازه برای شما · {block.title}\n{_summary(row)}")
        return actions
    store.update(block.id, row["id"], status="new", paid=True, _paid_at=now.isoformat(), _charge=charge)
    actions = [send(f"✅ پرداخت انجام شد. {block.confirm_text}\nشماره‌ی سفارش: {row['id']}")]
    _notify(spec, block.id, f"سفارش #{row['id']} - {row['total']:,} تومان (پرداخت‌شده ✅)\n{_order_lines(row)}"
            + (f"\nمحل ارسال: {row['delivery_zone']}" if row.get("delivery_zone") else ""), actions, total=row.get("total"))
    return actions


def _test_pay(spec, session, rid: int, store, now):
    cust = session.get("cust")
    for b in spec.blocks:
        if (b.type == "catalog_order" and b.payment == "online") or (b.type == "booking" and b.deposit):
            rows = store.find(b.id, id=rid, _cust=cust) if cust else []
            if rows:
                out = mark_paid(spec, store, now, b, rows[0], "test")
                if out:
                    out.append(menu_actions(spec))
                    return out
    return [send("این پرداخت دیگر معتبر نیست."), menu_actions(spec)]


def expire_unpaid(spec: BotSpec, store, now) -> list[dict]:
    """Cancel orders whose payment window ran out (stock and discount-code use come back). Returns the customer notices."""
    actions: list[dict] = []
    for b in spec.blocks:
        if b.type == "catalog_order" and b.payment == "card":  # card-to-card: no receipt in time
            for r in store.find(b.id, status="awaiting_transfer"):
                try:
                    placed = datetime.fromisoformat(r.get("_at", ""))
                except ValueError:
                    continue
                if now - placed > timedelta(minutes=b.card_wait_minutes):
                    cancel_record(spec, store, now, b, r, by="system")
                    if r.get("_cust"):
                        actions.append({"type": "notify_customer", "cust": r["_cust"],
                                        "text": f"رسید واریز سفارش {r['id']} به موقع نرسید و سفارش لغو شد. برای سفارش دوباره از منو اقدام کنید."})
            continue
        if not ((b.type == "catalog_order" and b.payment == "online") or (b.type == "booking" and b.deposit)):
            continue
        for r in store.find(b.id, status="awaiting_payment"):
            try:
                placed = datetime.fromisoformat(r.get("_at", ""))
            except ValueError:
                continue
            if now - placed > timedelta(minutes=PAY_WINDOW_MINUTES):
                cancel_record(spec, store, now, b, r, by="system")
                if r.get("_cust"):
                    what = f"بیعانه‌ی نوبت «{r.get('slot_label', b.title)}» تمام شد و نوبت آزاد شد. برای رزرو دوباره" if b.type == "booking" else f"سفارش {r['id']} تمام شد و سفارش لغو شد. برای سفارش دوباره"
                    actions.append({"type": "notify_customer", "cust": r["_cust"], "text": f"مهلت پرداخت {what} از منو اقدام کنید."})
    return actions


def reminder_buttons(spec: BotSpec, b, r: dict) -> list[dict]:
    """«می‌آیم» / «نمی‌توانم بیایم» under a booking reminder (data carries the block index and record id)."""
    if not b.reminder_confirm:
        return []
    bi = next(i for i, x in enumerate(spec.blocks) if x.id == b.id)
    return [_btn("✅ می‌آیم", f"rc:y:{bi}:{r['id']}"), _btn("❌ نمی‌توانم بیایم", f"rc:n:{bi}:{r['id']}")]


def _attendance(spec: BotSpec, session, store, now, coming: bool, bi: int, rid: int) -> list:
    """The customer answered a reminder. «No» cancels and frees the place, unless the cancellation deadline has
    passed: then the booking stays and the owner is told the customer will not come."""
    b = spec.blocks[bi] if 0 <= bi < len(spec.blocks) else None
    rows = store.find(b.id, id=rid, _cust=session.get("cust")) if b is not None and b.type == "booking" and session.get("cust") else []
    r = rows[0] if rows else None
    start = booking_start(b, r, now.tzinfo) if r else None
    if r is None or r.get("status") != "confirmed" or (start and now >= start):
        return [send("این نوبت دیگر فعال نیست."), menu_actions(spec)]
    if coming:
        store.update(b.id, rid, attend="yes")
        return [send("ممنون! منتظرتان هستیم."), menu_actions(spec)]
    store.update(b.id, rid, attend="no")
    why = _why_not(b, r, now)
    if why:
        actions = [send("ممنون که خبر دادید. " + why)]
        _notify(spec, b.id, _summary(r), actions, prefix=f"⚠️ مشتری اعلام کرد نمی‌تواند بیاید (مهلت لغو گذشته) · {b.title}")
        return [*actions, menu_actions(spec)]
    actions, _ = cancel_record(spec, store, now, b, r, by="customer")
    return [send("نوبت شما لغو شد؛ ممنون که خبر دادید."), *actions, menu_actions(spec)]


def _why_not(b, r: dict, now) -> str | None:
    """None = may cancel now; otherwise a polite Persian reason."""
    if b.type == "booking":
        if r.get("paid"):
            return "بیعانه‌ی این نوبت پرداخت شده است؛ برای لغو و بازگشت وجه با مدیر تماس بگیرید."
        if b.cancel_deadline_hours and r.get("date"):
            slot = next((s for s in b.slots if s.id == r.get("slot")), None)
            hhmm = r.get("time") or (slot.time if slot else None)  # appointments carry their own time
            if hhmm:
                h, m = (int(x) for x in hhmm.split(":"))
                start = datetime.combine(date.fromisoformat(r["date"]), time(h, m), tzinfo=now.tzinfo)
                if now >= start - timedelta(hours=b.cancel_deadline_hours):
                    return f"لغو فقط تا {b.cancel_deadline_hours} ساعت پیش از شروع ممکن است و این مهلت گذشته است. لطفاً با مدیر تماس بگیرید."
        return None
    if r.get("paid"):
        return "این سفارش پرداخت شده است؛ برای لغو و بازگشت وجه با مدیر تماس بگیرید."
    try:
        placed = datetime.fromisoformat(r.get("_at", ""))
    except ValueError:
        return "این سفارش دیگر قابل لغو نیست."
    if now - placed > timedelta(minutes=b.cancel_window_minutes):
        return f"لغو سفارش فقط تا {b.cancel_window_minutes} دقیقه پس از ثبت ممکن است. برای تغییر با مدیر تماس بگیرید."
    return None


def _owned(spec: BotSpec, session: dict, store, bi: int, rid: int):
    """The record only if it belongs to THIS customer and its block allows cancelling (never trust ids from the client)."""
    cust = session.get("cust")
    if not cust or not 0 <= bi < len(spec.blocks):
        return None
    b = spec.blocks[bi]
    if b.type not in ("booking", "catalog_order") or not b.allow_cancel:
        return None
    rows = store.find(b.id, id=rid, _cust=cust)
    return (b, rows[0]) if rows else None


def _my_start(spec, session, store, now):
    cust = session.get("cust")
    found = []
    if cust:
        for bi, b in _cancel_blocks(spec):
            found += [(bi, b, r) for r in store.find(b.id, _cust=cust) if _active(b, r, now)]
    progress = []
    if cust:
        for _, b in _cancel_blocks(spec):
            if b.type == "catalog_order":  # orders the shop has already started on can't be cancelled here, but the customer can follow them
                progress += [f"سفارش {r['id']} — {STATUS_FA[r['status']]}" for r in store.find(b.id, _cust=cust) if r.get("status") in ("preparing", "ready")]
    if not found:
        _reset(session)
        return [send("\n".join(["هنوز ثبت قابل لغوی ندارید." if progress else "هنوز ثبت فعالی ندارید.", *progress])), menu_actions(spec)]
    found.sort(key=lambda t: t[2]["id"], reverse=True)
    session.update(block=MY_BLOCK, step="list", data={})
    buttons = [_btn("لغو: " + _short(_describe(b, r), 50), f"x:{bi}:{r['id']}") for bi, b, r in found[:8]]
    head = "ثبت‌های فعال شما؛ برای لغو یا تغییر، مورد دلخواه را انتخاب کنید:" + ("".join("\n" + p for p in progress))
    return [send(head, buttons + [_btn("بازگشت به منو", "/menu")])]


def _my_choices(b):
    return [_btn("بله، لغو شود", "xy")] + ([_btn("🔄 تغییر زمان", "xr")] if b is not None and b.type == "booking" else []) + [_btn("خیر، بماند", "xn")]


def _mine(spec, session, text, store, now):
    text_n = norm(text)
    d = session["data"]
    if session["step"] == "list":
        m = re.fullmatch(r"x:(\d+):(\d+)", text_n)
        owned = _owned(spec, session, store, int(m.group(1)), int(m.group(2))) if m else None
        if owned is None:
            return [send("لطفاً یکی از موارد را انتخاب کنید یا به منو برگردید.")] + _my_start(spec, session, store, now)
        b, r = owned
        why = _why_not(b, r, now)
        if why:
            return [send(why)] + _my_start(spec, session, store, now)
        d.update(bi=int(m.group(1)), rid=r["id"])
        session["step"] = "confirm"
        ask = "لغو شود یا زمانش تغییر کند؟" if b.type == "booking" else "لغو شود؟"
        return [send(f"«{_describe(b, r)}» {ask}", _my_choices(b))]
    # confirm
    if text_n == "xr":
        owned = _owned(spec, session, store, d["bi"], d["rid"])
        why = _why_not(owned[0], owned[1], now) if owned else "این مورد دیگر قابل تغییر نیست."
        if owned is None or owned[0].type != "booking" or not _active(owned[0], owned[1], now) or why:
            _reset(session)
            return [send(why or "این مورد دیگر قابل تغییر نیست."), menu_actions(spec)]
        b, r = owned
        if b.schedule:
            out = _appt_start(spec, session, b, store, now)
        else:
            session.update(block=b.id, step="slot", data={})
            out = [send(b.title), _slot_prompt(b, store, now)]
        session["data"]["_replace"] = r["id"]
        return out
    if text_n == "xn":
        _reset(session)
        return [send("ثبت شما بدون تغییر باقی ماند."), menu_actions(spec)]
    if text_n != "xy":
        owned = _owned(spec, session, store, d["bi"], d["rid"])
        return [send("لطفاً یکی از دکمه‌ها را بزنید."), send("چه کاری انجام شود؟", _my_choices(owned[0] if owned else None))]
    owned = _owned(spec, session, store, d["bi"], d["rid"])
    if owned is None or not _active(owned[0], owned[1], now):
        _reset(session)
        return [send("این مورد دیگر قابل لغو نیست."), menu_actions(spec)]
    b, r = owned
    why = _why_not(b, r, now)
    if why:
        _reset(session)
        return [send(why), menu_actions(spec)]
    return _do_cancel(spec, session, store, now, b, r)


def cancel_record(spec: BotSpec, store, now, b, r: dict, by: str = "customer", reason: str = "") -> tuple[list[dict], dict | None]:
    """THE cancellation rules, shared by the customer flow and the owner dashboard:
    mark cancelled, free the place (booking) or put the stock back (table order), promote the first person waiting
    for the same date, and tell whoever needs to know. Returns (actions, promoted_record)."""
    prev = r["status"]
    store.update(b.id, r["id"], status="cancelled", _cancelled_at=now.isoformat(), _cancelled_by=by)
    actions: list[dict] = []
    if by == "customer":
        _notify(spec, b.id, _summary(r), actions, prefix=f"❌ لغو توسط مشتری · {b.title}")
    if b.type == "booking":
        actions += _staff_notice(r, f"❌ نوبت {'توسط مشتری' if by == 'customer' else 'توسط مدیر'} لغو شد · {b.title}\n{_summary(r)}")
    promoted = None
    if b.type == "booking":
        if prev == "confirmed":  # a place just opened: the first person waiting for the SAME date gets it
            where = {"slot": r.get("slot"), "status": "waitlisted"}
            if r.get("date"):
                where["date"] = r["date"]
            waiting = sorted(store.find(b.id, **where), key=lambda w: w["id"])
            slot = next((s for s in b.slots if s.id == r.get("slot")), None)
            left = _remaining(b, slot, store, date.fromisoformat(r["date"]) if r.get("date") else None) if slot else 1
            for w in waiting:  # in order; a group is promoted only when all of it fits
                if _party(w) > left:
                    continue
                left -= _party(w)
                store.update(b.id, w["id"], status="confirmed", _promoted_at=now.isoformat())
                promoted = promoted or w
                if w.get("_cust"):
                    actions.append({"type": "notify_customer", "cust": w["_cust"],
                                    "text": f"🎉 جای خالی شد! ثبت‌نام شما در «{w.get('slot_label', b.title)}» تأیید شد."})
                if by == "customer":
                    _notify(spec, b.id, _summary(w), actions, prefix=f"✅ از لیست انتظار تأیید شد · {b.title}")
                if left <= 0:
                    break
    elif b.source == "table":
        store.release(b.id, [(it["id"], it.get("qty", 1)) for it in r.get("items", [])])
    if by == "owner" and r.get("_cust"):
        what = f"ثبت‌نام شما در «{r.get('slot_label', b.title)}»" if b.type == "booking" else "سفارش شما"
        actions.append({"type": "notify_customer", "cust": r["_cust"],
                        "text": f"متأسفانه {what} توسط مدیر لغو شد." + (f"\nدلیل: {reason.strip()}" if reason.strip() else "")})
    return actions, promoted


def mark_no_show(store, now, b, r: dict) -> list[dict]:
    """The owner marks a confirmed booking whose time has come as «حاضر نشد» (counts toward no_show_limit)."""
    if b.type != "booking" or r.get("status") != "confirmed":
        raise ValueError("فقط نوبت تأییدشده را می‌توان «حاضر نشد» علامت زد.")
    start = booking_start(b, r, now.tzinfo)
    if start is not None and now < start:
        raise ValueError("هنوز زمان این نوبت نرسیده است.")
    store.update(b.id, r["id"], status="no_show", _no_show_at=now.isoformat())
    return []


def set_order_status(store, now, b, r: dict, status: str) -> list[dict]:
    """Owner moves an order forward (preparing -> ready -> done). Returns the customer notification, if any."""
    if b.type != "catalog_order":
        raise ValueError("وضعیت فقط برای سفارش‌ها قابل تغییر است.")
    cur = r.get("status")
    if cur == "awaiting_payment":
        raise ValueError("این سفارش هنوز پرداخت نشده است.")
    if cur in ("awaiting_transfer", "transfer_sent"):
        raise ValueError("ابتدا واریز کارت‌به‌کارت این سفارش را تأیید کنید.")
    if cur in ("cancelled", "done"):
        raise ValueError("این سفارش بسته شده و دیگر قابل تغییر نیست.")
    if status not in ORDER_FLOW[1:]:
        raise ValueError("وضعیت نامعتبر است.")
    forward = ORDER_FLOW.index(status) > ORDER_FLOW.index(cur) if cur in ORDER_FLOW else True
    store.update(b.id, r["id"], status=status, **{f"_{status}_at": now.isoformat()})
    note = {"preparing": "سفارش شما در حال آماده‌سازی است.", "ready": "✅ سفارش شما آماده است."}.get(status)
    if forward and note and r.get("_cust"):
        return [{"type": "notify_customer", "cust": r["_cust"], "text": note}]
    return []  # moving backwards (a correction) or closing the order never spams the customer


def _do_cancel(spec, session, store, now, b, r):
    actions, _ = cancel_record(spec, store, now, b, r, by="customer")
    done = f"ثبت‌نام شما در «{r.get('slot_label', b.title)}» لغو شد." if b.type == "booking" else "سفارش شما لغو شد."
    _reset(session)
    return [send(done), *actions, menu_actions(spec)]
