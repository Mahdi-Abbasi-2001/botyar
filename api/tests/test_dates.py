from datetime import date, datetime

from app.dates import TEHRAN, TEST_NOW, jalali_str, next_occurrences, persian_weekday, to_jalali


def test_jalali_matches_known_calendar_dates():
    assert to_jalali(date(2026, 10, 3)) == (1405, 7, 11)     # also what Liara's console showed on this day
    assert to_jalali(date(2026, 3, 21)) == (1405, 1, 1)      # Nowruz 1405
    assert to_jalali(date(2025, 3, 21)) == (1404, 1, 1)
    assert to_jalali(date(2024, 3, 20)) == (1403, 1, 1)
    assert to_jalali(date(2025, 3, 20)) == (1403, 12, 30)    # 1403 is a leap year: Esfand has 30 days
    assert to_jalali(date(2026, 9, 23)) == (1405, 7, 1)      # 1 Mehr
    assert to_jalali(date(2026, 12, 21)) == (1405, 9, 30)
    assert jalali_str(date(2026, 10, 8)) == "1405/07/16"


def test_persian_weekdays():
    assert persian_weekday(date(2026, 10, 3)) == 0   # Saturday
    assert persian_weekday(date(2026, 10, 8)) == 5   # Thursday
    assert persian_weekday(date(2026, 10, 9)) == 6   # Friday


def test_test_clock_is_a_saturday_noon_in_tehran():
    assert TEST_NOW.tzinfo is not None and persian_weekday(TEST_NOW.date()) == 0 and TEST_NOW.hour == 12


def test_next_occurrences_future_only_and_time_aware():
    sat_noon = TEST_NOW
    assert next_occurrences(sat_noon, 5, "10:00", 2) == [date(2026, 10, 8), date(2026, 10, 15)]   # Thursdays
    assert next_occurrences(sat_noon, 0, "18:00", 2) == [date(2026, 10, 3), date(2026, 10, 10)]   # today 18:00 is still ahead
    assert next_occurrences(sat_noon, 0, "10:00", 2) == [date(2026, 10, 10), date(2026, 10, 17)]  # today 10:00 already started
    just_before = datetime(2026, 10, 8, 9, 59, tzinfo=TEHRAN)
    assert next_occurrences(just_before, 5, "10:00", 1) == [date(2026, 10, 8)]
    just_after = datetime(2026, 10, 8, 10, 0, tzinfo=TEHRAN)
    assert next_occurrences(just_after, 5, "10:00", 1) == [date(2026, 10, 15)]
