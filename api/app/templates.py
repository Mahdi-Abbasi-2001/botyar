"""Hand-written starter specs (Day 1, no LLM). Also used as few-shot examples for the design agent."""
from .spec import BotSpec

WORKSHOP = {
    "name": "ربات کارگاه سفالگری",
    "welcome": "سلام! به کارگاه سفالگری سفال‌یار خوش آمدید.",
    "menu": [
        {"label": "ثبت‌نام در کارگاه", "block": "booking"},
        {"label": "درباره کارگاه", "block": "about"},
    ],
    "blocks": [
        {"type": "message", "id": "about", "text": "کارگاه سفالگری هر پنجشنبه برگزار می‌شود. هزینه هر جلسه ۴۵۰ هزار تومان."},
        {
            "type": "booking",
            "id": "booking",
            "title": "ثبت‌نام کارگاه سفالگری",
            "slots": [
                {"id": "thu1", "label": "پنجشنبه ساعت ۱۰ صبح", "capacity": 12},
                {"id": "thu2", "label": "پنجشنبه ساعت ۴ عصر", "capacity": 12},
            ],
            "waitlist": False,
        },
        {"type": "admin_notify", "id": "notify_booking", "on": "booking", "text": "ثبت‌نام جدید در کارگاه"},
    ],
}

CAFE = {
    "name": "ربات سفارش کافه",
    "welcome": "سلام! به کافه نیمکت خوش آمدید.",
    "menu": [
        {"label": "ثبت سفارش", "block": "order"},
        {"label": "ساعت کاری", "block": "hours"},
    ],
    "blocks": [
        {"type": "message", "id": "hours", "text": "همه روزه از ۹ صبح تا ۱۱ شب."},
        {
            "type": "catalog_order",
            "id": "order",
            "title": "منوی کافه",
            "items": [
                {"id": "latte", "name": "لاته", "price": 95000, "options": [{"name": "شیر", "choices": ["معمولی", "بادام"]}]},
                {"id": "espresso", "name": "اسپرسو", "price": 70000},
                {"id": "cake", "name": "کیک شکلاتی", "price": 110000},
            ],
            "max_items": 5,
            "min_total": 100000,
        },
        {"type": "admin_notify", "id": "notify_order", "on": "order", "text": "سفارش جدید"},
    ],
}

TEMPLATES = {"workshop": WORKSHOP, "cafe": CAFE}


def load_template(key: str) -> BotSpec:
    return BotSpec.model_validate(TEMPLATES[key])
