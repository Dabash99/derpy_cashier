"""UTC <-> Africa/Cairo conversions.

Everything is stored in the database as UTC; the UI only ever shows
Africa/Cairo local time. Using the IANA tz database (via zoneinfo) instead
of a fixed offset means Egypt's past DST rules are handled correctly for
historical timestamps, and future rule changes only need a tzdata update.
"""
from __future__ import annotations

from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python 3.8 has no stdlib zoneinfo.
    from backports.zoneinfo import ZoneInfo

CAIRO_TZ = ZoneInfo("Africa/Cairo")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_cairo(utc_dt: datetime) -> datetime:
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    return utc_dt.astimezone(CAIRO_TZ)


def to_utc_iso(utc_dt: datetime) -> str:
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    return utc_dt.astimezone(timezone.utc).isoformat()


def parse_utc_iso(text: str) -> datetime:
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
