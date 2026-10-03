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

# Style reference for the agent only (not offered as a template in the UI): a repeating weekly class.
WEEKLY_EXAMPLE = {
    "name": "ربات کلاس‌های باشگاه",
    "welcome": "سلام! برای ثبت‌نام در کلاس‌های هفتگی باشگاه از منو استفاده کنید.",
    "menu": [{"label": "ثبت‌نام در کلاس", "block": "classes"}],
    "blocks": [
        {"type": "booking", "id": "classes", "title": "ثبت‌نام کلاس هفتگی", "waitlist": True, "occurrences": 2,
         "slots": [
             {"id": "yoga", "label": "یوگا، شنبه ساعت ۸ صبح", "capacity": 10, "weekday": 0, "time": "08:00"},
             {"id": "pilates", "label": "پیلاتس، سه‌شنبه ساعت ۶ عصر", "capacity": 12, "weekday": 3, "time": "18:00"},
             {"id": "camp", "label": "کارگاه ویژه‌ی ۲۵ مهر", "capacity": 20},
         ]},
        {"type": "admin_notify", "id": "notify", "on": "classes", "text": "ثبت‌نام جدید در کلاس باشگاه"},
    ],
}

TEMPLATES = {"workshop": WORKSHOP, "cafe": CAFE}


def load_template(key: str) -> BotSpec:
    return BotSpec.model_validate(TEMPLATES[key])
