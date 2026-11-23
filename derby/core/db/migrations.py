"""Ordered schema migrations, tracked via SQLite's built-in PRAGMA user_version.

Each entry in MIGRATIONS is a function for one schema version. Later
phases only ever append a new function to this list — past ones are never
edited, so a cafe's existing database always upgrades predictably no
matter which version it started from.
"""
from __future__ import annotations

import sqlite3
from datetime import time as time_of_day
from typing import Callable, List

from derby.core.utils.business_date import business_date as _compute_business_date
from derby.core.utils.time_utils import parse_utc_iso as _parse_utc_iso


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


def _migration_0005_expenses(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS expense_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS recurring_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            amount_piasters INTEGER NOT NULL CHECK (amount_piasters > 0),
            day_of_month INTEGER NOT NULL CHECK (day_of_month BETWEEN 1 AND 31),
            is_active INTEGER NOT NULL DEFAULT 1,
            last_generated_month TEXT,
            created_at_utc TEXT NOT NULL,
            FOREIGN KEY (category_id) REFERENCES expense_categories (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            amount_piasters INTEGER NOT NULL CHECK (amount_piasters > 0),
            expense_date TEXT NOT NULL,
            description TEXT,
            receipt_file TEXT,
            recurring_id INTEGER,
            status TEXT NOT NULL CHECK (status IN ('active', 'void')),
            void_reason TEXT,
            voided_by INTEGER,
            voided_at_utc TEXT,
            replaced_by_id INTEGER,
            created_by INTEGER NOT NULL,
            created_at_utc TEXT NOT NULL,
            FOREIGN KEY (category_id) REFERENCES expense_categories (id),
            FOREIGN KEY (recurring_id) REFERENCES recurring_expenses (id),
            FOREIGN KEY (voided_by) REFERENCES users (id),
            FOREIGN KEY (replaced_by_id) REFERENCES expenses (id),
            FOREIGN KEY (created_by) REFERENCES users (id)
        )
        """
    )

    conn.execute("CREATE INDEX IF NOT EXISTS idx_expenses_date_status ON expenses (expense_date, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_business_date_status ON orders (business_date, status)")

    for sort_order, name in enumerate(["إيجار", "كهرباء", "مياه", "صيانة", "أدوات شغل", "أخرى"], start=1):
        conn.execute(
            "INSERT INTO expense_categories (name, sort_order, is_active) VALUES (?, ?, 1)", (name, sort_order)
        )


def _migration_0006_closing(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS day_closures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_date TEXT NOT NULL UNIQUE,
            revision INTEGER NOT NULL DEFAULT 1,
            built_at_utc TEXT NOT NULL,
            trigger TEXT NOT NULL CHECK (trigger IN ('auto', 'catchup', 'manual', 'exit')),
            report_text TEXT NOT NULL,
            invoice_count INTEGER NOT NULL DEFAULT 0,
            net_sales_piasters INTEGER NOT NULL DEFAULT 0,
            expenses_piasters INTEGER NOT NULL DEFAULT 0,
            profit_piasters INTEGER NOT NULL DEFAULT 0,
            open_orders_count INTEGER NOT NULL DEFAULT 0,
            running_sessions_count INTEGER NOT NULL DEFAULT 0,
            backup_file_name TEXT,
            backup_primary_status TEXT,
            backup_secondary_status TEXT CHECK (backup_secondary_status IN ('ok', 'failed', 'skipped', 'pending') OR backup_secondary_status IS NULL),
            backup_message TEXT,
            sent_at_utc TEXT,
            sent_by INTEGER,
            stale INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (sent_by) REFERENCES users (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS backup_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            at_utc TEXT NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('daily', 'manual', 'exit')),
            target TEXT NOT NULL CHECK (target IN ('primary', 'secondary')),
            path TEXT,
            size_bytes INTEGER,
            sha256 TEXT,
            verified INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            error TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_day_closures_business_date ON day_closures (business_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_backup_log_target_verified ON backup_log (target, verified, at_utc)")

    for key, value in (
        ("closing_enabled", "1"),
        ("backup_keep_count", "30"),
        ("whatsapp_method", "desktop"),
        ("last_exit_backup_utc", ""),
        ("app_first_run_date", ""),
    ):
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO NOTHING", (key, value))


def _migration_0007_supplies(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS supplies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            quantity_note TEXT,
            priority TEXT NOT NULL CHECK (priority IN ('عادي', 'مستعجل')),
            status TEXT NOT NULL CHECK (status IN ('needed', 'bought', 'dropped')),
            note TEXT,
            added_by INTEGER NOT NULL,
            added_at_utc TEXT NOT NULL,
            bought_by INTEGER,
            bought_at_utc TEXT,
            cost_piasters INTEGER,
            expense_id INTEGER,
            FOREIGN KEY (added_by) REFERENCES users (id),
            FOREIGN KEY (bought_by) REFERENCES users (id),
            FOREIGN KEY (expense_id) REFERENCES expenses (id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_supplies_status_priority ON supplies (status, priority)")


def _migration_0008_order_label(conn: sqlite3.Connection) -> None:
    # Optional short free-text label for a takeaway order (e.g. a
    # customer name/note) -- shown on its card, the cashier header, the
    # sales log, and the invoice. Never required, never touches
    # numbering/invoice rules.
    conn.execute("ALTER TABLE orders ADD COLUMN label TEXT")


def _migration_0009_inventory(conn: sqlite3.Connection) -> None:
    """Phase 9: optional per-product recipes/stock, purchases/suppliers,
    and the cash-drawer ledger. Every quantity (current_qty, min_qty,
    qty_per_unit, movement qty_delta) is a REAL -- these are grams/ml/
    pieces, not money, so the "money is always an integer" rule (see
    money.py) does not apply to them. Cost snapshots that ARE money
    (purchase totals, the per-line cost snapshot on a sold item, every
    drawer_entries amount) stay INTEGER piasters; only avg_cost_piasters
    and unit_cost_snapshot_piasters are REAL, since a cost per gram/ml is
    routinely a fraction of a piaster and rounding it at every purchase
    would make the weighted average drift.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS stock_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            unit TEXT NOT NULL CHECK (unit IN ('g', 'kg', 'ml', 'l', 'piece')),
            current_qty REAL NOT NULL DEFAULT 0,
            min_qty REAL NOT NULL DEFAULT 0,
            avg_cost_piasters REAL NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at_utc TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            notes TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at_utc TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER,
            purchase_date TEXT NOT NULL,
            total_cost_piasters INTEGER NOT NULL DEFAULT 0,
            is_paid INTEGER NOT NULL DEFAULT 0,
            expense_id INTEGER,
            note TEXT,
            created_by INTEGER NOT NULL,
            created_at_utc TEXT NOT NULL,
            FOREIGN KEY (supplier_id) REFERENCES suppliers (id),
            FOREIGN KEY (expense_id) REFERENCES expenses (id),
            FOREIGN KEY (created_by) REFERENCES users (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS purchase_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            purchase_id INTEGER NOT NULL,
            stock_item_id INTEGER NOT NULL,
            qty REAL NOT NULL CHECK (qty > 0),
            unit_cost_piasters REAL NOT NULL,
            total_cost_piasters INTEGER NOT NULL,
            FOREIGN KEY (purchase_id) REFERENCES purchases (id),
            FOREIGN KEY (stock_item_id) REFERENCES stock_items (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS recipe_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_type TEXT NOT NULL CHECK (owner_type IN ('product', 'addon')),
            owner_id INTEGER NOT NULL,
            stock_item_id INTEGER NOT NULL,
            qty_per_unit REAL NOT NULL CHECK (qty_per_unit > 0),
            UNIQUE (owner_type, owner_id, stock_item_id),
            FOREIGN KEY (stock_item_id) REFERENCES stock_items (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS stock_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_item_id INTEGER NOT NULL,
            movement_type TEXT NOT NULL CHECK (movement_type IN ('purchase', 'sale', 'waste', 'adjustment', 'return')),
            qty_delta REAL NOT NULL,
            unit_cost_snapshot_piasters REAL NOT NULL DEFAULT 0,
            ref_type TEXT,
            ref_id INTEGER,
            user_id INTEGER,
            note TEXT,
            created_at_utc TEXT NOT NULL,
            FOREIGN KEY (stock_item_id) REFERENCES stock_items (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS drawer_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_type TEXT NOT NULL CHECK (
                entry_type IN ('opening', 'sale_cash', 'expense', 'purchase', 'deposit', 'withdrawal', 'refund', 'count_adjustment')
            ),
            amount_delta_piasters INTEGER NOT NULL,
            ref_type TEXT,
            ref_id INTEGER,
            user_id INTEGER,
            note TEXT,
            is_historical INTEGER NOT NULL DEFAULT 0,
            created_at_utc TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS drawer_counts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            expected_piasters INTEGER NOT NULL,
            counted_piasters INTEGER NOT NULL,
            difference_piasters INTEGER NOT NULL,
            denominations_json TEXT,
            user_id INTEGER NOT NULL,
            created_at_utc TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )

    # Optional per-line cost snapshot (sum over its recipe, times qty, at
    # the moment it was sold) -- NULL for a line with no recipe, so past
    # profit never changes if a recipe or stock cost changes later.
    conn.execute("ALTER TABLE order_items ADD COLUMN cost_at_sale_piasters INTEGER")
    # Optional owner-set hourly electricity/wear cost for a PS device,
    # separate from its billed rate -- 0 (no cost) unless the owner sets it.
    conn.execute("ALTER TABLE ps_devices ADD COLUMN hourly_cost_piasters INTEGER NOT NULL DEFAULT 0")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_stock_movements_item_date ON stock_movements (stock_item_id, created_at_utc)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_stock_movements_ref ON stock_movements (ref_type, ref_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_recipe_lines_owner ON recipe_lines (owner_type, owner_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_purchase_lines_purchase ON purchase_lines (purchase_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_purchases_paid ON purchases (is_paid)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_drawer_entries_created_at ON drawer_entries (created_at_utc)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_drawer_counts_created_at ON drawer_counts (created_at_utc)")

    # "Supplies / مشتريات" expense category -- a paid purchase's auto-
    # created expense is filed here, so profit reports can exclude it from
    # operating expenses without a separate flag (see report_service).
    conn.execute(
        "INSERT INTO expense_categories (name, sort_order, is_active) "
        "SELECT 'مشتريات', (SELECT COALESCE(MAX(sort_order), 0) + 1 FROM expense_categories), 1 "
        "WHERE NOT EXISTS (SELECT 1 FROM expense_categories WHERE name = 'مشتريات')"
    )

    # Backfill: every existing cash sale and active expense becomes a
    # drawer_entries row, so the ledger/goods-review totals read correctly
    # for a cafe upgrading from an earlier phase. These are marked
    # is_historical=1 -- they feed reporting (e.g. a lifetime ledger view)
    # but must NEVER feed the *live* expected-cash balance, which only
    # ever starts from the most recent real 'opening' entry (see
    # drawer_service.expected_cash_piasters). InstaPay sales are never
    # cash -- excluded, per the drawer's own rule (see docs/SPEC.md).
    for order in conn.execute(
        "SELECT id, total_piasters, paid_by, paid_at_utc FROM orders WHERE status = 'paid' AND payment_method = 'cash'"
    ).fetchall():
        conn.execute(
            "INSERT INTO drawer_entries (entry_type, amount_delta_piasters, ref_type, ref_id, user_id, note, is_historical, created_at_utc) "
            "VALUES ('sale_cash', ?, 'order', ?, ?, NULL, 1, ?)",
            (order[1], order[0], order[2], order[3]),
        )
    for expense in conn.execute(
        "SELECT id, amount_piasters, created_by, created_at_utc FROM expenses WHERE status = 'active'"
    ).fetchall():
        conn.execute(
            "INSERT INTO drawer_entries (entry_type, amount_delta_piasters, ref_type, ref_id, user_id, note, is_historical, created_at_utc) "
            "VALUES ('expense', ?, 'expense', ?, ?, NULL, 1, ?)",
            (-expense[1], expense[0], expense[2], expense[3]),
        )


def _migration_0010_stock_movement_business_date(conn: sqlite3.Connection) -> None:
    """stock_movements had no business_date column (migration 0009) --
    the waste-cost query (and any future stock-movement-by-date query)
    was summing over plain UTC calendar dates, which can land a
    late-night movement on the wrong side of the cafe's actual business
    day (see docs/FIX_TZ_CACHE_REPORT.md). This adds the column and
    backfills it with the SAME business_date() + business_close_time
    rule orders/expenses already use -- never a second, invented rule.
    From here on, stock_movements_repo.create_movement always receives
    business_date as a required argument, computed by the caller
    (stock_service) the same way orders_service/expenses_service do.
    """
    conn.execute("ALTER TABLE stock_movements ADD COLUMN business_date TEXT")

    close_time_text = conn.execute("SELECT value FROM settings WHERE key = 'business_close_time'").fetchone()
    close_time_value = close_time_text["value"] if close_time_text is not None else "23:59"
    hour_str, minute_str = (close_time_value or "23:59").split(":")
    close_time = time_of_day(int(hour_str), int(minute_str))

    for row in conn.execute("SELECT id, created_at_utc FROM stock_movements WHERE business_date IS NULL").fetchall():
        business_date_value = _compute_business_date(_parse_utc_iso(row["created_at_utc"]), close_time).isoformat()
        conn.execute("UPDATE stock_movements SET business_date = ? WHERE id = ?", (business_date_value, row["id"]))

    conn.execute("CREATE INDEX IF NOT EXISTS idx_stock_movements_business_date ON stock_movements (business_date)")


def _migration_0011_drawer_entries_is_historical_repair(conn: sqlite3.Connection) -> None:
    """Repairs a real-world schema drift: `drawer_entries.is_historical`
    was added by editing migration 0009's body in place, during the
    same development session that first wrote it -- a violation of
    "never edit a past migration" that went unnoticed because no
    committed release had shipped yet. By the time it was caught, this
    project's own dev machine had already run the ORIGINAL (column-less)
    migration 0009 once for real, via run.bat, which set
    PRAGMA user_version to 9 -- so that database's drawer_entries table
    permanently lacks the column, and every later attempt to read or
    write a drawer_entries row (the dashboard's cash-in-drawer tile, any
    cash sale, expense, purchase, deposit, or drawer open/count) raises
    "no such column: is_historical" and crashes right after login (see
    docs/FIX_TZ_CACHE_REPORT.md).

    This migration is defensive rather than assuming that drift: it only
    adds the column if `PRAGMA table_info` shows it is actually missing
    (a database created from the CURRENT migrations.py already has it
    from migration 0009 itself, so this is then a complete no-op). When
    it does add the column, every existing row is marked historical --
    safe because, with the column missing, no row could have been
    written by any live drawer_repo.create_entry() call either (that
    INSERT always names is_historical), so every row already in the
    table at this point can only have come from migration 0009's own
    one-time backfill of pre-existing cash sales/expenses.
    """
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(drawer_entries)").fetchall()}
    if "is_historical" in columns:
        return
    conn.execute("ALTER TABLE drawer_entries ADD COLUMN is_historical INTEGER NOT NULL DEFAULT 0")
    conn.execute("UPDATE drawer_entries SET is_historical = 1")


def _migration_0012_audit_log_v2(conn: sqlite3.Connection) -> None:
    """Phase 11 Part A: audit_log (created bare in migration 0001, used
    ever since via audit_repo.log for a handful of events) grows the
    columns a real "سجل العمليات" screen needs -- business_date, a
    snapshot of the acting user's name (so a later deactivation/rename
    never changes how an old entry reads), entity linking, a short
    Arabic summary, a structured before/after details_json blob, and a
    severity flag -- plus the indexes a filtered, paged screen needs and
    the two triggers that make it genuinely append-only at the DB level
    (belt-and-braces alongside every repo/service only ever INSERTing
    into it). Existing rows are backfilled with a best-effort
    business_date (same business_date() + business_close_time rule every
    other backfill in this file uses) and a user_name snapshot from the
    users table as it stands today; they get severity='info' (already
    the column default) and NULL entity/summary/details_json, which the
    screen must render gracefully -- never a crash on an old row.
    """
    conn.execute("ALTER TABLE audit_log ADD COLUMN business_date TEXT")
    conn.execute("ALTER TABLE audit_log ADD COLUMN user_name TEXT")
    conn.execute("ALTER TABLE audit_log ADD COLUMN entity_type TEXT")
    conn.execute("ALTER TABLE audit_log ADD COLUMN entity_id INTEGER")
    conn.execute("ALTER TABLE audit_log ADD COLUMN summary_ar TEXT")
    conn.execute("ALTER TABLE audit_log ADD COLUMN details_json TEXT")
    conn.execute("ALTER TABLE audit_log ADD COLUMN severity TEXT NOT NULL DEFAULT 'info'")

    close_time_row = conn.execute("SELECT value FROM settings WHERE key = 'business_close_time'").fetchone()
    close_time_value = close_time_row["value"] if close_time_row is not None else "23:59"
    hour_str, minute_str = (close_time_value or "23:59").split(":")
    close_time = time_of_day(int(hour_str), int(minute_str))

    for row in conn.execute("SELECT id, at_utc, user_id FROM audit_log WHERE business_date IS NULL").fetchall():
        business_date_value = _compute_business_date(_parse_utc_iso(row["at_utc"]), close_time).isoformat()
        user_name = None
        if row["user_id"] is not None:
            user_row = conn.execute("SELECT name FROM users WHERE id = ?", (row["user_id"],)).fetchone()
            user_name = user_row["name"] if user_row is not None else None
        conn.execute(
            "UPDATE audit_log SET business_date = ?, user_name = ? WHERE id = ?",
            (business_date_value, user_name, row["id"]),
        )

    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log (at_utc)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_business_date ON audit_log (business_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log (user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log (action)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_entity ON audit_log (entity_type, entity_id)")

    # Append-only enforcement at the DB level -- no UPDATE or DELETE is
    # ever a legitimate operation on this table, from any code path,
    # forever (see docs for Phase 11 Part A). A correction is always a
    # new row; nothing in this codebase should ever need to catch these.
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_audit_log_no_update
        BEFORE UPDATE ON audit_log
        BEGIN
            SELECT RAISE(ABORT, 'audit_log is append-only: UPDATE is not permitted');
        END
        """
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_audit_log_no_delete
        BEFORE DELETE ON audit_log
        BEGIN
            SELECT RAISE(ABORT, 'audit_log is append-only: DELETE is not permitted');
        END
        """
    )


def _migration_0013_backups_v2(conn: sqlite3.Connection) -> None:
    """Phase 11 Part B: backup_log already stored sha256/verified/size
    per attempt (migration 0006) -- this adds the two columns a
    "Backups" screen needs to show app/schema version per backup, plus
    the settings a configurable retention/warning/auto-schedule policy
    needs. backup_folder_secondary (migration 0006/settings_repo) is
    reused as-is for "النسخة الخارجية" -- no new folder setting needed,
    only the policy around it.
    """
    conn.execute("ALTER TABLE backup_log ADD COLUMN app_version TEXT")
    conn.execute("ALTER TABLE backup_log ADD COLUMN schema_version INTEGER")

    for key, value in (
        ("backup_monthly_keep_count", "12"),
        ("backup_warning_days", "2"),
        ("backup_auto_hours", "0"),  # 0 = disabled; an owner-set N runs an extra backup every N hours
        ("backup_on_exit_enabled", "1"),
    ):
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO NOTHING", (key, value))


def _migration_0014_shifts_employees_payroll(conn: sqlite3.Connection) -> None:
    """Phase 11 Part C: shifts (tied to the existing drawer open/count),
    employees, attendance (clock in/out), and payroll (advances,
    deductions, bonuses, payments). `shift_id` is added as a NEW
    NULLABLE column on the existing `orders` and `drawer_entries` tables
    -- no CHECK constraint on either blocks a nullable integer column,
    so this is a plain additive link, never a rebuild. A payroll
    payment reuses the existing expenses mechanism (a new "مرتبات"
    category) rather than inventing a second expense concept.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            business_date TEXT NOT NULL,
            opened_at_utc TEXT NOT NULL,
            closed_at_utc TEXT,
            opening_cash_piasters INTEGER NOT NULL DEFAULT 0,
            counted_cash_piasters INTEGER,
            expected_cash_piasters INTEGER,
            difference_piasters INTEGER,
            notes TEXT,
            status TEXT NOT NULL CHECK (status IN ('open', 'closed')),
            handed_over_to_user_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (handed_over_to_user_id) REFERENCES users (id)
        )
        """
    )
    conn.execute("ALTER TABLE orders ADD COLUMN shift_id INTEGER")
    conn.execute("ALTER TABLE drawer_entries ADD COLUMN shift_id INTEGER")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            job_title TEXT,
            pay_type TEXT NOT NULL CHECK (pay_type IN ('daily', 'monthly')),
            base_amount_piasters INTEGER NOT NULL CHECK (base_amount_piasters >= 0),
            is_active INTEGER NOT NULL DEFAULT 1,
            linked_user_id INTEGER,
            created_at_utc TEXT NOT NULL,
            FOREIGN KEY (linked_user_id) REFERENCES users (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            business_date TEXT NOT NULL,
            clock_in_utc TEXT,
            clock_out_utc TEXT,
            note TEXT,
            corrected_by INTEGER,
            correction_reason TEXT,
            created_at_utc TEXT NOT NULL,
            FOREIGN KEY (employee_id) REFERENCES employees (id),
            FOREIGN KEY (corrected_by) REFERENCES users (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS payroll_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('advance', 'deduction', 'bonus')),
            amount_piasters INTEGER NOT NULL CHECK (amount_piasters > 0),
            line_date TEXT NOT NULL,
            note TEXT,
            applied_in_payment_id INTEGER,
            created_by INTEGER NOT NULL,
            created_at_utc TEXT NOT NULL,
            FOREIGN KEY (employee_id) REFERENCES employees (id),
            FOREIGN KEY (created_by) REFERENCES users (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS payroll_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            year_month TEXT NOT NULL,
            base_piasters INTEGER NOT NULL DEFAULT 0,
            bonuses_piasters INTEGER NOT NULL DEFAULT 0,
            advances_piasters INTEGER NOT NULL DEFAULT 0,
            deductions_piasters INTEGER NOT NULL DEFAULT 0,
            net_piasters INTEGER NOT NULL DEFAULT 0,
            payment_method TEXT NOT NULL CHECK (payment_method IN ('cash', 'instapay')),
            expense_id INTEGER,
            created_by INTEGER NOT NULL,
            created_at_utc TEXT NOT NULL,
            FOREIGN KEY (employee_id) REFERENCES employees (id),
            FOREIGN KEY (expense_id) REFERENCES expenses (id),
            FOREIGN KEY (created_by) REFERENCES users (id)
        )
        """
    )

    conn.execute("CREATE INDEX IF NOT EXISTS idx_shifts_user_status ON shifts (user_id, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_shifts_business_date ON shifts (business_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_shift_id ON orders (shift_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_drawer_entries_shift_id ON drawer_entries (shift_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_attendance_employee_date ON attendance (employee_id, business_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_payroll_lines_employee ON payroll_lines (employee_id, applied_in_payment_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_payroll_payments_employee_month ON payroll_payments (employee_id, year_month)")

    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('require_open_shift', '0') ON CONFLICT(key) DO NOTHING"
    )

    # "مرتبات" (payroll) expense category -- a payroll payment's auto-
    # created expense is filed here, same pattern as "مشتريات" (migration
    # 0009) for purchases.
    conn.execute(
        "INSERT INTO expense_categories (name, sort_order, is_active) "
        "SELECT 'مرتبات', (SELECT COALESCE(MAX(sort_order), 0) + 1 FROM expense_categories), 1 "
        "WHERE NOT EXISTS (SELECT 1 FROM expense_categories WHERE name = 'مرتبات')"
    )


def _migration_0015_customers_credit(conn: sqlite3.Connection) -> None:
    """Phase 11 Part D: customers and آجل (credit) sales. orders.
    payment_method stays CHECK-constrained to ('cash', 'instapay') --
    rather than widen that constraint (and risk every other place that
    already matches on it), a credit sale is a PAID order with
    payment_method left NULL and a NEW nullable customer_id column set
    -- customer_id IS NOT NULL is what "this was sold on آجل" means
    everywhere a service/report needs to tell the three apart. customer_
    ledger is its own append-only-by-convention table (never UPDATEd or
    DELETEd by any code path; a correction is always a new 'reversal'
    row), mirroring drawer_entries' own ledger discipline.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            notes TEXT,
            credit_limit_piasters INTEGER,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at_utc TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS customer_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            business_date TEXT NOT NULL,
            entry_type TEXT NOT NULL CHECK (entry_type IN ('charge', 'payment', 'adjustment', 'reversal')),
            amount_piasters INTEGER NOT NULL,
            order_id INTEGER,
            payment_method TEXT CHECK (payment_method IN ('cash', 'instapay') OR payment_method IS NULL),
            user_id INTEGER,
            note TEXT,
            created_at_utc TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers (id),
            FOREIGN KEY (order_id) REFERENCES orders (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    conn.execute("ALTER TABLE orders ADD COLUMN customer_id INTEGER")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_customers_active_name ON customers (is_active, name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_customer_ledger_customer ON customer_ledger (customer_id, created_at_utc)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_customer_ledger_business_date ON customer_ledger (business_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders (customer_id)")

    for key, value in (
        ("cashiers_may_sell_on_credit", "1"),
        ("default_customer_credit_limit_piasters", "0"),  # 0 = no limit
        ("customer_overdue_days", "14"),
    ):
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO NOTHING", (key, value))

    # A new drawer_entries entry type ('customer_payment_cash') would need
    # widening drawer_entries.entry_type's CHECK, which SQLite cannot do
    # via ALTER TABLE -- instead, a cash customer-payment gets its own
    # parallel ledger table, UNIONed into the drawer's expected-cash math
    # by drawer_service/drawer_repo rather than touching drawer_entries.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS extra_drawer_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_type TEXT NOT NULL CHECK (entry_type IN ('customer_payment_cash')),
            amount_delta_piasters INTEGER NOT NULL,
            ref_type TEXT,
            ref_id INTEGER,
            shift_id INTEGER,
            user_id INTEGER,
            note TEXT,
            created_at_utc TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_extra_drawer_entries_created_at ON extra_drawer_entries (created_at_utc)")


def _migration_0016_extras(conn: sqlite3.Connection) -> None:
    """Phase 11 Part E: named discount presets, the الرئيسية alerts
    center's per-type toggles and thresholds, and the reorder list's
    configurable target stock level.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS discount_presets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('percent', 'fixed')),
            amount INTEGER NOT NULL CHECK (amount > 0),
            is_active INTEGER NOT NULL DEFAULT 1,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at_utc TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_discount_presets_active ON discount_presets (is_active, sort_order)")

    # Optional owner-set target stock level per item, used by the
    # reorder list to suggest a purchase quantity (target - current, if
    # positive) -- defaults to min_qty * 2 at read time when unset
    # (see supplies/reorder_service.py), so this column is nullable.
    conn.execute("ALTER TABLE stock_items ADD COLUMN target_qty REAL")

    for key, value in (
        ("discount_free_form_pin_threshold_percent", "20"),
        ("ps_long_session_alert_hours", "6"),
        ("supplier_invoice_overdue_days", "14"),
        ("alert_ps_long_session_enabled", "1"),
        ("alert_customer_overdue_enabled", "1"),
        ("alert_backup_overdue_enabled", "1"),
        ("alert_low_stock_enabled", "1"),
        ("alert_drawer_not_opened_enabled", "1"),
        ("alert_shift_left_open_enabled", "1"),
        ("alert_unpaid_supplier_invoices_enabled", "1"),
    ):
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO NOTHING", (key, value))


MIGRATIONS: List[Callable[[sqlite3.Connection], None]] = [
    _migration_0001_initial,
    _migration_0002_menu,
    _migration_0003_cashier,
    _migration_0004_playstation,
    _migration_0005_expenses,
    _migration_0006_closing,
    _migration_0007_supplies,
    _migration_0008_order_label,
    _migration_0009_inventory,
    _migration_0010_stock_movement_business_date,
    _migration_0011_drawer_entries_is_historical_repair,
    _migration_0012_audit_log_v2,
    _migration_0013_backups_v2,
    _migration_0014_shifts_employees_payroll,
    _migration_0015_customers_credit,
    _migration_0016_extras,
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
