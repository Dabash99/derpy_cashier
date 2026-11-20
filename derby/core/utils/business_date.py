"""The cafe's "business date" rule.

A late-closing cafe's day doesn't end at midnight: if it closes at 3 AM,
an order placed at 1:30 AM still belongs to *yesterday's* business day.
`settings.business_close_time` (default 23:59) controls where that line
falls.

Rule (close_time is a local Africa/Cairo wall-clock time):
  - close_time >= 12:00 (noon): the cafe closes in the evening, so the
    business date is simply the Cairo calendar date (no shift).
  - close_time < 12:00 (e.g. 03:00): the cafe closes in the early morning,
    so times up to and including close_time still belong to the previous
    calendar day. We shift the clock back by (close_time + 1 minute)
    before reading the calendar date, so 03:00 and everything before it
    falls into the previous day, and 03:01 onward starts the new one.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from derby.core.utils.time_utils import to_cairo

DEFAULT_CLOSE_TIME = time(23, 59)
_NOON = time(12, 0)


def business_date(utc_dt: datetime, close_time: time = DEFAULT_CLOSE_TIME) -> date:
    cairo_dt = to_cairo(utc_dt)
    if close_time >= _NOON:
        return cairo_dt.date()
    offset = timedelta(hours=close_time.hour, minutes=close_time.minute + 1)
    shifted = cairo_dt - offset
    return shifted.date()
