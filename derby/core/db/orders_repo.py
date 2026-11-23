"""Data access for orders, order_items, and order_item_addons.

Pure CRUD/queries only -- the state machine, discount/approval rules,
totals math, and audit logging live in derby/features/pos/orders_service.py.
Write functions take `commit=False` so the service layer can compose
several of them inside one transaction (e.g. "pay" touches orders AND
increments the invoice counter atomically).
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from derby.core.utils.time_utils import to_utc_iso, utc_now

# --- orders ------------------------------------------------------------


def create_order(
    conn: sqlite3.Connection,
    table_id: Optional[int],
    opened_by: int,
    device_id: Optional[int] = None,
    label: Optional[str] = None,
    commit: bool = True,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO orders (table_id, device_id, status, opened_at_utc, opened_by, subtotal_piasters, discount_piasters, total_piasters, label)
        VALUES (?, ?, 'open', ?, ?, 0, 0, 0, ?)
        """,
        (table_id, device_id, to_utc_iso(utc_now()), opened_by, label),
    )
    if commit:
        conn.commit()
    return cursor.lastrowid


def set_label(conn: sqlite3.Connection, order_id: int, label: Optional[str], commit: bool = True) -> None:
    conn.execute("UPDATE orders SET label = ? WHERE id = ?", (label, order_id))
    if commit:
        conn.commit()


def get_order(conn: sqlite3.Connection, order_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()


def get_open_order_for_table(conn: sqlite3.Connection, table_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM orders WHERE table_id = ? AND status = 'open'", (table_id,)
    ).fetchone()


def get_open_order_for_device(conn: sqlite3.Connection, device_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM orders WHERE device_id = ? AND status = 'open'", (device_id,)
    ).fetchone()


def list_open_takeaway_orders(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    # table_id IS NULL also matches PlayStation device orders -- exclude
    # those explicitly, or a running device's order shows up twice (once
    # correctly on its PS card, once mislabeled as a takeaway row here).
    return conn.execute(
        "SELECT * FROM orders WHERE table_id IS NULL AND device_id IS NULL AND status = 'open' ORDER BY opened_at_utc"
    ).fetchall()


def list_open_orders(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    return conn.execute("SELECT * FROM orders WHERE status = 'open'").fetchall()


def list_open_orders_with_summary(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    """Every open order (table, PlayStation device, or takeaway) plus the
    table/device/opener names and item count, in one query -- used by the
    Home screen's "الطلبات المفتوحة" section so it never issues a
    per-card follow-up query."""
    return conn.execute(
        """
        SELECT
            o.*,
            t.name AS table_name,
            d.name AS device_name,
            u.name AS opened_by_name,
            (SELECT COUNT(*) FROM order_items oi WHERE oi.order_id = o.id) AS item_count
        FROM orders o
        LEFT JOIN tables t ON t.id = o.table_id
        LEFT JOIN ps_devices d ON d.id = o.device_id
        LEFT JOIN users u ON u.id = o.opened_by
        WHERE o.status = 'open'
        ORDER BY o.opened_at_utc
        """
    ).fetchall()


def list_orders(
    conn: sqlite3.Connection,
    business_date: Optional[str] = None,
    status: Optional[str] = None,
) -> List[sqlite3.Row]:
    clauses = []
    params: list = []
    if business_date is not None:
        clauses.append("business_date = ?")
        params.append(business_date)
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return conn.execute(
        "SELECT * FROM orders" + where + " ORDER BY paid_at_utc, opened_at_utc", tuple(params)
    ).fetchall()


def list_paid_between(conn: sqlite3.Connection, start_utc: str, end_utc: str) -> List[sqlite3.Row]:
    """Every order paid within [start_utc, end_utc] -- used by
    shift_service.build_shift_report, which reports by real wall-clock
    shift window rather than by business_date (a shift can start or end
    mid-business-day)."""
    return conn.execute(
        "SELECT * FROM orders WHERE status = 'paid' AND paid_at_utc >= ? AND paid_at_utc <= ? ORDER BY paid_at_utc",
        (start_utc, end_utc),
    ).fetchall()


def list_voided_between(conn: sqlite3.Connection, start_utc: str, end_utc: str) -> List[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM orders WHERE status = 'void' AND voided_at_utc >= ? AND voided_at_utc <= ? ORDER BY voided_at_utc",
        (start_utc, end_utc),
    ).fetchall()


def set_shift_id(conn: sqlite3.Connection, order_id: int, shift_id: Optional[int], commit: bool = True) -> None:
    conn.execute("UPDATE orders SET shift_id = ? WHERE id = ?", (shift_id, order_id))
    if commit:
        conn.commit()


def update_order_totals(
    conn: sqlite3.Connection, order_id: int, subtotal_piasters: int, discount_piasters: int, total_piasters: int, commit: bool = True
) -> None:
    conn.execute(
        "UPDATE orders SET subtotal_piasters = ?, discount_piasters = ?, total_piasters = ? WHERE id = ?",
        (subtotal_piasters, discount_piasters, total_piasters, order_id),
    )
    if commit:
        conn.commit()


def set_order_discount(
    conn: sqlite3.Connection, order_id: int, discount_piasters: int, reason: str, approved_by: Optional[int], commit: bool = True
) -> None:
    conn.execute(
        "UPDATE orders SET discount_piasters = ?, discount_reason = ?, discount_approved_by = ? WHERE id = ?",
        (discount_piasters, reason, approved_by, order_id),
    )
    if commit:
        conn.commit()


def clear_order_discount(conn: sqlite3.Connection, order_id: int, commit: bool = True) -> None:
    conn.execute(
        "UPDATE orders SET discount_piasters = 0, discount_reason = NULL, discount_approved_by = NULL WHERE id = ?",
        (order_id,),
    )
    if commit:
        conn.commit()


def mark_order_paid(
    conn: sqlite3.Connection,
    order_id: int,
    invoice_no: int,
    paid_by: int,
    business_date: str,
    payment_method: str,
    commit: bool = True,
) -> None:
    conn.execute(
        """
        UPDATE orders
        SET status = 'paid', invoice_no = ?, paid_by = ?, paid_at_utc = ?, business_date = ?, payment_method = ?
        WHERE id = ?
        """,
        (invoice_no, paid_by, to_utc_iso(utc_now()), business_date, payment_method, order_id),
    )
    if commit:
        conn.commit()


def mark_order_paid_on_credit(
    conn: sqlite3.Connection,
    order_id: int,
    invoice_no: int,
    paid_by: int,
    business_date: str,
    customer_id: int,
    commit: bool = True,
) -> None:
    """A آجل (credit) sale: payment_method stays NULL (the column's CHECK
    only allows 'cash'/'instapay'/NULL -- never widened, see migration
    0015's docstring) and customer_id is set instead. customer_id IS NOT
    NULL is what "this was sold on credit" means everywhere else."""
    conn.execute(
        """
        UPDATE orders
        SET status = 'paid', invoice_no = ?, paid_by = ?, paid_at_utc = ?, business_date = ?,
            payment_method = NULL, customer_id = ?
        WHERE id = ?
        """,
        (invoice_no, paid_by, to_utc_iso(utc_now()), business_date, customer_id, order_id),
    )
    if commit:
        conn.commit()


def mark_order_cancelled(conn: sqlite3.Connection, order_id: int, commit: bool = True) -> None:
    conn.execute("UPDATE orders SET status = 'cancelled' WHERE id = ?", (order_id,))
    if commit:
        conn.commit()


def mark_order_void(
    conn: sqlite3.Connection, order_id: int, voided_by: int, void_reason: str, commit: bool = True
) -> None:
    conn.execute(
        "UPDATE orders SET status = 'void', voided_by = ?, voided_at_utc = ?, void_reason = ? WHERE id = ?",
        (voided_by, to_utc_iso(utc_now()), void_reason, order_id),
    )
    if commit:
        conn.commit()


def set_order_location(
    conn: sqlite3.Connection,
    order_id: int,
    table_id: Optional[int] = None,
    device_id: Optional[int] = None,
    commit: bool = True,
) -> None:
    """Moves an order to a table or a device, always clearing the other
    column -- an order never belongs to both (see the Phase 4 migration's
    exclusivity trigger)."""
    conn.execute(
        "UPDATE orders SET table_id = ?, device_id = ? WHERE id = ?", (table_id, device_id, order_id)
    )
    if commit:
        conn.commit()


def next_invoice_no(conn: sqlite3.Connection) -> int:
    """Reads and increments the sequential invoice counter. Never commits
    itself -- must be called inside the same transaction as mark_order_paid
    so a crash between the two can never produce a gap or a duplicate."""
    row = conn.execute("SELECT value FROM settings WHERE key = 'next_invoice_no'").fetchone()
    current = int(row["value"]) if row is not None else 1
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('next_invoice_no', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(current + 1),),
    )
    return current


# --- order items -----------------------------------------------------------


def create_order_item(
    conn: sqlite3.Connection,
    order_id: int,
    kind: str,
    product_id: Optional[int],
    name_snapshot: str,
    unit_price_snapshot_piasters: int,
    qty: int,
    line_total_piasters: int,
    note: Optional[str] = None,
    ps_session_id: Optional[int] = None,
    commit: bool = True,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO order_items (
            order_id, kind, product_id, name_snapshot, unit_price_snapshot_piasters,
            qty, line_total_piasters, note, ps_session_id, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            order_id,
            kind,
            product_id,
            name_snapshot,
            unit_price_snapshot_piasters,
            qty,
            line_total_piasters,
            note,
            ps_session_id,
            to_utc_iso(utc_now()),
        ),
    )
    if commit:
        conn.commit()
    return cursor.lastrowid


def get_order_item(conn: sqlite3.Connection, item_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM order_items WHERE id = ?", (item_id,)).fetchone()


def list_order_items(conn: sqlite3.Connection, order_id: int) -> List[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM order_items WHERE order_id = ? ORDER BY id", (order_id,)
    ).fetchall()


def update_item_qty(conn: sqlite3.Connection, item_id: int, qty: int, line_total_piasters: int, commit: bool = True) -> None:
    conn.execute(
        "UPDATE order_items SET qty = ?, line_total_piasters = ? WHERE id = ?",
        (qty, line_total_piasters, item_id),
    )
    if commit:
        conn.commit()


def update_item_note(conn: sqlite3.Connection, item_id: int, note: Optional[str], commit: bool = True) -> None:
    conn.execute("UPDATE order_items SET note = ? WHERE id = ?", (note, item_id))
    if commit:
        conn.commit()


def delete_order_item(conn: sqlite3.Connection, item_id: int, commit: bool = True) -> None:
    conn.execute("DELETE FROM order_item_addons WHERE order_item_id = ?", (item_id,))
    conn.execute("DELETE FROM order_items WHERE id = ?", (item_id,))
    if commit:
        conn.commit()


# --- order item addons ------------------------------------------------------


def create_item_addon(
    conn: sqlite3.Connection,
    order_item_id: int,
    addon_id: Optional[int],
    name_snapshot: str,
    price_delta_snapshot_piasters: int,
    commit: bool = True,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO order_item_addons (order_item_id, addon_id, name_snapshot, price_delta_snapshot_piasters)
        VALUES (?, ?, ?, ?)
        """,
        (order_item_id, addon_id, name_snapshot, price_delta_snapshot_piasters),
    )
    if commit:
        conn.commit()
    return cursor.lastrowid


def list_item_addons(conn: sqlite3.Connection, order_item_id: int) -> List[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM order_item_addons WHERE order_item_id = ? ORDER BY id", (order_item_id,)
    ).fetchall()


def set_cost_at_sale(conn: sqlite3.Connection, item_id: int, cost_at_sale_piasters: int, commit: bool = True) -> None:
    """Phase 9: the recipe-derived cost snapshot for one sold line (0 if
    the item/its add-ons have no recipe at all). Written once, at
    payment time, by stock_service.apply_sale_deductions -- never
    recomputed afterward, so a later price/recipe change cannot change
    past profit."""
    conn.execute("UPDATE order_items SET cost_at_sale_piasters = ? WHERE id = ?", (cost_at_sale_piasters, item_id))
    if commit:
        conn.commit()
