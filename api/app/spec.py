"""BotSpec: the declarative description of a bot. The agent writes this; the engine runs it."""
from __future__ import annotations

import re
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, model_validator

FieldKind = Literal["text", "phone", "number", "choice"]


class FormField(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    label: str
    kind: FieldKind = "text"
    choices: list[str] = []
    required: bool = True

    @model_validator(mode="after")
    def _choices(self):
        if self.kind == "choice" and len(self.choices) < 2:
            raise ValueError(f"field '{self.key}': choice fields need at least 2 choices")
        return self


class MessageBlock(BaseModel):
    type: Literal["message"] = "message"
    id: str
    text: str


PLACEHOLDER = re.compile(r"\{(\w+)\}")


def check_placeholders(texts: list[str], allowed: set[str]):
    """{field_key} in a confirmation text is replaced by what the customer typed; anything else would be sent literally, so reject it."""
    for t in texts:
        for key in PLACEHOLDER.findall(t):
            if key not in allowed:
                raise ValueError(f"unknown placeholder {{{key}}}; allowed: {sorted(allowed)}")


class FormBlock(BaseModel):
    type: Literal["form"] = "form"
    id: str
    title: str
    fields: list[FormField] = Field(min_length=1)
    done_text: str = "اطلاعات شما ثبت شد. ممنون!"  # may contain {field_key}: replaced by the customer's answer

    @model_validator(mode="after")
    def _placeholders(self):
        check_placeholders([self.done_text], {f.key for f in self.fields})
        return self


ShortId = Annotated[str, Field(pattern=r"^[a-z0-9_]{1,24}$")]  # goes into callback_data (Bale max 64 bytes)


class Slot(BaseModel):
    id: ShortId
    label: str  # for a weekly slot: «پنجشنبه ساعت ۱۰ صبح» WITHOUT a date; the bot appends the real date itself
    capacity: int = Field(gt=0)
    weekday: int | None = None  # None = one-off slot (capacity counts for ever); 0=شنبه … 6=جمعه = repeats every week
    time: str | None = None  # "HH:MM" 24h Tehran time, required for weekly slots

    @model_validator(mode="after")
    def _weekly(self):
        if self.weekday is not None:
            if not 0 <= self.weekday <= 6:
                raise ValueError(f"slot '{self.id}': weekday must be 0 (شنبه) to 6 (جمعه)")
            if not self.time or not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", self.time):
                raise ValueError(f"slot '{self.id}': a weekly slot needs time as HH:MM")
        return self


DEFAULT_CONTACT = [
    FormField(key="name", label="نام و نام خانوادگی"),
    FormField(key="phone", label="شماره موبایل", kind="phone"),
]


_HHMM = re.compile(r"([01]\d|2[0-3]):[0-5]\d")


def _mins(t: str) -> int:
    return int(t[:2]) * 60 + int(t[3:])


class WorkDay(BaseModel):
    weekday: int = Field(ge=0, le=6)  # 0 = شنبه … 6 = جمعه
    start: str  # "HH:MM"
    end: str

    @model_validator(mode="after")
    def _hours(self):
        if not (_HHMM.fullmatch(self.start) and _HHMM.fullmatch(self.end)) or _mins(self.start) >= _mins(self.end):
            raise ValueError("working hours need start < end as HH:MM")
        return self


class Schedule(BaseModel):
    """Individual appointments generated from working hours (salon, clinic, tutor…), as opposed to fixed `slots`."""
    days: list[WorkDay] = Field(min_length=1, max_length=14)
    duration_minutes: int = Field(ge=10, le=480)
    capacity: int = Field(default=1, ge=1, le=20)  # customers per time, per staff member
    days_ahead: int = Field(default=7, ge=1, le=14)  # how many days from today can be booked
    staff: list[str] = []  # optional: each person has their own calendar and the customer chooses one
    break_start: str | None = None  # optional daily break (lunch), "HH:MM"
    break_end: str | None = None

    @model_validator(mode="after")
    def _ok(self):
        if len({d.weekday for d in self.days}) != len(self.days):
            raise ValueError("each weekday may appear once in the working days")
        for d in self.days:
            if _mins(d.end) - _mins(d.start) < self.duration_minutes:
                raise ValueError("an appointment is longer than a whole working day")
        if (self.break_start is None) != (self.break_end is None):
            raise ValueError("a break needs both break_start and break_end")
        if self.break_start and not (_HHMM.fullmatch(self.break_start) and _HHMM.fullmatch(self.break_end) and _mins(self.break_start) < _mins(self.break_end)):
            raise ValueError("break needs start < end as HH:MM")
        if len(self.staff) > 8 or len({x.strip() for x in self.staff}) != len(self.staff) or any(not x.strip() or len(x) > 40 for x in self.staff):
            raise ValueError("staff: up to 8 distinct non-empty names")
        return self


class BookingBlock(BaseModel):
    type: Literal["booking"] = "booking"
    id: str
    title: str
    slots: list[Slot] = []  # fixed events / classes with a capacity …
    schedule: Schedule | None = None  # … OR individual appointments generated from working hours (not both)
    occurrences: int = Field(default=2, ge=1, le=4)  # how many upcoming dates are offered for each weekly slot
    waitlist: bool = False
    allow_cancel: bool = False  # customers may cancel their own booking from «ثبت‌های من»
    cancel_deadline_hours: int = Field(default=0, ge=0, le=168)  # no cancelling inside this many hours before a dated slot starts
    reminder_hours: int = Field(default=0, ge=0, le=72)  # remind the customer this many hours before the start (0 = no reminder); needs a dated slot with a time
    fields: list[FormField] = Field(default_factory=lambda: [f.model_copy() for f in DEFAULT_CONTACT])
    confirm_text: str = "ثبت‌نام شما با موفقیت انجام شد."
    full_text: str = "متأسفانه ظرفیت این زمان تکمیل است."
    waitlist_text: str = "ظرفیت تکمیل است؛ شما در لیست انتظار قرار گرفتید و در صورت خالی شدن جا خبر می‌دهیم."

    @model_validator(mode="after")
    def _one_kind(self):
        if bool(self.slots) == (self.schedule is not None):
            raise ValueError("a booking block needs either `slots` (fixed events/classes) or `schedule` (appointments from working hours), not both and not neither")
        check_placeholders([self.confirm_text, self.waitlist_text], {f.key for f in self.fields} | {"slot_label", "date", "time", "staff"})
        return self


class OptionGroup(BaseModel):
    name: str
    choices: list[str] = Field(min_length=2)


class CatalogItem(BaseModel):
    id: ShortId
    name: str
    price: int = Field(ge=0)
    options: list[OptionGroup] = []


class ProductOption(BaseModel):
    name: str
    choices: list[str]


class ProductIn(BaseModel):
    """A row of the store's product table (also used as the agent's sample/test fixture)."""
    name: str
    category: str
    price: int = Field(ge=0)  # toman
    stock: int | None  # None = unlimited
    options: list[ProductOption]
    description: str


def norm_code(code: str) -> str:
    return code.strip().casefold()


class DiscountCode(BaseModel):
    code: str = Field(min_length=2, max_length=20)
    percent: int = Field(default=0, ge=0, le=100)  # exactly one of percent / amount
    amount: int = Field(default=0, ge=0)           # fixed Toman off
    min_total: int = Field(default=0, ge=0)        # minimum goods total for the code to apply
    max_uses: int = Field(default=0, ge=0)         # 0 = unlimited; cancelled orders give their use back

    @model_validator(mode="after")
    def _one_kind(self):
        if (self.percent > 0) == (self.amount > 0):
            raise ValueError("a discount code needs either percent or amount (exactly one)")
        if " " in self.code.strip():
            raise ValueError("a discount code is a single word")
        return self


class CatalogOrderBlock(BaseModel):
    type: Literal["catalog_order"] = "catalog_order"
    id: str
    title: str
    source: Literal["inline", "table"] = "inline"  # table = products live in the database, not in the spec
    items: list[CatalogItem] = []
    max_items: int = Field(default=10, gt=0)
    min_total: int = Field(default=0, ge=0)
    allow_cancel: bool = False  # customers may cancel their own order shortly after placing it
    cancel_window_minutes: int = Field(default=30, ge=1, le=1440)
    fields: list[FormField] = Field(default_factory=lambda: [f.model_copy() for f in DEFAULT_CONTACT])
    confirm_text: str = "سفارش شما ثبت شد."
    payment: Literal["none", "online"] = "none"      # online: the customer pays inside Bale (needs the owner's own bot + wallet token)
    delivery_fee: int = Field(default=0, ge=0)       # Toman added to every order (0 = none)
    free_delivery_over: int = Field(default=0, ge=0)  # goods total (after discount) from which delivery is free (0 = never)
    discount_codes: list[DiscountCode] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _items(self):
        if len({norm_code(c.code) for c in self.discount_codes}) != len(self.discount_codes):
            raise ValueError("duplicate discount code")
        check_placeholders([self.confirm_text], {f.key for f in self.fields})
        if self.source == "inline" and not self.items:
            raise ValueError("an inline catalog_order needs at least one item (or use source='table')")
        return self


class FaqEntry(BaseModel):
    question: str = Field(min_length=3, max_length=200)
    answer: str = Field(min_length=1, max_length=1500)


class FaqBlock(BaseModel):
    """Customers type a question in their own words; the bot returns the owner's EXACT answer (retrieval only, nothing is generated)."""
    type: Literal["faq"] = "faq"
    id: str
    title: str
    entries: list[FaqEntry] = Field(min_length=1, max_length=40)
    prompt_text: str = "سؤال خود را بنویسید تا پاسخش را پیدا کنم، یا از فهرست انتخاب کنید:"
    not_found_text: str = "پاسخ این سؤال را پیدا نکردم. سؤالتان برای مدیر ثبت شد و به‌زودی پاسخ می‌دهیم."


class ContactBlock(BaseModel):
    """Customers write to the owner; the owner answers from the dashboard inbox and the reply arrives in the customer's chat."""
    type: Literal["contact"] = "contact"
    id: str
    title: str
    prompt_text: str = "پیام خود را بنویسید تا برای مدیر ارسال شود. پاسخ را همین‌جا دریافت می‌کنید:"
    sent_text: str = "پیام شما برای مدیر ارسال شد. پاسخ را همین‌جا دریافت می‌کنید."


class FeedbackBlock(BaseModel):
    """Customers rate the service 1-5 and may add a comment; the owner sees every rating and the average in the panel."""
    type: Literal["feedback"] = "feedback"
    id: str
    title: str
    prompt_text: str = "به تجربه‌ی خود امتیاز دهید:"
    comment_text: str = "اگر نظر یا پیشنهادی دارید بنویسید، یا «رد کردن» را بزنید:"
    thanks_text: str = "ممنون از نظر شما 🌟"


class AdminNotifyBlock(BaseModel):
    type: Literal["admin_notify"] = "admin_notify"
    id: str
    on: str  # id of the block whose completion triggers the notification
    text: str = "ثبت جدید"


Block = Annotated[
    Union[MessageBlock, FormBlock, BookingBlock, CatalogOrderBlock, FaqBlock, ContactBlock, FeedbackBlock, AdminNotifyBlock],
    Field(discriminator="type"),
]


class MenuItem(BaseModel):
    label: str
    block: str


class BotSpec(BaseModel):
    name: str
    welcome: str
    menu: list[MenuItem] = Field(min_length=1)
    blocks: list[Block] = Field(min_length=1)

    @model_validator(mode="after")
    def _refs(self):
        ids = [b.id for b in self.blocks]
        if len(ids) != len(set(ids)):
            raise ValueError("block ids must be unique")
        for m in self.menu:
            target = next((b for b in self.blocks if b.id == m.block), None)
            if target is None:
                raise ValueError(f"menu item '{m.label}' points to unknown block '{m.block}'")
            if target.type == "admin_notify":
                raise ValueError("menu cannot point to an admin_notify block")
        for b in self.blocks:
            if b.type == "admin_notify" and b.on not in ids:
                raise ValueError(f"admin_notify '{b.id}' watches unknown block '{b.on}'")
        return self

    def block(self, block_id: str):
        return next(b for b in self.blocks if b.id == block_id)
