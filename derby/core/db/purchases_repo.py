"""Data access for purchases and purchase_lines.

Recomputing stock quantities/weighted-average cost from a purchase is a
service concern (derby/features/inventory/stock_service.py); this module
only stores the purchase record itself. Write functions take
`commit=False` so the service layer can compose a purchase, its lines,
the resulting stock_movements rows, and (if paid) an expense all inside
one transaction.
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from derby.core.utils.time_utils import to_utc_iso, utc_now


def create_purchase(
    conn: sqlite3.Connection,
    supplier_id: Optional[int],
    purchase_date: str,
    total_cost_piasters: int,
    is_paid: bool,
    created_by: int,
    note: Optional[str] = None,
    commit: bool = True,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO purchases (supplier_id, purchase_date, total_cost_piasters, is_paid, note, created_by, created_at_utc)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (supplier_id, purchase_date, total_cost_piasters, 1 if is_paid else 0, note or None, created_by, to_utc_iso(utc_now())),
    )
    if commit:
        conn.commit()
    return cursor.lastrowid


def get_purchase(conn: sqlite3.Connection, purchase_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM purchases WHERE id = ?", (purchase_id,)).fetchone()


def list_purchases(
    conn: sqlite3.Connection, start_date: Optional[str] = None, end_date: Optional[str] = None, is_paid: Optional[bool] = None
) -> List[sqlite3.Row]:
    clauses = []
    params: list = []
    if start_date is not None:
        clauses.append("purchase_date >= ?")
        params.append(start_date)
    if end_date is not None:
        clauses.append("purchase_date <= ?")
        params.append(end_date)
    if is_paid is not None:
        clauses.append("is_paid = ?")
        params.append(1 if is_paid else 0)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return conn.execute(
        "SELECT * FROM purchases" + where + " ORDER BY purchase_date, id", tuple(params)
    ).fetchall()


def mark_paid(conn: sqlite3.Connection, purchase_id: int, expense_id: int, commit: bool = True) -> None:
    conn.execute("UPDATE purchases SET is_paid = 1, expense_id = ? WHERE id = ?", (expense_id, purchase_id))
    if commit:
        conn.commit()


def create_purchase_line(
    conn: sqlite3.Connection,
    purchase_id: int,
    stock_item_id: int,
    qty: float,
    unit_cost_piasters: float,
    total_cost_piasters: int,
    commit: bool = True,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO purchase_lines (purchase_id, stock_item_id, qty, unit_cost_piasters, total_cost_piasters)
        VALUES (?, ?, ?, ?, ?)
        """,
        (purchase_id, stock_item_id, qty, unit_cost_piasters, total_cost_piasters),
    )
    if commit:
        conn.commit()
    return cursor.lastrowid


def list_purchase_lines(conn: sqlite3.Connection, purchase_id: int) -> List[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM purchase_lines WHERE purchase_id = ? ORDER BY id", (purchase_id,)
    ).fetchall()
