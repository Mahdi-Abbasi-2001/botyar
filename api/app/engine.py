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
from .spec import PLACEHOLDER, norm_code, BotSpec, BookingBlock, CatalogOrderBlock, ContactBlock, FaqBlock, FeedbackBlock, MenuBlock, QuizBlock, FormBlock, FormField, MessageBlock

log = logging.getLogger("botyar.engine")
STALE_RESETS = {"count": 0}  # tests assert this stays 0 unless a bot really changed under a conversation
MY_LABEL = "ثبت‌های من"  # built-in menu entry, present when a block allows cancelling
MY_BLOCK = "__my__"
STATUS_FA = {"confirmed": "تأیید شده", "waitlisted": "در لیست انتظار", "new": "سفارش جدید", "preparing": "در حال آماده‌سازی", "ready": "آماده", "done": "تحویل داده شد", "cancelled": "لغو شده", "unanswered": "بدون پاسخ", "awaiting_payment": "در انتظار پرداخت", "handled": "رسیدگی شد"}
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


class MemoryStore:
    def __init__(self):
        self.rows: dict[str, list[dict]] = {}
        self.catalog: dict[str, list[dict]] = {}

    def load_catalog(self, block_id: str, products: list[dict]):
        self.catalog[block_id] = [{**p, "id": i} for i, p in enumerate(products, 1)]

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
        if re.fullmatch(r"\d+", value):
            return True, int(value), ""
        return False, None, "لطفاً فقط عدد وارد کنید."
    if field.kind == "choice":
        for c in field.choices:
            if c == raw.strip() or norm(c) == value:
                return True, c, ""
        return False, None, "لطفاً یکی از گزینه‌ها را انتخاب کنید."
    return True, raw.strip(), ""


def _ask(field: FormField):
    if field.kind == "choice":
        return send(field.label, [_btn(c) for c in field.choices])
    return send(field.label)


def menu_actions(spec: BotSpec, prefix: str | None = None):
    text = prefix if prefix is not None else "از منوی زیر یکی را انتخاب کنید:"
    buttons = [_btn(m.label, f"m:{i}") for i, m in enumerate(spec.menu)]
    if _cancel_blocks(spec):
        buttons.append(_btn(MY_LABEL, f"m:{len(spec.menu)}"))
    return send(text, buttons)


def _reset(session):
    session.update(block=None, step=None, data={})


def _notify(spec: BotSpec, block_id: str, summary: str, actions: list, prefix: str | None = None):
    for b in spec.blocks:
        if b.type == "admin_notify" and b.on == block_id:
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


def handle(spec: BotSpec, session: dict, text: str, store: Store, now=None, matcher=None, rng=None) -> list[dict]:
    now = now or dates.now_tehran()  # injectable so tests run on a fixed clock
    rng = rng or _RNG
    text_n = norm(text)
    if text_n in MENU_WORDS:
        _reset(session)
        return [send(spec.welcome), menu_actions(spec)]
    if text_n in CANCEL_WORDS:
        _reset(session)
        return [menu_actions(spec, "انصراف انجام شد.")]

    m = re.fullmatch(r"pay:(\d+)", text_n)
    if m and session.get("pay_sim"):  # test payment button: the simulator and the agent's tests only, never a real chat
        return _test_pay(spec, session, int(m.group(1)), store, now)

    if session["block"] is None:
        return _from_menu(spec, session, text_n, store, now, rng)

    try:
        if session["block"] == MY_BLOCK:
            return _mine(spec, session, text, store, now)
        block = spec.block(session["block"])
        if block.type == "form":
            return _form(spec, session, block, text, store)
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
    except (StopIteration, IndexError, KeyError) as e:
        # The saved state belongs to an older version of the bot (the owner republished mid-conversation:
        # a block, field, slot or option it points to is gone). Never leave the customer in silence.
        STALE_RESETS["count"] += 1
        log.warning("stale chat state reset (%s: %s)", type(e).__name__, e)
        _reset(session)
        return [menu_actions(spec, "ربات همین الان به‌روزرسانی شد، برای همین باید از اول شروع کنیم. از منوی زیر ادامه دهید:")]
    _reset(session)
    return [menu_actions(spec)]


# ---------- menu ----------
def _from_menu(spec, session, text_n, store, now, rng=_RNG):
    if _cancel_blocks(spec) and (text_n == f"m:{len(spec.menu)}" or text_n == MY_LABEL):
        return _my_start(spec, session, store, now)
    item = None
    m = re.fullmatch(r"m:(\d+)", text_n)
    if m and int(m.group(1)) < len(spec.menu):
        item = spec.menu[int(m.group(1))]
    else:
        item = next((i for i in spec.menu if i.label == text_n), None)
    if item is None:
        return [menu_actions(spec, "متوجه نشدم. لطفاً از منو انتخاب کنید:")]
    return _start_block(spec, session, spec.block(item.block), store, now, rng)


def _start_block(spec, session, block, store, now, rng):
    """Begin a block (reached from the main menu or from a sub-menu)."""
    if block.type == "message":
        return [send(pick_text(block, session, rng)), menu_actions(spec)]
    session.update(block=block.id, step=0, data={})
    if block.type == "menu":
        session["step"] = "pick"
        return [_submenu_prompt(block)]
    if block.type == "quiz":
        session["data"] = {"score": 0}
        return [send(block.title), _quiz_question(block, 0)]
    if block.type == "form":
        return [send(block.title), _ask(block.fields[0])]
    if block.type == "faq":
        return _faq_start(session, block)
    if block.type == "feedback":
        session.update(block=block.id, step="rate", data={})
        return [send(block.title), _rate_prompt(block)]
    if block.type == "contact":
        session.update(block=block.id, step="msg", data={})
        return [send(block.title), send(block.prompt_text, _faq_nav())]
    if block.type == "booking" and block.schedule:
        return _appt_start(spec, session, block, store, now)
    if block.type == "booking":
        session["step"] = "slot"
        return [send(block.title), _slot_prompt(block, store, now)]
    if block.type == "catalog_order":
        return _order_start(spec, session, block, store)
    return [menu_actions(spec)]


# ---------- form ----------
def _fill(text: str, data: dict) -> str:
    """Put the customer's own answers into a confirmation text ({name} -> what they typed)."""
    return PLACEHOLDER.sub(lambda m: str(data.get(m.group(1), m.group(0))), text)


def _form(spec, session, block: FormBlock, text, store):
    idx = session["step"]
    field = block.fields[idx]
    ok, value, err = validate(field, text)
    if not ok:
        return [send(err), _ask(field)]
    session["data"][field.key] = value
    if idx + 1 < len(block.fields):
        session["step"] = idx + 1
        return [_ask(block.fields[idx + 1])]
    row = store.add(block.id, dict(session["data"]))
    actions = [send(_fill(block.done_text, row))]
    _notify(spec, block.id, _summary(row), actions)
    _reset(session)
    actions.append(menu_actions(spec))
    return actions


# ---------- booking ----------
def _remaining(block: BookingBlock, slot, store, day=None):
    """Free places. A weekly slot is counted per date (so it resets by itself); a one-off slot counts for ever."""
    where = {"slot": slot.id, "status": "confirmed"}
    if day is not None:
        where["date"] = day.isoformat()
    return slot.capacity - store.count(block.id, **where)


def _options(block: BookingBlock, now):
    """Everything the customer can pick right now: (slot, date-or-None, button data, display name)."""
    out = []
    for s in block.slots:
        days = dates.next_occurrences(now, s.weekday, s.time, block.occurrences) if s.weekday is not None else [None]
        for day in days:
            name = s.label + (f" — {dates.jalali_str(day)}" if day else "")
            out.append((s, day, f"s:{s.id}" + (f"@{day:%Y%m%d}" if day else ""), name))
    return out


def _slot_prompt(block: BookingBlock, store, now):
    buttons = []
    for s, day, data, name in _options(block, now):
        left = _remaining(block, s, store, day)
        if left > 0:
            buttons.append(_btn(f"{name} ({left} جای خالی)", data))
        elif block.waitlist:
            buttons.append(_btn(f"{name} (تکمیل - لیست انتظار)", data))
        else:
            buttons.append(_btn(f"{name} (تکمیل)", data))
    return send("زمان مورد نظر را انتخاب کنید:", buttons)


def _booking(spec, session, block: BookingBlock, text, store, now):
    text_n = norm(text)
    if block.schedule:
        return _appt(spec, session, block, text, store, now)
    if session["step"] == "slot":
        opts = _options(block, now)
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
        return _after_pick(spec, session, block, store, now)
    idx = session["step"]
    field = block.fields[idx]
    ok, value, err = validate(field, text)
    if not ok:
        return [send(err), _ask(field)]
    session["data"][field.key] = value
    if idx + 1 < len(block.fields):
        session["step"] = idx + 1
        return [_ask(block.fields[idx + 1])]
    return _commit_slot(spec, session, block, store, now)


def _commit_slot(spec, session, block: BookingBlock, store, now):
    slot = next(s for s in block.slots if s.id == session["data"]["slot"])
    day = date.fromisoformat(session["data"]["date"]) if "date" in session["data"] else None
    # re-check capacity at commit time (another customer may have taken the last place meanwhile)
    full = _remaining(block, slot, store, day) <= 0
    if full and not block.waitlist:
        _reset(session)
        return [send(block.full_text), menu_actions(spec)]
    if full and session["data"].get("_replace"):  # the date filled up while the customer was choosing: keep the old place
        session["step"] = "slot"
        return [send(block.full_text), _slot_prompt(block, store, now)]
    status = "waitlisted" if full else "confirmed"
    row = store.add(block.id, {**session["data"], "status": status, **_ident(session, now)})
    actions = _finish_booking(spec, session, block, store, now, row, status, block.waitlist_text if full else block.confirm_text)
    return actions


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
        return _commit_appt(spec, session, block, store, now) if block.schedule else _commit_slot(spec, session, block, store, now)
    session["step"] = 0
    return [_ask(block.fields[0])]


# ---------- appointments generated from working hours (booking block with a `schedule`) ----------
PAGE_TIMES = 8


def _hm(t: str) -> int:
    return int(t[:2]) * 60 + int(t[3:])


def _fmt(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _appt_times(block: BookingBlock, day: date, now) -> list[str]:
    """Every start time of that day that is still in the future and does not collide with the daily break."""
    sch, out = block.schedule, []
    for w in sch.days:
        if w.weekday != dates.persian_weekday(day):
            continue
        t = _hm(w.start)
        while t + sch.duration_minutes <= _hm(w.end):
            in_break = sch.break_start and t < _hm(sch.break_end) and t + sch.duration_minutes > _hm(sch.break_start)
            if not in_break and datetime.combine(day, time(t // 60, t % 60), tzinfo=now.tzinfo) > now:
                out.append(_fmt(t))
            t += sch.duration_minutes
    return out


def _appt_free(block: BookingBlock, store, staff: str, day: date, hhmm: str) -> int:
    where = {"slot": "appt", "status": "confirmed", "date": day.isoformat(), "time": hhmm}
    if staff:
        where["staff"] = staff
    return block.schedule.capacity - store.count(block.id, **where)


def _appt_free_times(block, store, staff, day, now) -> list[str]:
    return [t for t in _appt_times(block, day, now) if _appt_free(block, store, staff, day, t) > 0]


def _appt_days(block, store, staff, now) -> list[tuple[date, int]]:
    out = []
    for i in range(block.schedule.days_ahead + 1):
        day = now.date() + timedelta(days=i)
        n = len(_appt_free_times(block, store, staff, day, now))
        if n:
            out.append((day, n))
    return out


def _appt_label(day: date, hhmm: str | None = None, staff: str = "") -> str:
    base = f"{dates.WEEKDAYS[dates.persian_weekday(day)]} {dates.jalali_str(day)}" + (f" ساعت {hhmm}" if hhmm else "")
    return base + (f" — {staff}" if staff else "")


def _appt_start(spec, session, block, store, now):
    session.update(block=block.id, step="day", data={})
    if block.schedule.staff:
        session["step"] = "staff"
        return [send(block.title), send("با چه کسی؟", [_btn(n, f"f:{i}") for i, n in enumerate(block.schedule.staff)])]
    return _appt_day_prompt(spec, session, block, store, now, [send(block.title)])


def _appt_day_prompt(spec, session, block, store, now, head=()):
    staff = session["data"].get("staff", "")
    days = _appt_days(block, store, staff, now)
    if not days:
        _reset(session)
        return [*head, send("در حال حاضر نوبت خالی وجود ندارد. لطفاً بعداً دوباره سر بزنید."), menu_actions(spec)]
    session["step"] = "day"
    buttons = [_btn(f"{_appt_label(d)} ({n} نوبت خالی)", f"d:{d:%Y%m%d}") for d, n in days]
    return [*head, send("روز مورد نظر را انتخاب کنید:", buttons)]


def _appt_time_prompt(block, store, session, now, page=0, edit=False):
    d = session["data"]
    day = date.fromisoformat(d["date"])
    times = _appt_free_times(block, store, d.get("staff", ""), day, now)
    pages = max(1, math.ceil(len(times) / PAGE_TIMES))
    page = min(max(page, 0), pages - 1)
    buttons = [_btn(t, f"t:{t.replace(':', '')}") for t in times[page * PAGE_TIMES:(page + 1) * PAGE_TIMES]]
    if page > 0:
        buttons.append(_btn("‹ قبلی", f"tp:{page - 1}"))
    if page + 1 < pages:
        buttons.append(_btn("بعدی ›", f"tp:{page + 1}"))
    buttons.append(_btn("بازگشت به انتخاب روز", "back"))
    session["step"] = "time"
    head = f"ساعت مورد نظر برای {_appt_label(day, None, d.get('staff', ''))}" + (f" — صفحه {page + 1} از {pages}" if pages > 1 else "") + ":"
    return send(head, buttons, edit)


def _appt(spec, session, block: BookingBlock, text, store, now):
    text_n = norm(text)
    d = session["data"]
    step = session["step"]
    sch = block.schedule

    if step == "staff":
        m = re.fullmatch(r"f:(\d+)", text_n)
        idx = int(m.group(1)) if m else next((i for i, n in enumerate(sch.staff) if fa_norm(n) == fa_norm(text_n)), -1)
        if not 0 <= idx < len(sch.staff):
            return [send("لطفاً یکی از گزینه‌ها را انتخاب کنید."), send("با چه کسی؟", [_btn(n, f"f:{i}") for i, n in enumerate(sch.staff)])]
        d["staff"] = sch.staff[idx]
        return _appt_day_prompt(spec, session, block, store, now)

    if step == "day":
        m = re.fullmatch(r"d:(\d{8})", text_n)
        offered = {f"{x:%Y%m%d}": x for x, _ in _appt_days(block, store, d.get("staff", ""), now)}
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
        if not hhmm or hhmm not in _appt_free_times(block, store, d.get("staff", ""), day, now):
            return [send("این ساعت دیگر خالی نیست. لطفاً ساعت دیگری انتخاب کنید."), _appt_time_prompt(block, store, session, now)]
        d["time"] = hhmm
        d["slot"] = "appt"
        d["slot_label"] = _appt_label(day, hhmm, d.get("staff", ""))
        return _after_pick(spec, session, block, store, now)

    # contact fields
    idx = step
    field = block.fields[idx]
    ok, value, err = validate(field, text)
    if not ok:
        return [send(err), _ask(field)]
    d[field.key] = value
    if idx + 1 < len(block.fields):
        session["step"] = idx + 1
        return [_ask(block.fields[idx + 1])]
    return _commit_appt(spec, session, block, store, now)


def _commit_appt(spec, session, block: BookingBlock, store, now):
    d = session["data"]
    day = date.fromisoformat(d["date"])
    if _appt_free(block, store, d.get("staff", ""), day, d["time"]) <= 0:  # someone took it while this customer was typing
        d.pop("time", None)
        return [send(block.full_text), _appt_time_prompt(block, store, session, now)]
    row = store.add(block.id, {**d, "status": "confirmed", **_ident(session, now)})
    return _finish_booking(spec, session, block, store, now, row, "confirmed", block.confirm_text)


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


def _order_start(spec, session, block: CatalogOrderBlock, store):
    d: dict = {"_cart": []}
    session.update(block=block.id, step="item", data=d)
    if not _is_table(block):
        return [send(block.title), _item_prompt(block)]
    if store.products(block.id, None, None, 0, 1)[1] == 0:
        _reset(session)
        return [send(block.title), send("فعلاً محصولی ثبت نشده است."), menu_actions(spec)]
    if len(store.categories(block.id)) > 1:
        session["step"] = "cat"
        return [send(block.title), _cat_prompt(block, store)]
    session["step"], d["_page"] = "list", 0
    return [send(block.title), _list_prompt(block, store, d)]


def _cart_total(cart):
    return sum(c["price"] * c.get("qty", 1) for c in cart)


def _price(block: CatalogOrderBlock, subtotal: int, code) -> dict:
    """goods - discount + delivery. Delivery is free once the goods total AFTER the discount reaches free_delivery_over."""
    disc = 0
    if code is not None:
        disc = min(subtotal, round(subtotal * code.percent / 100) if code.percent else code.amount)
    goods = subtotal - disc
    fee = 0 if (block.free_delivery_over and goods >= block.free_delivery_over) else block.delivery_fee
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


def _code_prompt():
    return send("کد تخفیف دارید؟ آن را بنویسید، وگرنه «ندارم» را بزنید.", [_btn("ندارم", "dc:no")])


def _more_prompt():
    return send("آیتم دیگری اضافه می‌کنید؟", [_btn("افزودن آیتم دیگر", "more"), _btn("ثبت سفارش", "checkout")])


def _qty_prompt(pend):
    return send("تعداد را انتخاب کنید (یا عدد بنویسید):", [_btn(str(n), f"n:{n}") for n in (1, 2, 3)])


def _next_option(session, block):
    d = session["data"]
    groups = d["_pending"]["_groups"]
    i = d.get("_opt_idx", 0)
    if i < len(groups):
        session["step"] = "option"
        name, choices = groups[i]
        return [send(name, [_btn(c) for c in choices])]
    d.pop("_opt_idx", None)
    if _is_table(block):
        session["step"] = "qty"
        return [_qty_prompt(d["_pending"])]
    return _add_to_cart(session, block, 1)


def _add_to_cart(session, block, qty):
    d = session["data"]
    pend = d.pop("_pending")
    pend.pop("_groups", None)
    pend.pop("stock", None)
    if _is_table(block):
        pend["qty"] = qty
    session["step"] = "more"
    if len(d["_cart"]) + 1 > block.max_items:
        return [send(f"حداکثر {block.max_items} آیتم در هر سفارش مجاز است."), _more_prompt()]
    d["_cart"].append(pend)
    shown = f"«{pend['name']}»" + (f" × {qty}" if _is_table(block) else "")
    return [send(f"{shown} به سفارش اضافه شد."), _more_prompt()]


def _pick_product(session, block, store, pid):
    d = session["data"]
    p = store.product(block.id, pid)
    if p is None:
        return [send("این محصول دیگر موجود نیست."), _list_prompt(block, store, d)]
    in_cart = sum(c.get("qty", 1) for c in d.get("_cart", []) if c["id"] == p["id"])
    if p["stock"] is not None and p["stock"] <= 0:
        return [send(f"«{p['name']}» فعلاً موجود نیست."), _list_prompt(block, store, d)]
    if p["stock"] is not None and in_cart >= p["stock"]:
        return [send(f"همه‌ی موجودی «{p['name']}» ({p['stock']} عدد) همین الان در سبد شماست."), _list_prompt(block, store, d)]
    d["_pending"] = {"id": p["id"], "name": p["name"], "price": p["price"], "options": {}, "stock": p["stock"],
                     "_groups": [[o["name"], o["choices"]] for o in p["options"] if o["choices"]]}
    d["_opt_idx"] = 0
    return _next_option(session, block)


def _order(spec, session, block: CatalogOrderBlock, text, store, now):
    text_n = norm(text)
    d = session["data"]
    step = session["step"]
    table = _is_table(block)

    if step == "item":  # inline menu
        item = next((i for i in block.items if text_n == f"i:{i.id}" or text_n.startswith(i.name)), None)
        if item is None:
            return [send("لطفاً یکی از آیتم‌ها را انتخاب کنید."), _item_prompt(block)]
        d["_pending"] = {"id": item.id, "name": item.name, "price": item.price, "options": {},
                         "_groups": [[g.name, g.choices] for g in item.options]}
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
        name, choices = d["_pending"]["_groups"][d.get("_opt_idx", 0)]
        hit = next((c for c in choices if c == text.strip() or norm(c) == text_n), None)
        if hit is None:
            return [send("لطفاً یکی از گزینه‌ها را انتخاب کنید."), send(name, [_btn(c) for c in choices])]
        d["_pending"]["options"][name] = hit
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
            session["step"] = 0
            return [_ask(block.fields[0])]
        subtotal = _cart_total(d["_cart"])
        code = _find_code(block, text)
        err = _code_error(block, store, subtotal, code)
        if err:
            return [send(err), _code_prompt()]
        d["_code"] = code.code
        session["step"] = 0
        saved = _price(block, subtotal, code)["discount"]
        return [send(f"✅ کد تخفیف اعمال شد؛ {saved:,} تومان کمتر می‌پردازید."), _ask(block.fields[0])]

    if step == "more":
        if text_n == "more":
            if table:
                session["step"] = "list"
                return [_list_prompt(block, store, d)]
            session["step"] = "item"
            return [_item_prompt(block)]
        if text_n == "checkout":
            if not d["_cart"]:
                return [send("سبد سفارش خالی است."), _more_prompt()]
            if _cart_total(d["_cart"]) < block.min_total:
                return [send(f"حداقل مبلغ سفارش {block.min_total:,} تومان است. لطفاً آیتم بیشتری اضافه کنید."), _more_prompt()]
            d.pop("_code", None)
            if block.discount_codes:
                session["step"] = "code"
                return [_code_prompt()]
            session["step"] = 0
            return [_ask(block.fields[0])]
        return [_more_prompt()]

    # contact fields
    idx = step
    field = block.fields[idx]
    ok, value, err = validate(field, text)
    if not ok:
        return [send(err), _ask(field)]
    d[field.key] = value
    if idx + 1 < len(block.fields):
        session["step"] = idx + 1
        return [_ask(block.fields[idx + 1])]
    cart = d["_cart"]
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
    price = _price(block, subtotal, code)
    total = price["total"]
    contact = {f.key: d[f.key] for f in block.fields}
    extra = {"subtotal": subtotal, "discount": price["discount"], "discount_code": code.code if code else None, "delivery_fee": price["delivery_fee"]} if (code or dropped or block.delivery_fee or block.discount_codes) else {}
    online = block.payment == "online" and bool(session.get("pay_ok")) and total > 0
    row = store.add(block.id, {**contact, "items": cart, "total": total, "status": "awaiting_payment" if online else "new", **extra, **_ident(session, now)})
    lines = "\n".join(f"- {c['name']} {' '.join(c['options'].values())}".strip() + (f" × {c['qty']}" if "qty" in c else "") for c in cart)
    breakdown = ""
    if price["discount"] or price["delivery_fee"] or block.delivery_fee:
        breakdown = f"\nمبلغ کالاها: {subtotal:,} تومان"
        if price["discount"]:
            breakdown += f"\nتخفیف ({code.code}): {price['discount']:,} تومان"
        breakdown += f"\nهزینه ارسال: {price['delivery_fee']:,} تومان" if price["delivery_fee"] else "\nهزینه ارسال: رایگان"
    if dropped:
        breakdown += "\n⚠️ ظرفیت کد تخفیف در همین فاصله تمام شد و اعمال نشد."
    if online:  # the owner is notified when the money arrives, not when the cart is filled
        invoice_text = f"{lines}{breakdown}\nمبلغ قابل پرداخت: {total:,} تومان\nبرای ثبت نهایی سفارش، پرداخت را انجام دهید (تا {PAY_WINDOW_MINUTES} دقیقه فرصت دارید)."
        if session.get("pay_sim"):
            actions = [send(invoice_text + "\n(پرداخت آزمایشی؛ در بله فاکتور واقعی ارسال می‌شود)", [_btn("💳 پرداخت (آزمایشی)", f"pay:{row['id']}")])]
        else:
            actions = [{"type": "invoice", "rid": row["id"], "amount": total, "title": f"سفارش شماره {row['id']}"[:32], "text": invoice_text}]
        _reset(session)
        actions.append(menu_actions(spec))
        return actions
    if block.payment == "online" and not session.get("pay_ok"):
        breakdown += "\nپرداخت آنلاین هنوز برای این ربات فعال نشده؛ مدیر درباره‌ی پرداخت با شما هماهنگ می‌کند."
    actions = [send(f"{_fill(block.confirm_text, row)}\n{lines}{breakdown}\nجمع کل: {total:,} تومان")]
    _notify(spec, block.id, f"سفارش #{row['id']} - جمع {total:,} تومان" + (f" (کد {code.code})" if code else "") + f"\n{lines}", actions)
    _reset(session)
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


def _faq_list(block: FaqBlock, page: int, edit: bool = False):
    pages = max(1, math.ceil(len(block.entries) / FAQ_PAGE))
    page = min(max(page, 0), pages - 1)
    chunk = block.entries[page * FAQ_PAGE:(page + 1) * FAQ_PAGE]
    buttons = [_btn(_short(e.question, 50), f"fq:{page * FAQ_PAGE + k}") for k, e in enumerate(chunk)]
    if page > 0:
        buttons.append(_btn("‹ قبلی", f"fp:{page - 1}"))
    if page + 1 < pages:
        buttons.append(_btn("بعدی ›", f"fp:{page + 1}"))
    return send(f"فهرست سؤال‌ها — صفحه {page + 1} از {pages}", buttons + [_btn("بازگشت", "fa")], edit)


def _faq_answer(session, block: FaqBlock, i: int):
    session["data"]["_last_i"] = i
    return [send(block.entries[i].answer, [_btn("👍 مفید بود", "fh1"), _btn("👎 مفید نبود", "fh0"), _btn("سؤال دیگر", "fa")] + _faq_nav())]


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
    mp = re.fullmatch(r"fp:(\d+)", text_n)
    if mp:
        return [_faq_list(block, int(mp.group(1)), edit=True)]
    if text_n == "fa":
        return [_faq_prompt(block)]
    if text_n == "fh1":
        return [send("خوشحالم که کمک کرد 🌟", [_btn("سؤال دیگر", "fa")] + _faq_nav())]
    if text_n in ("fh0", "fn"):  # the answer did not help / none of the suggestions was right
        q = d.get("_last_q")
        if not q:
            return [_faq_prompt(block)]
        return _faq_unanswered(spec, session, block, store, now, q, note="پاسخ پیشنهادی کمک نکرد")
    query = text.strip()[:300]
    if len(query) < 2 or re.fullmatch(r"(?:fq|fp)(?::\S*)?|fh\d|fl|fa|fn", text_n):  # a stale / forged button is never a customer's question
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
def _submenu_prompt(block: MenuBlock):
    return send(block.title, [_btn(it.label, f"s:{n}") for n, it in enumerate(block.items)] + [_btn("بازگشت به منو", "/menu")])


def _submenu(spec, session, block: MenuBlock, text, store, now, rng):
    text_n = norm(text)
    m = re.fullmatch(r"s:(\d+)", text_n)
    if m and int(m.group(1)) < len(block.items):
        item = block.items[int(m.group(1))]
    else:
        item = next((i for i in block.items if fa_norm(i.label) == fa_norm(text_n)), None)
    if item is None:
        return [send("لطفاً یکی از گزینه‌ها را انتخاب کنید."), _submenu_prompt(block)]
    child = spec.block(item.block)
    if child.type == "message":  # reading a text keeps the customer in the sub-menu so they can browse its siblings
        return [send(pick_text(child, session, rng)), _submenu_prompt(block)]
    return _start_block(spec, session, child, store, now, rng)


# ---------- quiz ----------
def _quiz_question(block: QuizBlock, i: int):
    q = block.questions[i]
    return send(f"سؤال {i + 1} از {len(block.questions)}:\n{q.question}", [_btn(o, f"qa:{j}") for j, o in enumerate(q.options)] + [_btn("بازگشت به منو", "/menu")])


def _quiz(spec, session, block: QuizBlock, text, store, now):
    text_n, d, i = norm(text), session["data"], session["step"]
    q = block.questions[i]  # IndexError here = the quiz changed under a running customer: the stale-state guard resets
    m = re.fullmatch(r"qa:(\d+)", text_n)
    idx = int(m.group(1)) if m else next((j for j, o in enumerate(q.options) if fa_norm(o) == fa_norm(text_n)), -1)
    if not 0 <= idx < len(q.options):
        return [send("لطفاً یکی از گزینه‌ها را انتخاب کنید."), _quiz_question(block, i)]
    right = idx == q.correct
    d["score"] += int(right)
    actions = []
    if block.show_answers:
        actions.append(send("✅ درست!" if right else f"❌ نادرست. پاسخ درست: {q.options[q.correct]}"))
    if i + 1 < len(block.questions):
        session["step"] = i + 1
        return [*actions, _quiz_question(block, i + 1)]
    total, score = len(block.questions), d["score"]
    who = session.get("cust_name") or "مشتری"
    row = store.add(block.id, {"score": score, "total": total, "percent": round(100 * score / total), "who": who, "status": "done", **_ident(session, now)})
    actions.append(send(_fill(block.result_text, row)))
    _notify(spec, block.id, f"{who}: {score} از {total}", actions, prefix=f"🎯 نتیجه‌ی آزمون · {block.title}")
    _reset(session)
    actions.append(menu_actions(spec))
    return actions


# ---------- feedback (1-5 stars + optional comment) ----------
FEEDBACK_PER_DAY = 5


def _rate_prompt(block: FeedbackBlock):
    return send(block.prompt_text, [_btn("⭐" * n, f"r:{n}") for n in range(1, 6)] + [_btn("بازگشت به منو", "/menu")])


def _feedback(spec, session, block: FeedbackBlock, text, store, now):
    text_n, d = norm(text), session["data"]
    if session["step"] == "rate":
        m = re.fullmatch(r"r:([1-5])", text_n)
        if not m:
            return [send("لطفاً با یکی از دکمه‌ها امتیاز دهید."), _rate_prompt(block)]
        d["rating"], session["step"] = int(m.group(1)), "comment"
        return [send(block.comment_text, [_btn("رد کردن", "sk"), _btn("بازگشت به منو", "/menu")])]
    comment = "" if text_n == "sk" else text.strip()[:500]
    cust = session.get("cust")
    if cust:  # a customer can't flood the averages
        day_ago = now - timedelta(days=1)
        recent = sum(1 for r in store.find(block.id, _cust=cust) if datetime.fromisoformat(r["_at"]) > day_ago)
        if recent >= FEEDBACK_PER_DAY:
            _reset(session)
            return [send("امتیازهای امروز شما ثبت شده است؛ ممنون!"), menu_actions(spec)]
    row = store.add(block.id, {"rating": d["rating"], "comment": comment, "status": "new", **_ident(session, now)})
    actions = [send(block.thanks_text)]
    _notify(spec, block.id, f"{'⭐' * d['rating']}" + (f"\n{comment}" if comment else ""), actions, prefix=f"⭐ نظر جدید · {block.title}")
    _reset(session)
    actions.append(menu_actions(spec))
    return actions


# ---------- talk to the owner (messages go to the dashboard inbox; the owner's replies come back to this chat) ----------
CONTACT_MAX_CHARS, CONTACT_PER_HOUR = 1000, 20


def thread_id(cust: str | None) -> str:
    import hashlib

    return hashlib.sha1((cust or "anon").encode()).hexdigest()[:12]


def _contact(spec, session, block: ContactBlock, text, store, now):
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
    store.add(block.id, {"text": body, "from": "customer", "thread": thread_id(cust), "who": who, "status": "open", **_ident(session, now)})
    actions = [send(block.sent_text, _faq_nav())]
    _notify(spec, block.id, f"{who}: {body}\n(برای پاسخ، بخش «پیام‌ها» در پنل بات‌یار را باز کنید)", actions, prefix=f"📩 پیام جدید از مشتری · {block.title}")
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


PAY_WINDOW_MINUTES = 15


def _order_lines(r: dict) -> str:
    return "\n".join(f"- {c['name']} {' '.join(c['options'].values())}".strip() + (f" × {c['qty']}" if "qty" in c else "") for c in r.get("items", []))


def mark_paid(spec: BotSpec, store, now, block, row: dict, charge: str = "") -> list[dict]:
    """Payment arrived: the order becomes a normal new order and the owner finds out. Idempotent (a repeated delivery does nothing)."""
    if row.get("status") != "awaiting_payment":
        return []
    store.update(block.id, row["id"], status="new", paid=True, _paid_at=now.isoformat(), _charge=charge)
    actions = [send(f"✅ پرداخت انجام شد. {block.confirm_text}\nشماره‌ی سفارش: {row['id']}")]
    _notify(spec, block.id, f"سفارش #{row['id']} - {row['total']:,} تومان (پرداخت‌شده ✅)\n{_order_lines(row)}", actions)
    return actions


def _test_pay(spec, session, rid: int, store, now):
    cust = session.get("cust")
    for b in spec.blocks:
        if b.type == "catalog_order" and b.payment == "online":
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
        if b.type != "catalog_order" or b.payment != "online":
            continue
        for r in store.find(b.id, status="awaiting_payment"):
            try:
                placed = datetime.fromisoformat(r.get("_at", ""))
            except ValueError:
                continue
            if now - placed > timedelta(minutes=PAY_WINDOW_MINUTES):
                cancel_record(spec, store, now, b, r, by="system")
                if r.get("_cust"):
                    actions.append({"type": "notify_customer", "cust": r["_cust"], "text": f"مهلت پرداخت سفارش {r['id']} تمام شد و سفارش لغو شد. برای سفارش دوباره از منو اقدام کنید."})
    return actions


def _why_not(b, r: dict, now) -> str | None:
    """None = may cancel now; otherwise a polite Persian reason."""
    if b.type == "booking":
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
    head = "ثبت‌های فعال شما — برای لغو، روی مورد دلخواه بزنید:" + ("".join("\n" + p for p in progress))
    return [send(head, buttons + [_btn("بازگشت به منو", "/menu")])]


def _my_choices(b):
    return [_btn("بله، لغو کن", "xy")] + ([_btn("🔄 تغییر زمان", "xr")] if b is not None and b.type == "booking" else []) + [_btn("نه، نگه دار", "xn")]


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
        return [send("باشه، ثبت شما سر جایش ماند."), menu_actions(spec)]
    if text_n != "xy":
        owned = _owned(spec, session, store, d["bi"], d["rid"])
        return [send("لطفاً یکی از دکمه‌ها را بزنید."), send("چه کار کنیم؟", _my_choices(owned[0] if owned else None))]
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
    promoted = None
    if b.type == "booking":
        if prev == "confirmed":  # a place just opened: the first person waiting for the SAME date gets it
            where = {"slot": r.get("slot"), "status": "waitlisted"}
            if r.get("date"):
                where["date"] = r["date"]
            waiting = sorted(store.find(b.id, **where), key=lambda w: w["id"])
            if waiting:
                promoted = waiting[0]
                store.update(b.id, promoted["id"], status="confirmed", _promoted_at=now.isoformat())
                if promoted.get("_cust"):
                    actions.append({"type": "notify_customer", "cust": promoted["_cust"],
                                    "text": f"🎉 جای خالی شد! ثبت‌نام شما در «{promoted.get('slot_label', b.title)}» تأیید شد."})
                if by == "customer":
                    _notify(spec, b.id, _summary(promoted), actions, prefix=f"✅ از لیست انتظار تأیید شد · {b.title}")
    elif b.source == "table":
        store.release(b.id, [(it["id"], it.get("qty", 1)) for it in r.get("items", [])])
    if by == "owner" and r.get("_cust"):
        what = f"ثبت‌نام شما در «{r.get('slot_label', b.title)}»" if b.type == "booking" else "سفارش شما"
        actions.append({"type": "notify_customer", "cust": r["_cust"],
                        "text": f"متأسفانه {what} توسط مدیر لغو شد." + (f"\nدلیل: {reason.strip()}" if reason.strip() else "")})
    return actions, promoted


def set_order_status(store, now, b, r: dict, status: str) -> list[dict]:
    """Owner moves an order forward (preparing -> ready -> done). Returns the customer notification, if any."""
    if b.type != "catalog_order":
        raise ValueError("وضعیت فقط برای سفارش‌ها قابل تغییر است.")
    cur = r.get("status")
    if cur == "awaiting_payment":
        raise ValueError("این سفارش هنوز پرداخت نشده است.")
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
