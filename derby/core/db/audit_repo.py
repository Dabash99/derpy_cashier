"""Data access for the audit_log table (lockouts, update checks, etc.)."""
from __future__ import annotations

import sqlite3
from typing import Optional

from derby.core.utils.time_utils import to_utc_iso, utc_now


def log(conn: sqlite3.Connection, action: str, user_id: Optional[int] = None, details: str = "") -> None:
    conn.execute(
        "INSERT INTO audit_log (at_utc, user_id, action, details) VALUES (?, ?, ?, ?)",
        (to_utc_iso(utc_now()), user_id, action, details),
    )
    conn.commit()
