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


def _migration_0003_cashier(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_no INTEGER,
            table_id INTEGER,
            device_id INTEGER,  -- Phase 4: PlayStation device, unused for now
            status TEXT NOT NULL CHECK (status IN ('open', 'paid', 'cancelled', 'void')),
            opened_at_utc TEXT NOT NULL,
            opened_by INTEGER NOT NULL,
            paid_at_utc TEXT,
            paid_by INTEGER,
            business_date TEXT,
            subtotal_piasters INTEGER NOT NULL DEFAULT 0,
            discount_piasters INTEGER NOT NULL DEFAULT 0,
            discount_reason TEXT,
            discount_approved_by INTEGER,
            total_piasters INTEGER NOT NULL DEFAULT 0,
            payment_method TEXT CHECK (payment_method IN ('cash', 'instapay')),
            voided_at_utc TEXT,
            voided_by INTEGER,
            void_reason TEXT,
            note TEXT,
            FOREIGN KEY (table_id) REFERENCES tables (id),
            FOREIGN KEY (opened_by) REFERENCES users (id),
            FOREIGN KEY (paid_by) REFERENCES users (id),
            FOREIGN KEY (discount_approved_by) REFERENCES users (id),
            FOREIGN KEY (voided_by) REFERENCES users (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('product', 'ps_time')),
            product_id INTEGER,
            name_snapshot TEXT NOT NULL,
            unit_price_snapshot_piasters INTEGER NOT NULL,
            qty INTEGER NOT NULL CHECK (qty BETWEEN 1 AND 99),
            line_total_piasters INTEGER NOT NULL,
            note TEXT,
            created_at_utc TEXT NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders (id),
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS order_item_addons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_item_id INTEGER NOT NULL,
            addon_id INTEGER,
            name_snapshot TEXT NOT NULL,
            price_delta_snapshot_piasters INTEGER NOT NULL,
            FOREIGN KEY (order_item_id) REFERENCES order_items (id),
            FOREIGN KEY (addon_id) REFERENCES addons (id)
        )
        """
    )

    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders (status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_business_date ON orders (business_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_table_status ON orders (table_id, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items (order_id)")

    # Belt-and-braces at the DB level (the service layer also checks this
    # before inserting): only one OPEN order per table at a time.
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_one_open_per_table "
        "ON orders (table_id) WHERE status = 'open' AND table_id IS NOT NULL"
    )
    # Invoice numbers must never repeat once assigned.
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_invoice_no "
        "ON orders (invoice_no) WHERE invoice_no IS NOT NULL"
    )

    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('next_invoice_no', '1') "
        "ON CONFLICT(key) DO NOTHING"
    )

    for sort_order, name in enumerate(["ترابيزة 1", "ترابيزة 2", "ترابيزة 3"], start=1):
        conn.execute(
            "INSERT INTO tables (name, sort_order, is_active) VALUES (?, ?, 1)", (name, sort_order)
        )


def _migration_0004_playstation(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ps_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            single_rate_piasters_per_hour INTEGER NOT NULL DEFAULT 0,
            multi_rate_piasters_per_hour INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ps_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL,
            order_id INTEGER NOT NULL,
            mode TEXT NOT NULL CHECK (mode IN ('single', 'multi')),
            started_at_utc TEXT NOT NULL,
            stopped_at_utc TEXT,
            rate_snapshot_piasters_per_hour INTEGER NOT NULL,
            device_name_snapshot TEXT NOT NULL,
            actual_minutes INTEGER,
            billed_minutes INTEGER,
            price_piasters INTEGER,
            order_item_id INTEGER,
            is_final INTEGER NOT NULL DEFAULT 0,
            started_by INTEGER NOT NULL,
            stopped_by INTEGER,
            voided_at_utc TEXT,
            voided_by INTEGER,
            FOREIGN KEY (device_id) REFERENCES ps_devices (id),
            FOREIGN KEY (order_id) REFERENCES orders (id),
            FOREIGN KEY (order_item_id) REFERENCES order_items (id),
            FOREIGN KEY (started_by) REFERENCES users (id),
            FOREIGN KEY (stopped_by) REFERENCES users (id),
            FOREIGN KEY (voided_by) REFERENCES users (id)
        )
        """
    )
    conn.execute("ALTER TABLE order_items ADD COLUMN ps_session_id INTEGER")

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ps_sessions_device_stopped ON ps_sessions (device_id, stopped_at_utc)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ps_sessions_order_id ON ps_sessions (order_id)")
    # Only one running (stopped_at_utc IS NULL) session per device at a time.
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_ps_sessions_one_running_per_device "
        "ON ps_sessions (device_id) WHERE stopped_at_utc IS NULL"
    )
    # Only one open order per device at a time (mirrors idx_orders_one_open_per_table).
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_one_open_per_device "
        "ON orders (device_id) WHERE status = 'open' AND device_id IS NOT NULL"
    )

    # Defense in depth alongside the service-layer check: an order belongs to
    # a table, a device, or takeaway -- never both a table and a device.
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_orders_table_device_exclusive_insert
        BEFORE INSERT ON orders
        WHEN NEW.table_id IS NOT NULL AND NEW.device_id IS NOT NULL
        BEGIN
            SELECT RAISE(ABORT, 'order cannot have both table_id and device_id');
        END
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_orders_table_device_exclusive_update
        BEFORE UPDATE ON orders
        WHEN NEW.table_id IS NOT NULL AND NEW.device_id IS NOT NULL
        BEGIN
            SELECT RAISE(ABORT, 'order cannot have both table_id and device_id');
        END
        """
    )

    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('ps_long_session_hours', '6') "
        "ON CONFLICT(key) DO NOTHING"
    )

    for sort_order, name in enumerate(["بلاي ستيشن 1", "بلاي ستيشن 2"], start=1):
        conn.execute(
            "INSERT INTO ps_devices (name, single_rate_piasters_per_hour, multi_rate_piasters_per_hour, sort_order, is_active) "
            "VALUES (?, 0, 0, ?, 1)",
            (name, sort_order),
        )


MIGRATIONS: List[Callable[[sqlite3.Connection], None]] = [
    _migration_0001_initial,
    _migration_0002_menu,
    _migration_0003_cashier,
    _migration_0004_playstation,
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
