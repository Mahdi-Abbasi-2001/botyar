"""Calendar helpers: Tehran time, Persian weekdays, Gregorian <-> Jalali, and reading a Jalali date a customer typed."""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TEHRAN = ZoneInfo("Asia/Tehran")
WEEKDAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]  # index 0 = Saturday
# Fixed clock used whenever the agent's tests run, so tests never depend on today's date.
TEST_NOW = datetime(2026, 10, 3, 12, 0, tzinfo=TEHRAN)  # Saturday, 1405/07/11


def now_tehran() -> datetime:
    return datetime.now(TEHRAN)


def persian_weekday(d: date) -> int:
    """0 = Saturday ... 6 = Friday."""
    return (d.weekday() + 2) % 7


def to_jalali(d: date) -> tuple[int, int, int]:
    gy, gm, gd = d.year, d.month, d.day
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy, gy = 979, gy - 1600
    else:
        jy, gy = 0, gy - 621
    gy2 = gy + 1 if gm > 2 else gy
    days = 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 - 80 + gd + g_d_m[gm - 1]
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm, jd = 1 + days // 31, 1 + days % 31
    else:
        jm, jd = 7 + (days - 186) // 30, 1 + (days - 186) % 30
    return jy, jm, jd


MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def from_jalali(jy: int, jm: int, jd: int) -> date | None:
    """Jalali -> Gregorian; None for a day that does not exist (e.g. 30 Esfand of a common year)."""
    if not (1 <= jm <= 12 and 1 <= jd <= 31 and 1200 <= jy <= 1600):
        return None
    guess = date(jy + 621, 3, 21) + timedelta(days=(jm - 1) * 31 if jm <= 7 else 186 + (jm - 7) * 30) + timedelta(days=jd - 1)
    for delta in (0, -1, 1, -2, 2, -3, 3):
        g = guess + timedelta(days=delta)
        if to_jalali(g) == (jy, jm, jd):
            return g
    return None


def parse_jalali(text: str, today: date | None = None) -> date | None:
    """A date as people type it: «۱۴۰۳/۰۸/۱۵», «1403-8-15», «۱۵ آبان ۱۴۰۳», or «۱۵ آبان» (this year)."""
    t = text.translate(_DIGITS).strip()
    m = re.fullmatch(r"(\d{4})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{1,2})", t)
    if m:
        return from_jalali(int(m[1]), int(m[2]), int(m[3]))
    m = re.fullmatch(r"(\d{1,2})\s*(" + "|".join(MONTHS) + r")(?:\s*(?:ماه)?\s*(\d{4}))?", t.replace("ماه ", "").strip())
    if m:
        year = int(m[3]) if m[3] else to_jalali(today or now_tehran().date())[0]
        return from_jalali(year, MONTHS.index(m[2]) + 1, int(m[1]))
    return None


def jalali_str(d: date) -> str:
    y, m, dd = to_jalali(d)
    return f"{y}/{m:02d}/{dd:02d}"


def next_occurrences(now: datetime, weekday: int, hhmm: str, n: int) -> list[date]:
    """The next `n` dates (strictly in the future, counting the start time) on which this weekly slot happens."""
    h, m = (int(x) for x in hhmm.split(":"))
    out: list[date] = []
    for i in range(0, 7 * (n + 2)):
        day = now.date() + timedelta(days=i)
        if persian_weekday(day) != weekday:
            continue
        if datetime.combine(day, time(h, m), tzinfo=now.tzinfo) > now:
            out.append(day)
            if len(out) == n:
                break
    return out
