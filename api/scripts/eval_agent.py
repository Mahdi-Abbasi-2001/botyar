"""Regression evaluation of the builder agent against the REAL model (costs a few cents per full run).

    cd api && PYTHONPATH=. .venv/bin/python scripts/eval_agent.py            # all cases
    PYTHONPATH=. .venv/bin/python scripts/eval_agent.py weekly cancel        # only cases whose name contains a word

Every case sends one Persian request to a fresh account on a throw-away database, answers any clarifying questions with
a fixed sentence, and then checks what was built, not just that something was. Exit code 1 if any case regresses, so run
it before deploying any change to prompts.py / agent.py / spec.py.
"""
import json
import os
import sys
import tempfile
import time

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/eval.db"

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402

settings.register_per_ip_hour = 10_000  # one machine registers many throw-away accounts

ANSWER = "بقیه‌ی جزئیات رو خودت تصمیم بگیر و بساز."
INSIST = "همین الان بساز، هر چی خودت صلاح می‌دونی."  # sent when the agent still asks after ANSWER
MAX_COST, MAX_SECONDS = 0.02, 150


def kinds(spec):
    return [(b["type"], b.get("source", "")) for b in spec["blocks"] if b["type"] != "admin_notify"]


def blocks(spec, t):
    return [b for b in spec["blocks"] if b["type"] == t]


def slots(spec):
    return [s for b in blocks(spec, "booking") for s in b["slots"]]


# name, request, expected terminal status, structural check(spec, run_message) -> error string or None
CASES = [
    ("salon-slots", "برای آرایشگاه زنانه‌م ربات نوبت‌دهی می‌خوام. سه ساعت دارم: ۱۰ صبح، ۱۲ ظهر و ۴ عصر، هر ساعت فقط ۲ نفر. اسم و شماره بگیر و به من خبر بده.", "done",
     lambda s, m: None if blocks(s, "booking") else "no booking block"),
    ("restaurant-inline", "ربات سفارش غذا: چلوکباب ۳۸۰ هزار، جوجه ۳۲۰ هزار، قیمه ۲۶۰ هزار، سالاد ۶۰ هزار. نوع نان (سنگک یا لواش) رو بپرس. حداقل سفارش ۳۰۰ هزار. آدرس بگیر.", "done",
     lambda s, m: None if any(b.get("source") == "inline" and len(b["items"]) >= 4 for b in blocks(s, "catalog_order")) else "expected an inline menu with the dishes"),
    ("form-language-school", "ربات ثبت‌نام آموزشگاه زبان. نام، موبایل و سطح (مبتدی، متوسط، پیشرفته) رو بپرس و به من اطلاع بده.", "done",
     lambda s, m: None if blocks(s, "form") and any(f["kind"] == "choice" for b in blocks(s, "form") for f in b["fields"]) else "expected a form with a choice field"),
    ("bookstore-table", "فروشگاه کتاب دارم با چند هزار عنوان در ده‌ها دسته. فایل اکسل قیمت و موجودی رو بعدا آپلود می‌کنم. ربات سفارش می‌خوام. اسم و آدرس و موبایل بگیره.", "done",
     lambda s, m: None if any(b.get("source") == "table" and not b["items"] for b in blocks(s, "catalog_order")) else "expected a table-source catalog"),
    ("clinic-info+booking", "ربات کلینیک پوست: شنبه و سه‌شنبه ساعت ۴ عصر هر کدوم ظرفیت ۶ نفر. یک گزینه هم برای دیدن آدرس و ساعت کاری (خیابان ولیعصر، پلاک ۱۲) بذار.", "done",
     lambda s, m: None if blocks(s, "booking") and blocks(s, "message") else "expected booking + info message"),
    ("unsupported-secondary-feature", "ربات رزرو سالن ورزشی با پرداخت آنلاین و یادآوری پیامکی. شنبه ساعت ۶ عصر ظرفیت ۱۵ نفر.", "done",
     lambda s, m: None if ("پشتیبانی نمی" in m or "پشتیبانی نمی‌شود" in m) else "should state that payment/SMS are not supported"),
    ("repair-form", "ربات ثبت درخواست تعمیر موبایل: مدل گوشی (متن)، نوع مشکل (صفحه شکسته، باتری، شارژ، دیگر)، شماره تماس. به من اطلاع بده.", "done",
     lambda s, m: None if blocks(s, "form") else "expected a form"),
    ("large-cafe-table", "کافه‌م منوی بزرگی داره: ۱۵ نوع قهوه و نوشیدنی و ۱۰ تا شیرینی و کیک. بخش‌بندی کن و سفارش بگیر. اسم و موبایل بگیر و خبر بده.", "done",
     lambda s, m: None if blocks(s, "catalog_order") else "expected an order block"),
    # weekly slots
    ("weekly-two-classes", "برای باشگاهم ربات ثبت‌نام می‌خوام. کلاس یوگا هر شنبه ساعت ۸ صبح ظرفیت ۱۰ نفر و پیلاتس هر سه‌شنبه ساعت ۶ عصر ظرفیت ۱۲ نفر. نام و موبایل بگیر.", "done",
     lambda s, m: None if sorted((x.get("weekday"), x.get("time")) for x in slots(s)) == [(0, "08:00"), (3, "18:00")] else f"weekly slots wrong: {[(x.get('weekday'), x.get('time')) for x in slots(s)]}"),
    ("one-off-event", "ربات ثبت‌نام کارگاه عکاسی که فقط یک بار، ۲۵ مهر ساعت ۱۰ صبح برگزار می‌شود. ظرفیت ۲۰ نفر. نام و موبایل بگیر.", "done",
     lambda s, m: None if slots(s) and all(x.get("weekday") is None for x in slots(s)) else "a single dated event must not be weekly"),
    ("mixed-weekly-and-event", "ربات ثبت‌نام آموزشگاه: دوره‌ی هفتگی پنجشنبه‌ها ساعت ۱۰ صبح ظرفیت ۱۵ نفر، و یک کارگاه فقط در ۳۰ مهر ساعت ۵ عصر ظرفیت ۸ نفر. نام و موبایل بگیر.", "done",
     lambda s, m: None if sorted(x.get("weekday") is None for x in slots(s)) == [False, True] else "expected one weekly slot and one one-off slot"),
    # cancellation
    ("cancel-deadline", "ربات ثبت‌نام کلاس: هر پنجشنبه ساعت ۱۰ صبح ظرفیت ۸ نفر با لیست انتظار. مشتری‌ها بتونن تا ۲۴ ساعت قبل از کلاس لغو کنن. نام و موبایل بگیر.", "done",
     lambda s, m: None if any(b["allow_cancel"] and b["cancel_deadline_hours"] == 24 for b in blocks(s, "booking")) else "cancel deadline 24h not set"),
    ("cancel-order-window", "ربات سفارش کافه: لاته ۹۵ هزار، اسپرسو ۷۰ هزار. مشتری تا ۱۰ دقیقه بعد از ثبت بتونه سفارشش رو لغو کنه. نام و موبایل بگیر.", "done",
     lambda s, m: None if any(b["allow_cancel"] and b["cancel_window_minutes"] == 10 for b in blocks(s, "catalog_order")) else "order cancel window 10 min not set"),
    ("cancel-forbidden", "ربات رزرو سالن: شنبه ساعت ۵ عصر ظرفیت ۱۰ نفر. مشتری‌ها اجازه ندارن لغو کنن. نام و شماره بگیر.", "done",
     lambda s, m: None if all(not b["allow_cancel"] for b in blocks(s, "booking")) else "cancellation must be off"),
    ("cancel-default-on", "ربات نوبت‌دهی دندانپزشکی: دوشنبه ساعت ۹ صبح ظرفیت ۵ نفر. نام و موبایل بگیر.", "done",
     lambda s, m: None if all(b["allow_cancel"] for b in blocks(s, "booking")) else "cancellation should default to on"),
    # honesty
    ("declined-face", "یک ربات تشخیص چهره بساز", "declined", lambda s, m: None),
    ("declined-free-chat", "ربات هوش مصنوعی که به هر سوال مشتری‌ها آزادانه جواب بده", "declined", lambda s, m: None),
    ("declined-app", "یک اپلیکیشن موبایل برای فروشگاهم بساز", "declined", lambda s, m: None),
    ("vague-asks-first", "یه ربات برای باشگاهم می‌خوام", "needs_input", lambda s, m: None),
]
def sched(spec):
    return [b["schedule"] for b in blocks(spec, "booking") if b.get("schedule")]


APPOINTMENT_CASES = [
    ("appt-salon-staff-break", "ربات نوبت‌دهی آرایشگاه زنانه با دو آرایشگر سارا و مینا. شنبه تا چهارشنبه از ۹ صبح تا ۶ عصر، هر نوبت ۶۰ دقیقه، ساعت ۱ تا ۲ ناهار تعطیل. نام و موبایل بگیر و خبر بده.", "done",
     lambda s, m: None if sched(s) and sorted(d["weekday"] for d in sched(s)[0]["days"]) == [0, 1, 2, 3, 4] and sched(s)[0]["duration_minutes"] == 60
     and set(sched(s)[0]["staff"]) == {"سارا", "مینا"} and (sched(s)[0]["break_start"], sched(s)[0]["break_end"]) == ("13:00", "14:00")
     else f"salon schedule wrong: {json.dumps(sched(s), ensure_ascii=False)[:300]}"),
    ("appt-clinic-short-visits", "ربات ویزیت دکتر پوست: دوشنبه و چهارشنبه از ۴ تا ۸ عصر، هر ویزیت ۱۵ دقیقه. نام و موبایل بگیر.", "done",
     lambda s, m: None if sched(s) and sorted(d["weekday"] for d in sched(s)[0]["days"]) == [2, 4] and sched(s)[0]["duration_minutes"] == 15
     and all((d["start"], d["end"]) == ("16:00", "20:00") for d in sched(s)[0]["days"]) and not sched(s)[0]["staff"] else f"clinic schedule wrong: {json.dumps(sched(s), ensure_ascii=False)[:300]}"),
    ("appt-vs-class-stays-slots", "ربات ثبت‌نام کلاس پیلاتس: هر سه‌شنبه ساعت ۶ عصر، ظرفیت ۱۲ نفر. نام و موبایل بگیر.", "done",
     lambda s, m: None if slots(s) and not sched(s) else "a fixed class must stay a slot, not a schedule"),
    ("appt-and-class-two-blocks", "ربات استودیو: کلاس گروهی یوگا هر شنبه ساعت ۸ صبح ظرفیت ۱۰ نفر، و همچنین نوبت مشاوره‌ی خصوصی جداگانه دوشنبه‌ها از ۱۰ تا ۱۲ هر ۳۰ دقیقه. نام و موبایل بگیر.", "done",
     lambda s, m: None if slots(s) and sched(s) and all(bool(b["slots"]) != bool(b.get("schedule")) for b in blocks(s, "booking")) else "expected one slots block and one schedule block"),
    ("appt-default-duration", "ربات نوبت‌دهی مشاور تحصیلی، یکشنبه‌ها از ۱۰ صبح تا ۲ بعدازظهر. نام و موبایل بگیر.", "done",
     lambda s, m: None if sched(s) and sched(s)[0]["duration_minutes"] and ("۳۰" in m or "30" in m or "مدت" in m) else "should assume a duration and say so"),
]

def faqs(spec):
    return [b for b in blocks(spec, "faq")]


FAQ_CASES = [
    ("faq-with-facts", "ربات پرسش‌های متداول برای کلینیک دندانپزشکی: ساعت کاری شنبه تا چهارشنبه ۹ تا ۱۸، آدرس خیابان ولیعصر پلاک ۱۲، هزینه ویزیت ۲۵۰ هزار تومان، پارکینگ اختصاصی داریم و بیمه تکمیلی قبول می‌کنیم.", "done",
     lambda s, m: None if faqs(s) and len(faqs(s)[0]["entries"]) >= 4 and "ولیعصر" in json.dumps(faqs(s)[0]["entries"], ensure_ascii=False) and "۲۵۰" in json.dumps(faqs(s)[0]["entries"], ensure_ascii=False)
     and any(b["on"] == faqs(s)[0]["id"] for b in blocks(s, "admin_notify")) else "expected an FAQ with the owner's facts and a notification block"),
    ("faq-no-invented-facts", "یه ربات پرسش و پاسخ برای کافه‌م بساز", "needs_input", lambda s, m: None),
    ("faq-forced-build-no-invention", "ربات سؤال‌های متداول برای باشگاه ورزشی", "done",
     lambda s, m: None if faqs(s) and not any(ch in json.dumps(faqs(s)[0]["entries"], ensure_ascii=False) for ch in "0123456789۰۱۲۳۴۵۶۷۸۹") else "answers contain digits although the owner gave no facts: invented hours/prices?"),
    ("faq-plus-booking", "ربات کلینیک: نوبت‌دهی دوشنبه‌ها از ۴ تا ۸ عصر هر ۲۰ دقیقه، و بخش سؤال‌های متداول: آدرس ما خیابان آزادی پلاک ۵ است و ویزیت ۳۰۰ هزار تومان.", "done",
     lambda s, m: None if faqs(s) and sched(s) else "expected an FAQ block AND an appointment schedule"),
]

CONTACT_CASES = [
    ("contact-basic", "ربات فروشگاه لوازم‌التحریر که مشتری‌ها بتوانند برای من پیام بفرستند و من خودم جواب بدهم", "done",
     lambda s, m: None if blocks(s, "contact") and any(b["on"] == blocks(s, "contact")[0]["id"] for b in blocks(s, "admin_notify")) else "expected a contact block watched by admin_notify"),
    ("contact-with-order", "ربات کافه: منوی لاته ۹۵ هزار تومان و اسپرسو ۷۰ هزار تومان، و مشتری بتواند به من پیام بدهد", "done",
     lambda s, m: None if blocks(s, "contact") and blocks(s, "catalog_order") else "expected contact AND catalog_order"),
]

def _orders(s):
    return blocks(s, "catalog_order")


PRICING_CASES = [
    ("pricing-fee-and-code", "ربات کافه: لاته ۱۰۰ هزار تومان، کیک ۵۰ هزار تومان. هزینه ارسال ۳۰ هزار تومان، رایگان برای سفارش بالای ۲۰۰ هزار تومان. کد تخفیف YALDA ده درصد.", "done",
     lambda s, m: None if _orders(s) and _orders(s)[0]["delivery_fee"] == 30000 and _orders(s)[0]["free_delivery_over"] == 200000
     and any(c["code"].upper() == "YALDA" and c["percent"] == 10 for c in _orders(s)[0]["discount_codes"]) else "fee/free-over/code not captured exactly"),
    ("pricing-no-invented-code", "ربات سفارش شیرینی با کد تخفیف", "needs_input", lambda s, m: None),
    ("pricing-amount-code-limited", "ربات کافه با لاته ۹۰ هزار تومان. کد تخفیف WELCOME پنجاه هزار تومان تخفیف می‌دهد، فقط برای ۱۰ نفر اول.", "done",
     lambda s, m: None if _orders(s) and any(c["code"].upper() == "WELCOME" and c["amount"] == 50000 and c["max_uses"] == 10 for c in _orders(s)[0]["discount_codes"]) else "amount code with max_uses not captured"),
]

FEEDBACK_CASES = [
    ("payment-online-order", "ربات کافه: لاته ۹۵ هزار تومان و کیک ۱۱۰ هزار تومان. مشتری باید سفارشش را همان‌جا آنلاین پرداخت کند.", "done",
     lambda s, m: None if _orders(s) and _orders(s)[0].get("payment") == "online" and ("توکن" in m or "کیف پول" in m or "انتشار" in m) else "payment=online and a note about the wallet token/own bot expected: " + m[:200]),
    ("payment-for-booking-declined-honestly", "ربات نوبت‌دهی دندانپزشکی دوشنبه‌ها ۹ تا ۱۳ هر ۳۰ دقیقه، و مشتری برای رزرو نوبت بیعانه آنلاین بپردازد", "done",
     lambda s, m: None if "پشتیبانی نمی" in m else "must say booking deposits are not supported: " + m[:200]),
    ("reminder-24h", "ربات آرایشگاه: نوبت‌دهی شنبه تا چهارشنبه ۹ تا ۱۷ هر ۳۰ دقیقه. ۲۴ ساعت قبل از نوبت به مشتری یادآوری بده.", "done",
     lambda s, m: None if sched(s) and all(b.get("reminder_hours") == 24 for b in blocks(s, "booking")) else "reminder_hours should be 24"),
    ("reminder-one-off-event-honest", "ربات ثبت‌نام همایش یک‌روزه ۱۵ مهر، ظرفیت ۱۰۰ نفر. یک روز قبل یادآوری بفرست.", "done",
     lambda s, m: None if ("یادآوری" in m and ("ساعت" in m or "پشتیبانی نمی" in m)) or all(not b.get("reminder_hours") for b in blocks(s, "booking")) else "must not silently promise a reminder for an event without a clock time"),
    ("order-edit-not-promised", "ربات کافه با لاته ۹۵ هزار تومان. مشتری بتواند سفارشش را ویرایش کند و آیتم‌هایش را عوض کند", "done",
     lambda s, m: None if ("پشتیبانی نمی" in m) else "should say order editing is not supported: " + m[:300]),
    ("feedback-basic", "ربات رستوران که مشتری‌ها بتوانند به غذا امتیاز ۱ تا ۵ بدهند و نظرشان را بنویسند، و به من اطلاع بدهد", "done",
     lambda s, m: None if blocks(s, "feedback") and any(b["on"] == blocks(s, "feedback")[0]["id"] for b in blocks(s, "admin_notify")) else "expected feedback + notify"),
    ("feedback-with-booking", "ربات آرایشگاه: نوبت‌دهی شنبه تا چهارشنبه ۹ تا ۱۷ هر ۳۰ دقیقه و بخش ثبت نظر مشتری", "done",
     lambda s, m: None if blocks(s, "feedback") and sched(s) else "expected feedback AND schedule booking"),
]

PERSONALIZE_CASES = [
    ("greet-by-name", "یه ربات بساز که وقتی کاربر /start می‌زنه بهش سلام کنه و اسمشو بپرسه، بعد با اسم خودش بهش خوش‌آمد بگه.", "done",
     lambda s, m: None if blocks(s, "form") else "should build the closest thing (a form asking the name) and say that echoing the name is limited"),
]

PARTIAL_CASES = [
    ("partial-live-clock", "یه ربات بساز که وقتی کاربر /start می‌زنه دو تا دکمه «ساعت فعلی» و «راهنما» نشون بده.", "done",
     lambda s, m: None if len(s.get("menu", [])) >= 1 and ("پشتیبانی نمی" in m) else "should build the supported button(s) and say the live clock is not supported: " + m[:200]),
]

RANDOM_CASES = [
    ("random-quote", "یه ربات بساز که با زدن دکمه «جمله انگیزشی» هر بار یک جمله انگیزشی تصادفی نمایش بده.", "done",
     lambda s, m: None if any(len(b.get("variants", [])) >= 5 for b in blocks(s, "message")) else "expected a message block with at least 5 variants"),
    ("random-no-invented-facts", "ربات کافه من که با دکمه «پیشنهاد امروز» یکی از پیشنهادهای ما رو تصادفی نشون بده", "needs_input", lambda s, m: None),
]

# appended by later features (appointment calendars, FAQ, owner chat, delivery/discounts) — see EXTRA_CASES below
EXTRA_CASES: list = [*APPOINTMENT_CASES, *FAQ_CASES, *CONTACT_CASES, *PRICING_CASES, *FEEDBACK_CASES, *PERSONALIZE_CASES, *PARTIAL_CASES, *RANDOM_CASES]


def run_case(c, i, name, text, want_status, check):
    tok = c.post("/api/auth/register", json={"email": f"eval{i}@example.com", "password": "123456"}).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    bot = c.post("/api/bots/draft", headers=H).json()["id"]
    t0, cost, repairs, status, msg = time.time(), 0.0, 0, "?", ""
    for m in (text, ANSWER, INSIST):
        rid = c.post(f"/api/bots/{bot}/builder", headers=H, json={"text": m}).json()["run_id"]
        r = c.get(f"/api/bots/{bot}/builder/runs/{rid}", headers=H).json()
        cost += r["result"].get("cost_usd", 0)
        repairs += sum("رفع خطاهای" in e for e in r["events"])
        status, msg = r["status"], r["result"].get("message", "")
        if status != "needs_input" or want_status == "needs_input":
            break
    secs = time.time() - t0
    errors = []
    if status != want_status:
        errors.append(f"status {status!r}, wanted {want_status!r}")
    spec = (c.get(f"/api/bots/{bot}", headers=H).json().get("spec")) or {"blocks": []}
    tests = c.get(f"/api/bots/{bot}/tests", headers=H).json()["results"]
    if want_status == "done":
        for t in tests:
            if not t["passed"] and os.environ.get("EVAL_VERBOSE"):
                print("   FAILED SCENARIO:", json.dumps(t, ensure_ascii=False)[:1500])
        if not tests or not all(t["passed"] for t in tests):
            errors.append(f"tests {sum(t['passed'] for t in tests)}/{len(tests)}")
        err = check(spec, msg)
        if err:
            errors.append(err)
    if cost > MAX_COST:
        errors.append(f"cost ${cost:.4f} over ${MAX_COST}")
    if secs > MAX_SECONDS:
        errors.append(f"{secs:.0f}s over {MAX_SECONDS}s")
    return dict(name=name, ok=not errors, errors=errors, secs=secs, cost=cost, repairs=repairs, tests=f"{sum(t['passed'] for t in tests)}/{len(tests)}")


def main(argv):
    only = [a for a in argv if not a.startswith("-")]
    cases = [x for x in CASES + EXTRA_CASES if not only or any(w in x[0] for w in only)]
    results = []
    with TestClient(app) as c:
        for i, case in enumerate(cases):
            res = run_case(c, i, *case)
            results.append(res)
            print(f"{'PASS' if res['ok'] else 'FAIL'} {res['name']:32} {res['secs']:5.0f}s ${res['cost']:.4f} repairs={res['repairs']} tests={res['tests']}" + ("" if res["ok"] else "  <- " + "; ".join(res["errors"])), flush=True)
    bad = [r for r in results if not r["ok"]]
    print(f"\n{len(results) - len(bad)}/{len(results)} passed | zero-repair {sum(r['repairs'] == 0 for r in results)}/{len(results)} | total ${sum(r['cost'] for r in results):.4f} | {sum(r['secs'] for r in results):.0f}s")
    json.dump(results, open(os.path.join(tempfile.gettempdir(), "eval_agent_last.json"), "w"), ensure_ascii=False, indent=1)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
