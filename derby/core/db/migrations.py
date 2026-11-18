"""Ordered schema migrations, tracked via SQLite's built-in PRAGMA user_version.

Each entry in MIGRATIONS is a function for one schema version. Later
phases only ever append a new function to this list — past ones are never
edited, so a cafe's existing database always upgrades predictably no
matter which version it started from.
"""
from __future__ import annotations

import sqlite3
from typing import Callable, List


def _migration_0001_initial(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('owner', 'cashier')),
            pin_hash BLOB NOT NULL,
            pin_salt BLOB NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            failed_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until_utc TEXT,
            created_at_utc TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            at_utc TEXT NOT NULL,
            user_id INTEGER,
            action TEXT NOT NULL,
            details TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )


MIGRATIONS: List[Callable[[sqlite3.Connection], None]] = [
    _migration_0001_initial,
]


def run_pending_migrations(conn: sqlite3.Connection) -> None:
    current_version = conn.execute("PRAGMA user_version").fetchone()[0]
    for version, migrate in enumerate(MIGRATIONS, start=1):
        if version <= current_version:
            continue
        conn.execute("BEGIN")
        try:
            migrate(conn)
            conn.execute("PRAGMA user_version = {0}".format(version))
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()
