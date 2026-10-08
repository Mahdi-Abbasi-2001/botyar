"""BotSpec: the declarative description of a bot. The agent writes this; the engine runs it."""
from __future__ import annotations

import re
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator

from .dates import parse_jalali


def jalali_date(s: str):
    """A spec date written by the agent: Jalali «1403/07/30» only."""
    return parse_jalali(s) if re.fullmatch(r"\d{4}/\d{1,2}/\d{1,2}", s.strip()) else None

# text · phone (Iranian mobile) · number · choice (one button) · multi (several buttons, then «تمام»)
# email · national_id (Iranian national code, checksum) · date (Jalali, e.g. ۱۴۰۳/۰۸/۱۵ or «۱۵ آبان»)
# location (the customer shares a map location from Bale's 📎 menu, or writes the address; the owner gets a map link)
# file (forms only: a résumé / document / photo the customer sends; PDF, Word or image up to 10 MB; forwarded to the owner)
FieldKind = Literal["text", "phone", "number", "choice", "multi", "email", "national_id", "date", "location", "file"]


class ShowIf(BaseModel):
    """Ask this question only when an EARLIER question's answer is one of `equals` (for a multi answer: contains one)."""
    field: str
    equals: list[str] = Field(min_length=1)


class FormField(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    label: str
    kind: FieldKind = "text"
    choices: list[str] = []
    required: bool = True  # optional questions get a «رد کردن» button
    min_value: int | None = None  # number fields: allowed range
    max_value: int | None = None
    show_if: ShowIf | None = None
    scores: list[int] = []  # lead scoring: points per choice (same length as choices); a multi answer adds up its choices

    @model_validator(mode="after")
    def _choices(self):
        if self.kind in ("choice", "multi") and len(self.choices) < 2:
            raise ValueError(f"field '{self.key}': {self.kind} fields need at least 2 choices")
        if self.scores and (self.kind not in ("choice", "multi") or len(self.scores) != len(self.choices)):
            raise ValueError(f"field '{self.key}': scores need a choice/multi field and one number per choice")
        if self.min_value is not None and self.max_value is not None and self.min_value > self.max_value:
            raise ValueError(f"field '{self.key}': min_value is above max_value")
        return self


def no_files(fields: list[FormField]):
    if any(f.kind == "file" for f in fields):
        raise ValueError("file questions are only for form blocks")


def check_fields(fields: list[FormField]):
    """Unique keys, and every show_if points to an EARLIER question (with one of its choices, when it has choices)."""
    seen: dict[str, FormField] = {}
    for f in fields:
        if f.key in seen:
            raise ValueError(f"duplicate field key '{f.key}'")
        if f.show_if:
            ref = seen.get(f.show_if.field)
            if ref is None:
                raise ValueError(f"field '{f.key}': show_if must refer to an earlier question's key")
            if ref.choices and not set(f.show_if.equals) <= set(ref.choices):
                raise ValueError(f"field '{f.key}': show_if values must be choices of '{ref.key}'")
        seen[f.key] = f


class JoinGate(BaseModel):
    """Customers must be members of this channel before the bot talks to them (checked on Bale/Telegram; the owner must make the
    bot an admin of the channel). If the check itself fails, customers are let in: a setup mistake must never lock them out."""
    channel: str  # "@username" or a numeric chat id
    text: str = "برای استفاده از ربات، ابتدا در کانال ما عضو شوید و سپس «عضو شدم» را بزنید."
    join_url: str = Field(default="", max_length=200)  # optional; built from the @username when empty

    @model_validator(mode="after")
    def _channel(self):
        c = self.channel.strip()
        if not re.fullmatch(r"@[A-Za-z0-9_]{4,64}|-?\d{5,20}", c):
            raise ValueError("channel must be an @username (letters, digits, underscore) or a numeric chat id")
        self.channel = c
        if self.join_url and not self.join_url.startswith("https://"):
            raise ValueError("join_url must start with https://")
        return self


class JoinChannel(BaseModel):
    """A channel the customer must have joined before receiving a message block's content."""
    channel: str  # "@username"
    title: str = Field(default="", max_length=40)  # the button label (default: the @username)

    @model_validator(mode="after")
    def _channel(self):
        c = self.channel.strip()
        if not re.fullmatch(r"@[A-Za-z0-9_]{4,64}", c):
            raise ValueError("a join channel must be an @username (letters, digits, underscore)")
        self.channel = c
        return self


class MenuItem(BaseModel):
    label: str
    block: str


class MapPoint(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class LinkButton(BaseModel):
    """A button that opens a web page (Instagram, website, map, online shop)."""
    label: str = Field(min_length=1, max_length=30)
    url: str = Field(pattern=r"^https?://\S+$", max_length=300)


class ContactCard(BaseModel):
    """A phone contact the customer can save or call with one tap («تماس با ما»)."""
    phone: str = Field(pattern=r"^\+?[0-9۰-۹ -]{7,20}$")
    name: str = Field(min_length=1, max_length=60)


class MessageBlock(BaseModel):
    type: Literal["message"] = "message"
    id: str
    text: str
    # image/document: one file the owner uploads in «فایل‌ها»; album: album_size photos (portfolio, gallery)
    media: Literal["none", "image", "document", "album"] = "none"
    album_size: int = Field(default=0, ge=0, le=10)
    contact: ContactCard | None = None  # a contact card after the text
    hours: list["WorkDay"] = Field(default_factory=list, max_length=14)  # opening hours: the text gets «🟢 الان باز هستیم» / «🔴 الان بسته‌ایم»
    location: MapPoint | None = None  # a map pin sent after the text
    variants: list[Annotated[str, Field(min_length=1, max_length=1500)]] = Field(default_factory=list, max_length=30)  # non-empty: each tap shows one of these at random (never the same twice in a row)
    links: list[LinkButton] = Field(default_factory=list, max_length=6)  # link buttons under the text
    # content behind a join: the text/file/links above are delivered only after the customer is a member of EVERY channel here
    join: list[JoinChannel] = Field(default_factory=list, max_length=5)
    join_text: str = Field(default="", max_length=300)  # shown with the channel buttons (default text when empty)

    @model_validator(mode="after")
    def _join(self):
        names = [c.channel.lower() for c in self.join]
        if len(set(names)) != len(names):
            raise ValueError("the same channel is listed twice in join")
        return self

    @model_validator(mode="after")
    def _album(self):
        if self.media == "album" and self.album_size < 2:
            raise ValueError("an album needs album_size 2..10 (the number of photos)")
        if self.media != "album":
            self.album_size = 0
        return self


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
    confirm_before_submit: bool = False  # show the answers with «تأیید و ثبت» / «از اول» before saving
    one_per_customer: bool = False       # a customer who already submitted gets closed_text
    max_submissions: int = Field(default=0, ge=0)  # 0 = unlimited; once reached the form is closed
    closes_on: str = ""                  # last day to submit, Jalali «1403/07/30» (empty = never closes)
    closed_text: str = "ثبت این فرم به پایان رسیده است."
    already_text: str = "شما قبلاً این فرم را ثبت کرده‌اید."
    review: bool = False      # applications/requests: the owner answers each one (accepted / rejected / under review) from the dashboard
    hot_score: int = Field(default=0, ge=0)  # lead scoring: a submission whose answer scores add up to this is flagged 🔥 (0 = off)

    @model_validator(mode="after")
    def _placeholders(self):
        check_fields(self.fields)
        if self.hot_score and not any(f.scores for f in self.fields):
            raise ValueError("hot_score needs scores on at least one choice/multi question")
        if self.fields[0].show_if:
            raise ValueError("the first question cannot have show_if")
        check_placeholders([self.done_text], {f.key for f in self.fields} | {"id"})
        if self.closes_on and jalali_date(self.closes_on) is None:
            raise ValueError("closes_on must be a real Jalali date like 1403/07/30")
        return self


ShortId = Annotated[str, Field(pattern=r"^[a-z0-9_]{1,24}$")]  # goes into callback_data (Bale max 64 bytes)


class Slot(BaseModel):
    id: ShortId
    label: str  # for a weekly slot: «پنجشنبه ساعت ۱۰ صبح» WITHOUT a date; the bot appends the real date itself
    capacity: int = Field(gt=0)
    price: int = Field(default=0, ge=0)  # Toman, shown on the button (0 = not shown)
    weekday: int | None = None  # None = one-off slot (capacity counts for ever); 0=شنبه … 6=جمعه = repeats every week
    time: str | None = None  # "HH:MM" 24h Tehran time, required for weekly slots and dated sessions
    on: str | None = None  # a DATED one-off session, Jalali «1405/07/25» (with time): capacity per session, hidden once it has started

    @model_validator(mode="after")
    def _weekly(self):
        if self.on is not None:
            if self.weekday is not None:
                raise ValueError(f"slot '{self.id}': a dated session has `on` OR `weekday`, not both")
            if jalali_date(self.on) is None:
                raise ValueError(f"slot '{self.id}': `on` must be a Jalali date like 1405/07/25")
            if not self.time or not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", self.time):
                raise ValueError(f"slot '{self.id}': a dated session needs time as HH:MM")
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

    @field_validator("end", mode="before")
    @classmethod
    def _midnight(cls, v):
        """«تا ۲۴» / «تا نیمه‌شب» is how owners say they close at midnight: the last minute of that day."""
        return "23:59" if isinstance(v, str) and v.strip() in ("24:00", "24", "00:00", "0:00") else v

    @model_validator(mode="after")
    def _hours(self):
        if not (_HHMM.fullmatch(self.start) and _HHMM.fullmatch(self.end)) or _mins(self.start) >= _mins(self.end):
            raise ValueError("working hours need start < end as HH:MM")
        return self


class Service(BaseModel):
    """One kind of appointment with its own length (haircut 30 min, colouring 90 min)."""
    id: ShortId
    name: str = Field(min_length=1, max_length=60)
    duration_minutes: int = Field(ge=10, le=480)
    price: int = Field(default=0, ge=0)  # Toman, shown on the button (0 = not shown)
    staff: list[str] = []  # who does it (names from schedule.staff); empty = everyone


class StaffHours(BaseModel):
    """One staff member's own working days and hours (instead of the schedule's)."""
    staff: str
    days: list[WorkDay] = Field(min_length=1, max_length=14)


class Schedule(BaseModel):
    """Individual appointments generated from working hours (salon, clinic, tutor…), as opposed to fixed `slots`."""
    days: list[WorkDay] = Field(min_length=1, max_length=14)
    duration_minutes: int = Field(ge=10, le=480)  # one appointment; with `services` it is the grid start times step on
    services: list[Service] = Field(default_factory=list, max_length=20)  # the customer picks one first; its length is used
    staff_hours: list[StaffHours] = Field(default_factory=list, max_length=8)  # staff whose days/hours differ from `days`
    capacity: int = Field(default=1, ge=1, le=20)  # customers per time, per staff member
    days_ahead: int = Field(default=7, ge=1, le=14)  # how many days from today can be booked
    staff: list[str] = []  # optional: each person has their own calendar and the customer chooses one
    break_start: str | None = None  # optional daily break (lunch), "HH:MM"
    break_end: str | None = None

    @model_validator(mode="after")
    def _ok(self):
        if len({d.weekday for d in self.days}) != len(self.days):
            raise ValueError("each weekday may appear once in the working days")
        longest = max([self.duration_minutes] + [s.duration_minutes for s in self.services])
        if max(_mins(d.end) - _mins(d.start) for d in self.days) < longest:
            raise ValueError("an appointment (or service) is longer than a whole working day")
        if len({s.id for s in self.services}) != len(self.services):
            raise ValueError("duplicate service id")
        for s in self.services:
            if set(s.staff) - set(self.staff):
                raise ValueError(f"service '{s.id}': staff must be names from schedule.staff")
        if len({h.staff for h in self.staff_hours}) != len(self.staff_hours) or {h.staff for h in self.staff_hours} - set(self.staff):
            raise ValueError("staff_hours: one entry per staff member, with names from schedule.staff")
        for h in self.staff_hours:
            if len({d.weekday for d in h.days}) != len(h.days):
                raise ValueError(f"staff_hours '{h.staff}': each weekday may appear once")
            if max(_mins(d.end) - _mins(d.start) for d in h.days) < longest:
                raise ValueError(f"staff_hours '{h.staff}': an appointment is longer than a whole working day")
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
    reminder_hours: int = Field(default=0, ge=0, le=72)
    reminder_confirm: bool = True  # the reminder asks «می‌آیم» / «نمی‌توانم بیایم» (a «no» frees the place)
    closed_dates: list[str] = Field(default_factory=list, max_length=60)  # Jalali «1403/07/30»: no bookings on these days
    min_notice_hours: int = Field(default=0, ge=0, le=168)  # nothing that starts sooner than this can be booked
    max_active_per_customer: int = Field(default=0, ge=0, le=20)  # upcoming bookings one customer may hold (0 = no limit)
    deposit: int = Field(default=0, ge=0)  # Toman paid online (Bale wallet) to confirm a booking; 0 = none
    repeat_weeks: int = Field(default=0, ge=0, le=12)  # >1: after a weekly session/appointment the customer may book up to this many weeks in a row
    no_show_limit: int = Field(default=0, ge=0, le=10)  # after this many «حاضر نشد» marks the customer can't book online (0 = never)
    max_party: int = Field(default=1, ge=1, le=20)  # >1: «چند نفر هستید؟» and the group takes that many places (slots only)  # remind the customer this many hours before the start (0 = no reminder); needs a dated slot with a time
    fields: list[FormField] = Field(default_factory=lambda: [f.model_copy() for f in DEFAULT_CONTACT])

    @model_validator(mode="before")
    @classmethod
    def _never_no_questions(cls, v):
        """«No questions» is not a thing the engine can run (there would be nobody to contact): an empty list means the standard name + phone."""
        if isinstance(v, dict) and not v.get("fields"):
            v = {**v, "fields": [f.model_dump() for f in DEFAULT_CONTACT]}
        return v
    confirm_text: str = "ثبت‌نام شما با موفقیت انجام شد."
    full_text: str = "متأسفانه ظرفیت این زمان تکمیل است."
    waitlist_text: str = "ظرفیت تکمیل است؛ شما در لیست انتظار قرار گرفتید و اگر جایی خالی شود، به شما خبر می‌دهیم."

    @model_validator(mode="after")
    def _one_kind(self):
        if bool(self.slots) == (self.schedule is not None):
            raise ValueError("a booking block needs either `slots` (fixed events/classes) or `schedule` (appointments from working hours), not both and not neither")
        check_fields(self.fields)
        no_files(self.fields)
        bad = [d for d in self.closed_dates if jalali_date(d) is None]
        if bad:
            raise ValueError(f"closed_dates must be real Jalali dates like 1403/07/30: {bad}")
        if self.deposit and (self.waitlist or self.repeat_weeks > 1):
            raise ValueError("a deposit cannot be combined with a waitlist or repeat_weeks")
        if self.schedule and self.max_party > 1:
            raise ValueError("max_party is for slot bookings; appointments use schedule.capacity")
        check_placeholders([self.confirm_text, self.waitlist_text], {f.key for f in self.fields} | {"id", "slot_label", "date", "time", "staff", "service", "price", "party"})
        return self


def _check_prices(o):
    if o.prices and len(o.prices) != len(o.choices):
        raise ValueError(f"option '{o.name}': prices needs one number per choice (or leave it empty)")
    return o


class OptionGroup(BaseModel):
    name: str
    choices: list[str] = Field(min_length=2)
    prices: list[int] = []  # Toman added per choice, same order as choices (e.g. XL +50000); empty = no change

    _p = model_validator(mode="after")(_check_prices)


class CatalogItem(BaseModel):
    id: ShortId
    name: str
    price: int = Field(ge=0)
    options: list[OptionGroup] = []


class ProductOption(BaseModel):
    name: str
    choices: list[str]
    prices: list[int] = []  # Toman added per choice (same order); empty = no change

    _p = model_validator(mode="after")(_check_prices)


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
    visible: bool = True                           # listed for every customer in the built-in «کدهای تخفیف» menu button; False = a private code the owner hands out

    @model_validator(mode="after")
    def _one_kind(self):
        if (self.percent > 0) == (self.amount > 0):
            raise ValueError("a discount code needs either percent or amount (exactly one)")
        if " " in self.code.strip():
            raise ValueError("a discount code is a single word")
        return self


class DeliveryZone(BaseModel):
    """An area the order is sent to, with its own delivery fee (e.g. «تهران» 100,000 / «سایر شهرها» 200,000)."""
    label: str = Field(min_length=1, max_length=40)
    fee: int = Field(ge=0)  # Toman; 0 = free delivery to this area


class TimeWindow(BaseModel):
    """A delivery/pickup window offered at checkout (e.g. 12:00–13:00)."""
    start: str  # "HH:MM"
    end: str

    @model_validator(mode="after")
    def _hours(self):
        if not (_HHMM.fullmatch(self.start) and _HHMM.fullmatch(self.end)) or _mins(self.start) >= _mins(self.end):
            raise ValueError("time windows need start < end as HH:MM")
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

    @model_validator(mode="before")
    @classmethod
    def _never_no_questions(cls, v):
        """«No questions» is not a thing the engine can run (there would be nobody to contact): an empty list means the standard name + phone."""
        if isinstance(v, dict) and not v.get("fields"):
            v = {**v, "fields": [f.model_dump() for f in DEFAULT_CONTACT]}
        return v
    confirm_text: str = "سفارش شما ثبت شد."
    ask_quantity: bool = False  # inline menus: ask «تعداد» after each item (table catalogs always ask)
    order_hours: list[WorkDay] = Field(default_factory=list, max_length=14)  # when orders are taken (empty = always)
    closed_text: str = "در حال حاضر سفارش نمی‌پذیریم."  # outside order_hours (the hours are appended)
    # online: the customer pays inside Bale (needs the owner's own bot + wallet token)
    # card: card-to-card; the bot shows card_number, the customer sends the reference number or a receipt photo, the owner confirms
    payment: Literal["none", "online", "card"] = "none"
    card_number: str = ""                             # 16 digits (spaces/dashes allowed)
    card_holder: str = Field(default="", max_length=60)
    card_wait_minutes: int = Field(default=60, ge=15, le=1440)  # an order with no reference by then is cancelled and its stock returned
    delivery_fee: int = Field(default=0, ge=0)       # Toman added to every order (0 = none)
    free_delivery_over: int = Field(default=0, ge=0)  # goods total (after discount) from which delivery is free (0 = never)
    # areas with their own fee: at checkout the customer picks one and its fee replaces delivery_fee
    delivery_zones: list[DeliveryZone] = Field(default_factory=list, max_length=12)
    discount_codes: list[DiscountCode] = Field(default_factory=list, max_length=20)
    # delivery/pickup time: the customer picks a window today (or the next days); full or past windows are not offered
    time_windows: list[TimeWindow] = Field(default_factory=list, max_length=24)
    per_window: int = Field(default=0, ge=0)          # orders per window per day (0 = unlimited)
    window_days: int = Field(default=1, ge=1, le=7)   # 1 = today only; 2 = today and tomorrow …
    min_lead_minutes: int = Field(default=30, ge=0, le=720)  # a window must start at least this long after the order
    window_question: str = Field(default="زمان تحویل را انتخاب کنید:", max_length=120)
    restock_alerts: bool = True       # table catalogs: «موجود شد خبرم کن» under an out-of-stock product
    low_stock_alert: int = Field(default=0, ge=0)     # tell the owner when a product's stock falls to this many (0 = off)
    repeat_order: bool = True         # returning customers get «تکرار سفارش قبلی»

    @model_validator(mode="after")
    def _items(self):
        check_fields(self.fields)
        no_files(self.fields)
        if self.payment == "card":
            digits = re.sub(r"[\s-]", "", self.card_number.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")))
            if not re.fullmatch(r"\d{16}", digits):
                raise ValueError("payment='card' needs card_number: the owner's 16-digit card number (ask the owner; never invent one)")
            self.card_number = " ".join(digits[i:i + 4] for i in range(0, 16, 4))
        if len({(w.start, w.end) for w in self.time_windows}) != len(self.time_windows):
            raise ValueError("duplicate time window")
        if len({norm_code(c.code) for c in self.discount_codes}) != len(self.discount_codes):
            raise ValueError("duplicate discount code")
        if len({z.label.strip() for z in self.delivery_zones}) != len(self.delivery_zones):
            raise ValueError("duplicate delivery zone label")
        if len(self.delivery_zones) == 1:
            raise ValueError("delivery_zones needs at least 2 areas; for one fee everywhere use delivery_fee")
        if self.delivery_zones and self.delivery_fee:
            raise ValueError("use delivery_zones OR delivery_fee, not both (set delivery_fee to 0 when there are zones)")
        check_placeholders([self.confirm_text], {f.key for f in self.fields} | {"id"})
        if self.source == "inline" and not self.items:
            raise ValueError("an inline catalog_order needs at least one item (or use source='table')")
        return self


class FaqEntry(BaseModel):
    question: str = Field(min_length=3, max_length=200)
    answer: str = Field(min_length=1, max_length=1500)
    alternates: list[Annotated[str, Field(min_length=2, max_length=200)]] = Field(default_factory=list, max_length=8)  # other ways customers ask it
    category: str = Field(default="", max_length=30)  # groups the question list («ارسال», «پرداخت») when there are many questions
    media: Literal["none", "image"] = "none"  # a photo sent with the answer (the owner uploads it in «فایل‌ها»)
    location: MapPoint | None = None          # a map pin sent with the answer («آدرس کجاست؟»)
    then: str = ""        # optional: id of a block offered as a button under the answer (e.g. «قیمت ویزیت؟» → booking)
    then_label: str = Field(default="", max_length=30)  # that button's text (default: the block's title)


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
    topics: list[Annotated[str, Field(min_length=1, max_length=30)]] = Field(default_factory=list, max_length=8)  # asked first, e.g. پشتیبانی / فروش / شکایت
    prompt_text: str = "پیام خود را بنویسید تا برای مدیر ارسال شود. پاسخ را همین‌جا دریافت می‌کنید:"
    sent_text: str = "پیام شما برای مدیر ارسال شد. پاسخ را همین‌جا دریافت می‌کنید."
    hours: list[WorkDay] = Field(default_factory=list, max_length=14)  # when the owner answers; outside them away_text follows sent_text
    away_text: str = Field(default="الان خارج از ساعت پاسخ‌گویی هستیم و در اولین فرصت جواب می‌دهیم.", max_length=300)


class FeedbackBlock(BaseModel):
    """Customers rate the service 1-5 and may add a comment; the owner sees every rating and the average in the panel."""
    type: Literal["feedback"] = "feedback"
    id: str
    title: str
    prompt_text: str = "به تجربه‌ی خود امتیاز دهید:"
    comment_text: str = "اگر نظر یا پیشنهادی دارید بنویسید، یا «رد کردن» را بزنید:"
    thanks_text: str = "ممنون از نظر شما 🌟"
    aspects: list[Annotated[str, Field(min_length=1, max_length=30)]] = Field(default_factory=list, max_length=5)  # rate each (غذا، برخورد، سرعت) instead of one overall score
    follow_up_below: int = Field(default=0, ge=0, le=5)  # an overall rating below this asks for a phone number so the owner can call back (0 = never)
    follow_up_text: str = "متأسفیم که راضی نبودید. اگر شماره‌ی موبایل خود را بگذارید، مدیر با شما تماس می‌گیرد:"
    # automatic request: `after_hours` after a booking's time (or after an order is marked «تحویل شد») in block `after`,
    # the customer is asked for a rating once, with the stars right in the message
    after: str = ""
    after_hours: int = Field(default=2, ge=1, le=72)
    ask_text: str = Field(default="از «{what}» راضی بودید؟ لطفاً به ما امتیاز دهید:", max_length=200)


class MenuBlock(BaseModel):
    """A sub-menu: tapping its menu entry shows more buttons, each leading to another block (message, form, booking, another sub-menu...)."""
    type: Literal["menu"] = "menu"
    id: str
    title: str  # shown above the buttons
    items: list[MenuItem] = Field(min_length=1, max_length=10)


class QuizQuestion(BaseModel):
    question: str = Field(min_length=3, max_length=300)
    options: list[Annotated[str, Field(min_length=1, max_length=60)]] = Field(min_length=2, max_length=5)
    correct: int = Field(default=0, ge=0)  # index of the right option (ignored in a personality quiz)
    outcomes: list[str] = []  # personality quiz: the outcome id each option counts toward (same length as options)
    media: Literal["none", "image"] = "none"  # a photo shown with the question (the owner uploads it in «فایل‌ها»)

    @model_validator(mode="after")
    def _in_range(self):
        if self.correct >= len(self.options):
            raise ValueError("correct must be the index of one of the options")
        if self.outcomes and len(self.outcomes) != len(self.options):
            raise ValueError("outcomes needs one outcome id per option")
        return self


class QuizOutcome(BaseModel):
    """A personality-quiz result («کدام قهوه مناسب شماست» → «اسپرسو»)."""
    id: ShortId
    title: str = Field(min_length=1, max_length=60)
    text: str = Field(min_length=1, max_length=800)


class QuizBlock(BaseModel):
    """Multiple-choice questions with one right answer each; the customer gets a score at the end and the owner sees every result."""
    type: Literal["quiz"] = "quiz"
    id: str
    title: str
    questions: list[QuizQuestion] = Field(min_length=1, max_length=20)
    result_text: str = "نتیجه‌ی شما: {score} از {total} ({percent}٪)"  # {score} {total} {percent} {id}
    show_answers: bool = True  # tell right/wrong (and the right answer) after each question
    shuffle: bool = False  # questions in a random order for each attempt
    pick: int = Field(default=0, ge=0)  # ask only this many (random) questions of the bank (0 = all)
    pass_percent: int = Field(default=0, ge=0, le=100)  # >0: pass_text / fail_text follow the result
    pass_text: str = "🎉 قبول شدید!"
    fail_text: str = "متأسفانه نمره‌ی قبولی را کسب نکردید."
    one_attempt: bool = False  # a customer who already took the quiz sees their result instead of a new attempt
    show_history: bool = False  # a built-in «نتیجه‌های من» menu button lists the customer's own recent results (every quiz that has this on)
    pass_code: str = ""  # a discount code (of a catalog_order block) given to those who pass (needs pass_percent)
    personality: list[QuizOutcome] = Field(default_factory=list, max_length=8)  # non-empty = personality quiz: no right answers

    @model_validator(mode="after")
    def _placeholders(self):
        check_placeholders([self.result_text], {"score", "total", "percent", "id"})
        if self.personality:
            ids = {o.id for o in self.personality}
            if len(ids) != len(self.personality) or len(ids) < 2:
                raise ValueError("personality needs at least 2 outcomes with distinct ids")
            for q in self.questions:
                if not q.outcomes or not set(q.outcomes) <= ids:
                    raise ValueError(f"personality quiz: every question needs outcomes from {sorted(ids)}")
            if self.pass_percent or self.pass_code:
                raise ValueError("a personality quiz has no pass mark (no pass_percent / pass_code)")
        if self.pass_code and not self.pass_percent:
            raise ValueError("pass_code needs pass_percent")
        return self


class ReferralBlock(BaseModel):
    """Every customer gets a personal invite link; people who arrive through it as brand-new customers are counted for them.
    The reward is the owner's own text, handed out by the owner (nothing is paid automatically)."""
    type: Literal["referral"] = "referral"
    id: str
    title: str
    text: str = "دوستانتان را با لینک اختصاصی خودتان دعوت کنید."
    goal: int = Field(default=5, ge=1, le=1000)
    reward_text: str = "تبریک! به هدف رسیدید. برای دریافت جایزه با مدیر هماهنگ کنید."
    reward_code: str = ""  # a discount code (of a catalog_order block) sent automatically at the goal
    tiers: list["ReferralTier"] = Field(default_factory=list, max_length=4)  # more rewards at higher counts (10, 20 …)
    count_after: Literal["join", "order"] = "join"  # order: an invite counts only after the friend's first order/booking

    @model_validator(mode="after")
    def _tiers(self):
        goals = [self.goal, *(t.goal for t in self.tiers)]
        if goals != sorted(set(goals)):
            raise ValueError("tiers need goals above `goal`, increasing and distinct")
        return self


class ReferralTier(BaseModel):
    goal: int = Field(ge=2, le=1000)
    reward_text: str = Field(min_length=1, max_length=300)
    reward_code: str = ""


class AnonChatBlock(BaseModel):
    """Two customers are paired and chat without seeing who the other is (Bale/Telegram only; needs two real customers at once).
    Text only; links and phone numbers are not passed on; either side can end the chat or report the other, and the owner can ban people."""
    type: Literal["anon_chat"] = "anon_chat"
    id: str
    title: str
    intro_text: str = "با یک نفر ناشناس گفتگو کنید. نام و مشخصات شما دیده نمی‌شود. لطفاً مؤدب باشید؛ تخلف را می‌توانید گزارش دهید."
    topics: list[Annotated[str, Field(min_length=1, max_length=30)]] = Field(default_factory=list, max_length=8)  # rooms: people are paired within a topic
    max_minutes: int = Field(default=0, ge=0, le=240)  # a chat ends by itself after this long (0 = no limit)


class AdminNotifyBlock(BaseModel):
    type: Literal["admin_notify"] = "admin_notify"
    id: str
    on: str  # id of the block whose completion triggers the notification
    text: str = "ثبت جدید"
    min_total: int = Field(default=0, ge=0)          # orders: only those with a total of at least this (Toman)
    max_rating: int = Field(default=0, ge=0, le=5)   # feedback: only ratings of this or lower (e.g. 2 = unhappy customers)


Block = Annotated[
    Union[MessageBlock, FormBlock, BookingBlock, CatalogOrderBlock, FaqBlock, ContactBlock, FeedbackBlock, MenuBlock, QuizBlock, ReferralBlock, AnonChatBlock, AdminNotifyBlock],
    Field(discriminator="type"),
]


class BotSpec(BaseModel):
    name: str
    welcome: str
    menu: list[MenuItem] = Field(min_length=1)
    blocks: list[Block] = Field(min_length=1)
    gate: JoinGate | None = None  # forced channel join

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
            for e in (b.entries if b.type == "faq" else []):
                t = next((x for x in self.blocks if x.id == e.then), None) if e.then else None
                if e.then and (t is None or t.type == "admin_notify" or t.id == b.id):
                    raise ValueError(f"faq entry «{e.question[:30]}»: then must be the id of another block")
                if t is not None and not e.then_label:
                    e.then_label = (getattr(t, "title", "") or "ادامه")[:30]
            if b.type == "admin_notify" and b.on not in ids:
                raise ValueError(f"admin_notify '{b.id}' watches unknown block '{b.on}'")
            if b.type == "feedback" and b.after:
                t = next((x for x in self.blocks if x.id == b.after), None)
                if t is None or t.type not in ("booking", "catalog_order"):
                    raise ValueError(f"feedback '{b.id}': after must be the id of a booking or catalog_order block")
            for code in [getattr(b, "pass_code", ""), getattr(b, "reward_code", ""), *(t.reward_code for t in getattr(b, "tiers", []))]:
                if code and not any(norm_code(code) == norm_code(c.code) for x in self.blocks if x.type == "catalog_order" for c in x.discount_codes):
                    raise ValueError(f"'{b.id}': code {code!r} must be one of the discount_codes of a catalog_order block")
                for x in self.blocks:  # a reward must be earned: listing it in the public «کدهای تخفیف» button would defeat the quiz / referral
                    for c in (x.discount_codes if x.type == "catalog_order" else []):
                        if code and norm_code(code) == norm_code(c.code):
                            c.visible = False
            if b.type == "menu":
                for it in b.items:
                    t = next((x for x in self.blocks if x.id == it.block), None)
                    if t is None:
                        raise ValueError(f"sub-menu '{b.id}' item '{it.label}' points to unknown block '{it.block}'")
                    if t.type == "admin_notify":
                        raise ValueError("a menu cannot point to an admin_notify block")
        menus = {b.id: [i.block for i in b.items] for b in self.blocks if b.type == "menu"}

        def visit(node, path):
            if node in path:
                raise ValueError(f"sub-menus loop back on themselves: {' -> '.join([*path, node])}")
            for nxt in menus.get(node, []):
                if nxt in menus:
                    visit(nxt, [*path, node])

        for root in menus:
            visit(root, [])
        return self

    def block(self, block_id: str):
        return next(b for b in self.blocks if b.id == block_id)


for _m in (MessageBlock, ReferralBlock):  # they refer to WorkDay / ReferralTier, defined further down
    _m.model_rebuild()
