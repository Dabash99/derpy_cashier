"""Data access for stock_movements -- the single source of truth for
stock quantity. stock_items.current_qty is a cached projection that
stock_service keeps in sync on every write; recompute_from_movements()
below is the repair path if it ever drifts.
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from derby.core.utils.time_utils import to_utc_iso, utc_now

TYPE_PURCHASE = "purchase"
TYPE_SALE = "sale"
TYPE_WASTE = "waste"
TYPE_ADJUSTMENT = "adjustment"
TYPE_RETURN = "return"


def create_movement(
    conn: sqlite3.Connection,
    stock_item_id: int,
    movement_type: str,
    qty_delta: float,
    business_date: str,
    unit_cost_snapshot_piasters: float = 0.0,
    ref_type: Optional[str] = None,
    ref_id: Optional[int] = None,
    user_id: Optional[int] = None,
    note: Optional[str] = None,
    commit: bool = True,
) -> int:
    """`business_date` (an ISO "YYYY-MM-DD" string) is required, not
    derived here -- this module stays pure data access, same as
    orders_repo/expenses_repo; the caller (stock_service) computes it
    with the same business_date()+business_close_time rule those
    other services already use, never a second invented rule."""
    cursor = conn.execute(
        """
        INSERT INTO stock_movements (
            stock_item_id, movement_type, qty_delta, unit_cost_snapshot_piasters,
            ref_type, ref_id, user_id, note, business_date, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            stock_item_id, movement_type, qty_delta, unit_cost_snapshot_piasters,
            ref_type, ref_id, user_id, note, business_date, to_utc_iso(utc_now()),
        ),
    )
    if commit:
        conn.commit()
    return cursor.lastrowid


def list_movements_for_item(conn: sqlite3.Connection, stock_item_id: int) -> List[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM stock_movements WHERE stock_item_id = ? ORDER BY created_at_utc, id", (stock_item_id,)
    ).fetchall()


def list_movements_for_ref(conn: sqlite3.Connection, ref_type: str, ref_id: int) -> List[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM stock_movements WHERE ref_type = ? AND ref_id = ? ORDER BY id", (ref_type, ref_id)
    ).fetchall()


def sum_qty_delta(conn: sqlite3.Connection, stock_item_id: int) -> float:
    row = conn.execute(
        "SELECT COALESCE(SUM(qty_delta), 0) AS total FROM stock_movements WHERE stock_item_id = ?", (stock_item_id,)
    ).fetchone()
    return row["total"]


def sum_waste_cost_in_range(conn: sqlite3.Connection, start_date_iso: str, end_date_iso: str) -> int:
    """Waste cost for a BUSINESS-date range (not a UTC calendar-date
    range) -- matches exactly how orders/expenses are ranged in
    report_service, so a late-night waste entry lands on the same
    business day as a late-night sale or expense would."""
    row = conn.execute(
        "SELECT COALESCE(SUM(-qty_delta * unit_cost_snapshot_piasters), 0) AS total FROM stock_movements "
        "WHERE movement_type = 'waste' AND business_date BETWEEN ? AND ?",
        (start_date_iso, end_date_iso),
    ).fetchone()
    return int(round(row["total"]))
