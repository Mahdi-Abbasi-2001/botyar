"""Send odd / tiny first-minute requests to the REAL agent and print what it does (no pass/fail; read the output).
Costs about a cent for ten requests.   PYTHONPATH=. .venv/bin/python scripts/odd_requests.py"""
import os
import sys
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/odd.db"

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402

settings.register_per_ip_hour = 10_000

REQUESTS = [
    "یه ربات بساز که فقط بگه سلام",
    "ربات ماشین حساب که دو تا عدد بگیره و جمعشون رو بگه",
    "یه ربات جوک بساز که هر بار یه جوک تصادفی بگه",
    "ربات که قیمت لحظه‌ای دلار و طلا رو نشون بده",
    "ربات فروشگاه لباس که عکس محصولات رو هم نشون بده",
    "ربات نظرسنجی که از کاربر ۳ تا سؤال بپرسه و نتیجه رو برای من بفرسته",
    "ربات که هر روز صبح ساعت ۸ برای همه‌ی مشتری‌ها پیام صبح بخیر بفرسته",
    "ربات ثبت سفارش پیتزا",
    "ربات که اگه کاربر بگه سلام جواب سلام بده و اگه گفت خداحافظ خداحافظی کنه",
    "ربات پشتیبانی که مشکل مشتری رو بگیره و بهش شماره پیگیری بده",
]


BATCH2 = [
    "ربات مسابقه که ۵ تا سؤال چهارگزینه‌ای بپرسه و در آخر بگه چند تا درست جواب دادی",
    "ربات که بگه تا شروع کنسرت چند روز مونده",
    "ربات با منوی تودرتو: دکمه «محصولات» که بعدش دو تا دکمه «لپ‌تاپ» و «موبایل» نشون بده و هرکدوم توضیح خودشو بگه",
    "ربات که اسم و شماره بگیره و بعد یه فایل PDF کاتالوگ برای دانلود بفرسته",
    "ربات که آدرس مغازه رو روی نقشه (لوکیشن) نشون بده",
    "ربات رزرو میز رستوران که برای ۲ تا ۸ نفر میز بگیره و ساعت ۱۸ تا ۲۳ هر ۹۰ دقیقه",
    "ربات که به انگلیسی هم جواب بده، کاربر زبانشو انتخاب کنه",
    "ربات که کد تخفیف شخصی برای هر مشتری بسازه",
    "ربات که لیست قیمت خدمات آرایشگاه رو نشون بده: کوتاهی ۲۰۰ هزار، رنگ ۹۰۰ هزار، کراتینه ۲ میلیون",
    "ربات که شماره موبایل بگیره و بعد کد تأیید پیامکی بفرسته",
]
if len(sys.argv) > 2 and sys.argv[1] == "say":  # odd_requests.py say "<one request>"
    REQUESTS = [sys.argv[2]]
    del sys.argv[1:3]
elif len(sys.argv) > 1 and sys.argv[1] == "batch2":
    REQUESTS = BATCH2
    sys.argv.pop(1)


def main(only):
    with TestClient(app) as c:
        for i, text in enumerate(REQUESTS):
            if only and not any(w in str(i + 1) for w in only):
                continue
            tok = c.post("/api/auth/register", json={"username": f"odd{i}", "password": "123456"}).json()["token"]
            H = {"Authorization": f"Bearer {tok}"}
            bot = c.post("/api/bots/draft", headers=H).json()["id"]
            rid = c.post(f"/api/bots/{bot}/builder", headers=H, json={"text": text}).json()["run_id"]
            r = c.get(f"/api/bots/{bot}/builder/runs/{rid}", headers=H).json()
            spec = c.get(f"/api/bots/{bot}", headers=H).json().get("spec") or {}
            res = r["result"]
            print(f"\n#{i + 1} {text}\n  status={r['status']} cost=${res.get('cost_usd', 0):.4f} menu={[m['label'] for m in spec.get('menu', [])]} blocks={[b['type'] for b in spec.get('blocks', [])]}")
            print("  agent:", (res.get("message") or "")[:420].replace("\n", " "))
            for q in res.get("questions") or []:
                print("  ask:", q)


if __name__ == "__main__":
    main(sys.argv[1:])
