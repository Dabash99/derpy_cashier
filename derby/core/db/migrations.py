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


def _migration_0002_menu(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at_utc TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            name_ar TEXT NOT NULL,
            name_en TEXT,
            price_piasters INTEGER NOT NULL CHECK (price_piasters >= 0),
            image_file TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            sort_order INTEGER NOT NULL DEFAULT 0,
            needs_price_review INTEGER NOT NULL DEFAULT 0,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL,
            FOREIGN KEY (category_id) REFERENCES categories (id),
            UNIQUE (category_id, name_ar)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS addon_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            min_select INTEGER NOT NULL DEFAULT 0,
            max_select INTEGER,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS addons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            price_delta_piasters INTEGER NOT NULL CHECK (price_delta_piasters >= 0),
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (group_id) REFERENCES addon_groups (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS product_addon_groups (
            product_id INTEGER NOT NULL,
            group_id INTEGER NOT NULL,
            PRIMARY KEY (product_id, group_id),
            FOREIGN KEY (product_id) REFERENCES products (id),
            FOREIGN KEY (group_id) REFERENCES addon_groups (id)
        )
        """
    )


MIGRATIONS: List[Callable[[sqlite3.Connection], None]] = [
    _migration_0001_initial,
    _migration_0002_menu,
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
