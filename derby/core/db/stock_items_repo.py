"""Data access for stock_items (raw-material inventory).

current_qty/min_qty/avg_cost_piasters are maintained by
derby/features/inventory/stock_service.py, never recomputed here --
this module only does the SQL. See migrations.py for why quantities are
REAL while avg_cost_piasters is also REAL (a per-gram cost is routinely
fractional).
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from derby.core.utils.time_utils import to_utc_iso, utc_now

UNITS = ("g", "kg", "ml", "l", "piece")


def create_stock_item(
    conn: sqlite3.Connection,
    name: str,
    unit: str,
    min_qty: float = 0.0,
    commit: bool = True,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO stock_items (name, unit, current_qty, min_qty, avg_cost_piasters, is_active, created_at_utc)
        VALUES (?, ?, 0, ?, 0, 1, ?)
        """,
        (name, unit, min_qty, to_utc_iso(utc_now())),
    )
    if commit:
        conn.commit()
    return cursor.lastrowid


def get_stock_item(conn: sqlite3.Connection, stock_item_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM stock_items WHERE id = ?", (stock_item_id,)).fetchone()


def find_by_name(conn: sqlite3.Connection, name: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM stock_items WHERE name = ?", (name,)).fetchone()


def list_stock_items(conn: sqlite3.Connection, active_only: bool = False) -> List[sqlite3.Row]:
    where = " WHERE is_active = 1" if active_only else ""
    return conn.execute("SELECT * FROM stock_items" + where + " ORDER BY name").fetchall()


def list_low_stock(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM stock_items WHERE is_active = 1 AND current_qty <= min_qty ORDER BY name"
    ).fetchall()


def update_stock_item(
    conn: sqlite3.Connection,
    stock_item_id: int,
    name: str,
    unit: str,
    min_qty: float,
    is_active: bool,
    commit: bool = True,
) -> None:
    conn.execute(
        "UPDATE stock_items SET name = ?, unit = ?, min_qty = ?, is_active = ? WHERE id = ?",
        (name, unit, min_qty, 1 if is_active else 0, stock_item_id),
    )
    if commit:
        conn.commit()


def set_qty_and_cost(
    conn: sqlite3.Connection, stock_item_id: int, current_qty: float, avg_cost_piasters: float, commit: bool = True
) -> None:
    """Writes the two values stock_service maintains as the single source
    of derived state -- never called with values computed anywhere else."""
    conn.execute(
        "UPDATE stock_items SET current_qty = ?, avg_cost_piasters = ? WHERE id = ?",
        (current_qty, avg_cost_piasters, stock_item_id),
    )
    if commit:
        conn.commit()
