"""Data access for the settings key/value table.

Everything is stored as text (SQLite has no strict typing anyway); callers
convert to int/bool as needed. DEFAULTS is applied once at startup so the
rest of the app can always assume every key exists.
"""
from __future__ import annotations

import sqlite3
from typing import Dict, Optional

from derby.core.updates.version_logic import DEFAULT_UPDATE_MANIFEST_URL
from derby.core.utils.paths import default_backup_dir
from derby.core.utils.platform_info import default_whatsapp_method

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
    "update_manifest_url": DEFAULT_UPDATE_MANIFEST_URL,
    # Global login lockout state (Step 5): kept in settings, not per-user,
    # so a restart of the app does not reset an in-progress lockout.
    "login_failed_attempts": "0",
    "login_locked_until_utc": "",
    # Daily closing / backup (Phase 7).
    "closing_enabled": "1",
    "backup_keep_count": "30",
    # whatsapp_method is intentionally NOT a static value here either --
    # same reasoning as backup_folder_primary above: it must reflect
    # sys.getwindowsversion() at ensure_defaults() time (Windows 7 has no
    # WhatsApp Desktop), not whatever platform this module happened to be
    # first imported on.
    "whatsapp_method": "",
    "last_exit_backup_utc": "",
    "app_first_run_date": "",
}


_LAZY_DEFAULTS = {
    "backup_folder_primary": lambda: str(default_backup_dir()),
    "whatsapp_method": default_whatsapp_method,
}


def ensure_defaults(conn: sqlite3.Connection) -> None:
    for key, value in DEFAULTS.items():
        if key in _LAZY_DEFAULTS:
            continue  # resolved below, lazily -- see the comment on DEFAULTS
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO NOTHING",
            (key, value),
        )
    # True only the very first time ensure_defaults() ever completes for
    # this database (app_first_run_date is set right after, by
    # closing_service.ensure_first_run_date) -- used below so the
    # Windows-version-aware whatsapp_method default can override the
    # static "desktop" that migration 0006 already inserted directly
    # (migrations are append-only and never edited, so that row already
    # exists by the time we get here) WITHOUT ever clobbering a value the
    # owner deliberately changed on a later run.
    is_genuine_first_run = conn.execute(
        "SELECT 1 FROM settings WHERE key = 'app_first_run_date' AND value != ''"
    ).fetchone() is None

    # Resolved now (not baked into DEFAULTS above) so each reflects THIS
    # process/test's actual environment/platform, not whatever it was the
    # first time derby.core.db.settings_repo was imported.
    for key, resolve in _LAZY_DEFAULTS.items():
        if key == "whatsapp_method" and is_genuine_first_run:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, resolve()),
            )
            continue
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO NOTHING",
            (key, resolve()),
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
