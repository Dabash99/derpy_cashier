"""Data access for the settings key/value table.

Everything is stored as text (SQLite has no strict typing anyway); callers
convert to int/bool as needed. DEFAULTS is applied once at startup so the
rest of the app can always assume every key exists.
"""
from __future__ import annotations

import sqlite3
from typing import Dict, Optional

from derby.core.utils.paths import default_backup_dir

DEFAULTS: Dict[str, str] = {
    "cafe_name": "",
    "business_close_time": "23:59",
    "ps_min_minutes": "30",
    "rounding_step_egp": "5",
    "ps_long_session_hours": "6",
    "whatsapp_number": "",
    "backup_folder_primary": str(default_backup_dir()),
    "backup_folder_secondary": "",
    "auto_lock_minutes": "10",
    "update_manifest_url": "",
    # Global login lockout state (Step 5): kept in settings, not per-user,
    # so a restart of the app does not reset an in-progress lockout.
    "login_failed_attempts": "0",
    "login_locked_until_utc": "",
}


def ensure_defaults(conn: sqlite3.Connection) -> None:
    for key, value in DEFAULTS.items():
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO NOTHING",
            (key, value),
        )
    conn.commit()


def get(conn: sqlite3.Connection, key: str, default: Optional[str] = None) -> Optional[str]:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        return DEFAULTS.get(key, default)
    return row["value"]


def set_value(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def get_all(conn: sqlite3.Connection) -> Dict[str, str]:
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    result = dict(DEFAULTS)
    for row in rows:
        result[row["key"]] = row["value"]
    return result
