from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from derby.core.utils.business_date import business_date
from derby.core.utils.time_utils import to_cairo


def test_normal_day_default_close_time():
    # 2024-06-15 12:00 UTC is a normal afternoon in Cairo.
    utc_dt = datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc)
    assert business_date(utc_dt) == to_cairo(utc_dt).date()


def test_2359_boundary_default_close_time():
    # Just before midnight Cairo time still belongs to that calendar day;
    # just after midnight belongs to the next one (close_time >= noon means
    # no shift is applied, so the boundary is plain midnight).
    offset = to_cairo(datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc)).utcoffset()
    cairo_235900 = datetime(2024, 6, 15, 23, 59, 0)
    utc_at_235900 = (cairo_235900 - offset).replace(tzinfo=timezone.utc)
    assert business_date(utc_at_235900) == date(2024, 6, 15)

    cairo_000100_next_day = datetime(2024, 6, 16, 0, 1, 0)
    utc_at_000100 = (cairo_000100_next_day - offset).replace(tzinfo=timezone.utc)
    assert business_date(utc_at_000100) == date(2024, 6, 16)


def test_close_time_0300_early_morning_belongs_to_previous_day():
    close_time = time(3, 0)
    offset = to_cairo(datetime(2024, 1, 10, 12, 0, tzinfo=timezone.utc)).utcoffset()

    # 01:30 Cairo local time, close time 03:00 -> previous business day.
    cairo_0130 = datetime(2024, 1, 10, 1, 30, 0)
    utc_at_0130 = (cairo_0130 - offset).replace(tzinfo=timezone.utc)
    assert business_date(utc_at_0130, close_time) == date(2024, 1, 9)

    # Exactly at close time (03:00) is still the previous business day (inclusive boundary).
    cairo_0300 = datetime(2024, 1, 10, 3, 0, 0)
    utc_at_0300 = (cairo_0300 - offset).replace(tzinfo=timezone.utc)
    assert business_date(utc_at_0300, close_time) == date(2024, 1, 9)

    # One minute after close time starts the new business day.
    cairo_0301 = datetime(2024, 1, 10, 3, 1, 0)
    utc_at_0301 = (cairo_0301 - offset).replace(tzinfo=timezone.utc)
    assert business_date(utc_at_0301, close_time) == date(2024, 1, 10)

    # Daytime hours (after close_time, before midnight) belong to the same calendar day.
    cairo_1000 = datetime(2024, 1, 10, 10, 0, 0)
    utc_at_1000 = (cairo_1000 - offset).replace(tzinfo=timezone.utc)
    assert business_date(utc_at_1000, close_time) == date(2024, 1, 10)


def _find_cairo_dst_transition(year: int):
    """Scan a year for the day Cairo's UTC offset changes (a DST transition)."""
    start = datetime(year, 1, 1, 12, 0, tzinfo=timezone.utc)
    previous_offset = to_cairo(start).utcoffset()
    for day_number in range(1, 366):
        current = start + timedelta(days=day_number)
        current_offset = to_cairo(current).utcoffset()
        if current_offset != previous_offset:
            return current
        previous_offset = current_offset
    return None


def test_cairo_dst_change_day():
    transition_utc = _find_cairo_dst_transition(2024)
    assert transition_utc is not None, "expected tzdata to contain a Cairo DST transition in 2024"

    before = transition_utc - timedelta(hours=12)
    after = transition_utc + timedelta(hours=12)

    # Default close time (>= noon) just mirrors the Cairo calendar date on both
    # sides of the transition -- it must not crash or silently misbehave.
    assert business_date(before) == to_cairo(before).date()
    assert business_date(after) == to_cairo(after).date()

    # The early-morning-shift branch must also survive the transition.
    close_time = time(3, 0)
    assert business_date(before, close_time) is not None
    assert business_date(after, close_time) is not None
