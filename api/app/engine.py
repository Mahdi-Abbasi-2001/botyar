"""Deterministic runtime: engine.handle(spec, session, text, store) -> list[Action].

No LLM here. The same engine drives the web simulator, the test runner and the Bale adapter.
Actions: {"type": "send", "text", "buttons": [{"text","data"}]} | {"type": "notify_admin", "text"}
"""
from __future__ import annotations

import re
import math
from typing import Any, Protocol

from .spec import BotSpec, BookingBlock, CatalogOrderBlock, FormBlock, FormField, MessageBlock

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
MENU_WORDS = {"/start", "/menu", "منو", "منوی اصلی", "شروع"}
CANCEL_WORDS = {"/cancel", "انصراف", "لغو"}


def norm(text: str) -> str:
    return (text or "").translate(_DIGITS).strip()


_FA = str.maketrans({"ي": "ی", "ك": "ک", "ة": "ه", "\u200c": " "})


def fa_norm(text: str) -> str:
    """Search-friendly form: ASCII digits, Persian ی/ک, no ZWNJ, lowercase, single spaces."""
    return " ".join(norm(text).translate(_FA).lower().split())


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


class Store(Protocol):
    def add(self, collection: str, data: dict) -> dict: ...
    def count(self, collection: str, **where: Any) -> int: ...
    def categories(self, block_id: str) -> list[str]: ...
    def products(self, block_id: str, category: str | None, query: str | None, offset: int, limit: int) -> tuple[list[dict], int]: ...
    def product(self, block_id: str, pid: int) -> dict | None: ...
    def reserve(self, block_id: str, lines: list[tuple[int, int]]) -> list[int]: ...


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

    def reserve(self, block_id, lines):
        rows = {p["id"]: p for p in self.catalog.get(block_id, [])}
        failed = [pid for pid, qty in lines if pid not in rows or (rows[pid]["stock"] is not None and rows[pid]["stock"] < qty)]
        if not failed:
            for pid, qty in lines:
                if rows[pid]["stock"] is not None:
                    rows[pid]["stock"] -= qty
        return failed


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
        return _order_start(spec, session, block, store)
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


# ---------- catalog order (inline menu, or products from the database table) ----------
PAGE = 5


def _is_table(block: CatalogOrderBlock) -> bool:
    return block.source == "table"


def _item_prompt(block: CatalogOrderBlock):
    return send("آیتم مورد نظر را انتخاب کنید:", [_btn(f"{i.name} - {i.price:,} تومان", f"i:{i.id}") for i in block.items])


def _cat_prompt(block, store):
    buttons = [_btn(c, f"c:{i}") for i, c in enumerate(store.categories(block.id))]
    buttons += [_btn("همه‌ی محصولات", "all"), _btn("🔎 جستجو", "search")]
    return send("دسته‌بندی را انتخاب کنید:", buttons)


def _list_prompt(block, store, d):
    cats = store.categories(block.id)
    cat, q, page = d.get("_cat"), d.get("_q"), d.get("_page", 0)
    items, total = store.products(block.id, cat, q, page * PAGE, PAGE)
    back = [_btn("بازگشت به دسته‌ها", "back")] if len(cats) > 1 else []
    if total == 0:
        return send("محصولی پیدا نشد.", [_btn("🔎 جستجوی دیگر", "search")] + back)
    pages = math.ceil(total / PAGE)
    if not items:  # page out of range -> last page
        page = pages - 1
        items, _ = store.products(block.id, cat, q, page * PAGE, PAGE)
    d["_page"] = page
    head = f"نتیجه‌ی جستجو برای «{q}»" if q else (cat or "همه‌ی محصولات")
    buttons = [_btn(f"{p['name']} - {p['price']:,} تومان", f"p:{p['id']}") for p in items]
    if page > 0:
        buttons.append(_btn("‹ قبلی", f"pg:{page - 1}"))
    if page + 1 < pages:
        buttons.append(_btn("بعدی ›", f"pg:{page + 1}"))
    buttons += [_btn("🔎 جستجو", "search")] + back
    return send(f"{head} — صفحه {page + 1} از {pages}", buttons)


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
    if p["stock"] is not None and p["stock"] <= 0:
        return [send(f"«{p['name']}» فعلاً موجود نیست."), _list_prompt(block, store, d)]
    d["_pending"] = {"id": p["id"], "name": p["name"], "price": p["price"], "options": {}, "stock": p["stock"],
                     "_groups": [[o["name"], o["choices"]] for o in p["options"] if o["choices"]]}
    d["_opt_idx"] = 0
    return _next_option(session, block)


def _order(spec, session, block: CatalogOrderBlock, text, store):
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
        return [_list_prompt(block, store, d)]

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
            return [_list_prompt(block, store, d)]
        if text_n == "search":
            session["step"] = "q"
            return [send("نام یا بخشی از نام محصول را بنویسید:")]
        if text_n == "back" and len(store.categories(block.id)) > 1:
            d["_q"] = None
            session["step"] = "cat"
            return [_cat_prompt(block, store)]
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
        top = min(99, stock) if stock is not None else 99
        if n < 1:
            return [send("لطفاً تعداد را به صورت عدد وارد کنید."), _qty_prompt(d["_pending"])]
        if n > top:
            return [send(f"حداکثر موجودی این محصول {top} عدد است."), _qty_prompt(d["_pending"])]
        return _add_to_cart(session, block, n)

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
    total = _cart_total(cart)
    contact = {f.key: d[f.key] for f in block.fields}
    row = store.add(block.id, {**contact, "items": cart, "total": total, "status": "new"})
    lines = "\n".join(f"- {c['name']} {' '.join(c['options'].values())}".strip() + (f" × {c['qty']}" if "qty" in c else "") for c in cart)
    actions = [send(f"{block.confirm_text}\n{lines}\nجمع کل: {total:,} تومان")]
    _notify(spec, block.id, f"سفارش #{row['id']} - جمع {total:,} تومان\n{lines}", actions)
    _reset(session)
    actions.append(menu_actions(spec))
    return actions
