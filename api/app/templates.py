"""Hand-written starter specs (Day 1, no LLM). Also used as few-shot examples for the design agent."""
from .spec import BotSpec

WORKSHOP = {
    "name": "ربات کارگاه سفالگری",
    "welcome": "سلام! به کارگاه سفالگری سفال‌یار خوش آمدید.",
    "menu": [
        {"label": "ثبت‌نام در کارگاه", "block": "booking"},
        {"label": "درباره‌ی کارگاه", "block": "about"},
    ],
    "blocks": [
        {"type": "message", "id": "about", "text": "کارگاه سفالگری هر پنجشنبه برگزار می‌شود. هزینه‌ی هر جلسه ۴۵۰ هزار تومان."},
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
         "allow_cancel": True, "cancel_deadline_hours": 12,
         "slots": [
             {"id": "yoga", "label": "یوگا، شنبه ساعت ۸ صبح", "capacity": 10, "weekday": 0, "time": "08:00"},
             {"id": "pilates", "label": "پیلاتس، سه‌شنبه ساعت ۶ عصر", "capacity": 12, "weekday": 3, "time": "18:00"},
             {"id": "camp", "label": "کارگاه ویژه‌ی ۲۵ مهر", "capacity": 20},
         ]},
        {"type": "admin_notify", "id": "notify", "on": "classes", "text": "ثبت‌نام جدید در کلاس باشگاه"},
    ],
}

# Style reference for the agent only: individual appointments generated from working hours, with two staff members.
APPOINTMENT_EXAMPLE = {
    "name": "ربات نوبت‌دهی آرایشگاه",
    "welcome": "سلام! برای رزرو نوبت از منو استفاده کنید.",
    "menu": [{"label": "رزرو نوبت", "block": "appt"}],
    "blocks": [
        {"type": "booking", "id": "appt", "title": "رزرو نوبت", "allow_cancel": True, "cancel_deadline_hours": 3,
         "schedule": {"days": [{"weekday": 0, "start": "09:00", "end": "18:00"}, {"weekday": 1, "start": "09:00", "end": "18:00"},
                               {"weekday": 3, "start": "09:00", "end": "18:00"}],
                      "duration_minutes": 60, "capacity": 1, "days_ahead": 7, "staff": ["سارا", "مینا"],
                      "break_start": "13:00", "break_end": "14:00"}},
        {"type": "admin_notify", "id": "notify", "on": "appt", "text": "نوبت جدید ثبت شد"},
    ],
}

# Style reference for the agent only: an FAQ bot. Facts come ONLY from what the owner said.
FAQ_EXAMPLE = {
    "name": "ربات پرسش‌های متداول کلینیک",
    "welcome": "سلام! پاسخ سؤال‌های رایج را اینجا پیدا کنید.",
    "menu": [{"label": "سؤال دارید؟", "block": "faq"}],
    "blocks": [
        {"type": "faq", "id": "faq", "title": "پرسش‌های متداول",
         "entries": [
             {"question": "ساعت کاری کلینیک چیست؟", "answer": "شنبه تا چهارشنبه از ۹ صبح تا ۶ عصر."},
             {"question": "آدرس کلینیک کجاست؟", "answer": "خیابان ولیعصر، پلاک ۱۲."},
             {"question": "هزینه ویزیت چقدر است؟", "answer": "ویزیت اولیه ۲۵۰ هزار تومان است."},
         ]},
        {"type": "admin_notify", "id": "notify_faq", "on": "faq", "text": "سؤال جدید بدون پاسخ"},
    ],
}

# Style reference for the agent only: customers message the owner, who answers from the panel.
CONTACT_EXAMPLE = {
    "name": "ربات فروشگاه گل",
    "welcome": "سلام! به فروشگاه گل خوش آمدید.",
    "menu": [{"label": "پیام به مدیر", "block": "contact"}],
    "blocks": [
        {"type": "contact", "id": "contact", "title": "ارتباط با مدیر"},
        {"type": "admin_notify", "id": "notify_contact", "on": "contact", "text": "پیام جدید از مشتری"},
    ],
}

FEEDBACK_EXAMPLE = {
    "name": "ربات نظرسنجی رستوران",
    "welcome": "سلام! نظر شما برای ما ارزشمند است.",
    "menu": [{"label": "ثبت نظر", "block": "fb"}],
    "blocks": [
        {"type": "feedback", "id": "fb", "title": "نظرسنجی رستوران"},
        {"type": "admin_notify", "id": "notify_fb", "on": "fb", "text": "نظر جدید ثبت شد"},
    ],
}

TEMPLATES = {"workshop": WORKSHOP, "cafe": CAFE}


def load_template(key: str) -> BotSpec:
    return BotSpec.model_validate(TEMPLATES[key])
