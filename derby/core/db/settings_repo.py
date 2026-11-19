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
    # backup_folder_primary is intentionally NOT a static value here: it
    # must be resolved by calling default_backup_dir() at ensure_defaults()
    # time (see below), not baked in once when this module is first
    # imported -- a module-level call would freeze whatever %USERPROFILE%
    # happened to be for the rest of the process, which breaks both
    # production (the user's profile can't change mid-run anyway, but it's
    # still the wrong layer for it) and, much more importantly, test
    # isolation: monkeypatching default_backup_dir per test would have no
    # effect on an already-computed module-level constant.
    "backup_folder_primary": "",
    "backup_folder_secondary": "",
    "auto_lock_minutes": "10",
    "update_manifest_url": "",
    # Global login lockout state (Step 5): kept in settings, not per-user,
    # so a restart of the app does not reset an in-progress lockout.
    "login_failed_attempts": "0",
    "login_locked_until_utc": "",
    # Daily closing / backup (Phase 7).
    "closing_enabled": "1",
    "backup_keep_count": "30",
    "whatsapp_method": "desktop",
    "last_exit_backup_utc": "",
    "app_first_run_date": "",
}


def ensure_defaults(conn: sqlite3.Connection) -> None:
    for key, value in DEFAULTS.items():
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO NOTHING",
            (key, value),
        )
    # Resolved now (not baked into DEFAULTS above) so it reflects whatever
    # default_backup_dir() returns in THIS process/test, not whatever it
    # returned the first time derby.core.db.settings_repo was imported.
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('backup_folder_primary', ?) ON CONFLICT(key) DO NOTHING",
        (str(default_backup_dir()),),
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
