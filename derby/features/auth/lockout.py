"""Global login lockout: 5 wrong PINs in a row locks the login screen for
5 minutes. Stored in `settings` (not memory) so restarting the app does
not reset it, per the approved spec.

`now` is always an explicit parameter (defaulting to the real clock) so
tests can inject a fake clock instead of sleeping or mocking datetime.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from derby.core.db import audit_repo, settings_repo
from derby.core.utils.time_utils import parse_utc_iso, to_utc_iso, utc_now

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 5


def record_failed_attempt(conn: sqlite3.Connection, now: Optional[datetime] = None) -> int:
    now = now if now is not None else utc_now()
    attempts = int(settings_repo.get(conn, "login_failed_attempts", "0")) + 1
    settings_repo.set_value(conn, "login_failed_attempts", str(attempts))
    if attempts >= MAX_FAILED_ATTEMPTS:
        locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
        settings_repo.set_value(conn, "login_locked_until_utc", to_utc_iso(locked_until))
        audit_repo.log(conn, "login_lockout", details="{0} failed attempts".format(attempts))
    return attempts


def reset_failed_attempts(conn: sqlite3.Connection) -> None:
    settings_repo.set_value(conn, "login_failed_attempts", "0")
    settings_repo.set_value(conn, "login_locked_until_utc", "")


def get_lock_remaining(conn: sqlite3.Connection, now: Optional[datetime] = None) -> Optional[timedelta]:
    now = now if now is not None else utc_now()
    locked_until_text = settings_repo.get(conn, "login_locked_until_utc", "") or ""
    if not locked_until_text:
        return None
    locked_until = parse_utc_iso(locked_until_text)
    remaining = locked_until - now
    if remaining.total_seconds() <= 0:
        return None
    return remaining


def is_locked(conn: sqlite3.Connection, now: Optional[datetime] = None) -> bool:
    return get_lock_remaining(conn, now) is not None
