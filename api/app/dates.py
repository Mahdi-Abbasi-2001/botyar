"""Calendar helpers for recurring weekly slots: Tehran time, Persian weekdays, Gregorian -> Jalali."""
from __future__ import annotations

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
