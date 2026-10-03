"""Deterministic runtime: engine.handle(spec, session, text, store) -> list[Action].

No LLM here. The same engine drives the web simulator, the test runner and the Bale adapter.
Actions: {"type": "send", "text", "buttons": [{"text","data"}]} | {"type": "notify_admin", "text"}
"""
from __future__ import annotations

import re
from typing import Any, Protocol

from .spec import BotSpec, BookingBlock, CatalogOrderBlock, FormBlock, FormField, MessageBlock

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
MENU_WORDS = {"/start", "/menu", "منو", "منوی اصلی", "شروع"}
CANCEL_WORDS = {"/cancel", "انصراف", "لغو"}


def norm(text: str) -> str:
    return (text or "").translate(_DIGITS).strip()


class Store(Protocol):
    def add(self, collection: str, data: dict) -> dict: ...
    def count(self, collection: str, **where: Any) -> int: ...


class MemoryStore:
    def __init__(self):
        self.rows: dict[str, list[dict]] = {}

    def add(self, collection, data):
        row = {"id": len(self.rows.setdefault(collection, [])) + 1, **data}
        self.rows[collection].append(row)
        return row

    def count(self, collection, **where):
        return sum(all(r.get(k) == v for k, v in where.items()) for r in self.rows.get(collection, []))


def new_session() -> dict:
    return {"block": None, "step": None, "data": {}}


def send(text, buttons=None):
    return {"type": "send", "text": text, "buttons": buttons or []}


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
        if value in field.choices:
            return True, value, ""
        return False, None, "لطفاً یکی از گزینه‌ها را انتخاب کنید."
    return True, raw.strip(), ""


def _ask(field: FormField):
    if field.kind == "choice":
        return send(field.label, [_btn(c) for c in field.choices])
    return send(field.label)


def menu_actions(spec: BotSpec, prefix: str | None = None):
    text = prefix if prefix is not None else "از منوی زیر یکی را انتخاب کنید:"
    return send(text, [_btn(m.label, f"m:{i}") for i, m in enumerate(spec.menu)])


def _reset(session):
    session.update(block=None, step=None, data={})


def _notify(spec: BotSpec, block_id: str, summary: str, actions: list):
    for b in spec.blocks:
        if b.type == "admin_notify" and b.on == block_id:
            actions.append({"type": "notify_admin", "text": f"{b.text}\n{summary}"})


def _summary(data: dict) -> str:
    return "\n".join(f"{k}: {v}" for k, v in data.items() if not k.startswith("_"))


def handle(spec: BotSpec, session: dict, text: str, store: Store) -> list[dict]:
    text_n = norm(text)
    if text_n in MENU_WORDS:
        _reset(session)
        return [send(spec.welcome), menu_actions(spec)]
    if text_n in CANCEL_WORDS:
        _reset(session)
        return [menu_actions(spec, "انصراف انجام شد.")]

    if session["block"] is None:
        return _from_menu(spec, session, text_n, store)

    block = spec.block(session["block"])
    if block.type == "form":
        return _form(spec, session, block, text, store)
    if block.type == "booking":
        return _booking(spec, session, block, text, store)
    if block.type == "catalog_order":
        return _order(spec, session, block, text, store)
    _reset(session)
    return [menu_actions(spec)]


# ---------- menu ----------
def _from_menu(spec, session, text_n, store):
    item = None
    m = re.fullmatch(r"m:(\d+)", text_n)
    if m and int(m.group(1)) < len(spec.menu):
        item = spec.menu[int(m.group(1))]
    else:
        item = next((i for i in spec.menu if i.label == text_n), None)
    if item is None:
        return [menu_actions(spec, "متوجه نشدم. لطفاً از منو انتخاب کنید:")]
    block = spec.block(item.block)
    if block.type == "message":
        return [send(block.text), menu_actions(spec)]
    session.update(block=block.id, step=0, data={})
    if block.type == "form":
        return [send(block.title), _ask(block.fields[0])]
    if block.type == "booking":
        session["step"] = "slot"
        return [send(block.title), _slot_prompt(block, store)]
    if block.type == "catalog_order":
        session["step"] = "item"
        session["data"] = {"_cart": []}
        return [send(block.title), _item_prompt(block)]
    return [menu_actions(spec)]


# ---------- form ----------
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
    actions = [send(block.done_text)]
    _notify(spec, block.id, _summary(row), actions)
    _reset(session)
    actions.append(menu_actions(spec))
    return actions


# ---------- booking ----------
def _remaining(block: BookingBlock, slot, store):
    return slot.capacity - store.count(block.id, slot=slot.id, status="confirmed")


def _slot_prompt(block: BookingBlock, store):
    buttons = []
    for s in block.slots:
        left = _remaining(block, s, store)
        if left > 0:
            buttons.append(_btn(f"{s.label} ({left} جای خالی)", f"s:{s.id}"))
        elif block.waitlist:
            buttons.append(_btn(f"{s.label} (تکمیل - لیست انتظار)", f"s:{s.id}"))
        else:
            buttons.append(_btn(f"{s.label} (تکمیل)", f"s:{s.id}"))
    return send("زمان مورد نظر را انتخاب کنید:", buttons)


def _booking(spec, session, block: BookingBlock, text, store):
    text_n = norm(text)
    if session["step"] == "slot":
        slot_id = text_n[2:] if text_n.startswith("s:") else None
        slot = next((s for s in block.slots if s.id == slot_id or text_n.startswith(s.label)), None)
        if slot is None:
            return [send("لطفاً یکی از زمان‌ها را انتخاب کنید."), _slot_prompt(block, store)]
        if _remaining(block, slot, store) <= 0 and not block.waitlist:
            return [send(block.full_text), _slot_prompt(block, store)]
        session["data"]["slot"] = slot.id
        session["data"]["slot_label"] = slot.label
        session["step"] = 0
        return [_ask(block.fields[0])]
    idx = session["step"]
    field = block.fields[idx]
    ok, value, err = validate(field, text)
    if not ok:
        return [send(err), _ask(field)]
    session["data"][field.key] = value
    if idx + 1 < len(block.fields):
        session["step"] = idx + 1
        return [_ask(block.fields[idx + 1])]
    slot = next(s for s in block.slots if s.id == session["data"]["slot"])
    # re-check capacity at commit time (another user may have taken the last seat)
    full = _remaining(block, slot, store) <= 0
    if full and not block.waitlist:
        _reset(session)
        return [send(block.full_text), menu_actions(spec)]
    status = "waitlisted" if full else "confirmed"
    row = store.add(block.id, {**session["data"], "status": status})
    actions = [send(block.waitlist_text if full else block.confirm_text)]
    _notify(spec, block.id, f"[{status}] " + _summary(row), actions)
    _reset(session)
    actions.append(menu_actions(spec))
    return actions


# ---------- catalog order ----------
def _item_prompt(block: CatalogOrderBlock):
    return send("آیتم مورد نظر را انتخاب کنید:", [_btn(f"{i.name} - {i.price:,} تومان", f"i:{i.id}") for i in block.items])


def _cart_total(block, cart):
    return sum(c["price"] for c in cart)


def _order(spec, session, block: CatalogOrderBlock, text, store):
    text_n = norm(text)
    d = session["data"]
    step = session["step"]
    if step == "item":
        item = next((i for i in block.items if text_n == f"i:{i.id}" or text_n.startswith(i.name)), None)
        if item is None:
            return [send("لطفاً یکی از آیتم‌ها را انتخاب کنید."), _item_prompt(block)]
        d["_pending"] = {"id": item.id, "name": item.name, "price": item.price, "options": {}}
        return _next_option(session, block, item)
    if step == "option":
        item = next(i for i in block.items if i.id == d["_pending"]["id"])
        group = item.options[d["_opt_idx"]]
        if text_n not in group.choices:
            return [send("لطفاً یکی از گزینه‌ها را انتخاب کنید."), send(group.name, [_btn(c) for c in group.choices])]
        d["_pending"]["options"][group.name] = text_n
        d["_opt_idx"] += 1
        return _next_option(session, block, item)
    if step == "more":
        if text_n == "more":
            session["step"] = "item"
            return [_item_prompt(block)]
        if text_n == "checkout":
            total = _cart_total(block, d["_cart"])
            if total < block.min_total:
                return [send(f"حداقل مبلغ سفارش {block.min_total:,} تومان است. لطفاً آیتم بیشتری اضافه کنید."), _more_prompt()]
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
    total = _cart_total(block, cart)
    contact = {f.key: d[f.key] for f in block.fields}
    row = store.add(block.id, {**contact, "items": cart, "total": total, "status": "new"})
    lines = "\n".join(f"- {c['name']} {' '.join(c['options'].values())}".strip() for c in cart)
    actions = [send(f"{block.confirm_text}\n{lines}\nجمع کل: {total:,} تومان")]
    _notify(spec, block.id, f"سفارش #{row['id']} - جمع {total:,} تومان\n{lines}", actions)
    _reset(session)
    actions.append(menu_actions(spec))
    return actions


def _more_prompt():
    return send("آیتم دیگری اضافه می‌کنید؟", [_btn("افزودن آیتم دیگر", "more"), _btn("ثبت سفارش", "checkout")])


def _next_option(session, block, item):
    d = session["data"]
    d.setdefault("_opt_idx", 0)
    if d["_opt_idx"] < len(item.options):
        session["step"] = "option"
        g = item.options[d["_opt_idx"]]
        return [send(g.name, [_btn(c) for c in g.choices])]
    if len(d["_cart"]) + 1 > block.max_items:
        d.pop("_pending", None)
        d.pop("_opt_idx", None)
        session["step"] = "more"
        return [send(f"حداکثر {block.max_items} آیتم در هر سفارش مجاز است."), _more_prompt()]
    d["_cart"].append(d.pop("_pending"))
    d.pop("_opt_idx", None)
    session["step"] = "more"
    return [send(f"«{item.name}» به سفارش اضافه شد."), _more_prompt()]
