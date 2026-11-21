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
    unit_cost_snapshot_piasters: float = 0.0,
    ref_type: Optional[str] = None,
    ref_id: Optional[int] = None,
    user_id: Optional[int] = None,
    note: Optional[str] = None,
    commit: bool = True,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO stock_movements (
            stock_item_id, movement_type, qty_delta, unit_cost_snapshot_piasters,
            ref_type, ref_id, user_id, note, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (stock_item_id, movement_type, qty_delta, unit_cost_snapshot_piasters, ref_type, ref_id, user_id, note, to_utc_iso(utc_now())),
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
