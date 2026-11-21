"""Data access for suppliers."""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from derby.core.utils.time_utils import to_utc_iso, utc_now


def create_supplier(
    conn: sqlite3.Connection, name: str, phone: Optional[str] = None, notes: Optional[str] = None, commit: bool = True
) -> int:
    cursor = conn.execute(
        "INSERT INTO suppliers (name, phone, notes, is_active, created_at_utc) VALUES (?, ?, ?, 1, ?)",
        (name, phone or None, notes or None, to_utc_iso(utc_now())),
    )
    if commit:
        conn.commit()
    return cursor.lastrowid


def get_supplier(conn: sqlite3.Connection, supplier_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()


def list_suppliers(conn: sqlite3.Connection, active_only: bool = False) -> List[sqlite3.Row]:
    where = " WHERE is_active = 1" if active_only else ""
    return conn.execute("SELECT * FROM suppliers" + where + " ORDER BY name").fetchall()


def update_supplier(
    conn: sqlite3.Connection,
    supplier_id: int,
    name: str,
    phone: Optional[str],
    notes: Optional[str],
    is_active: bool,
    commit: bool = True,
) -> None:
    conn.execute(
        "UPDATE suppliers SET name = ?, phone = ?, notes = ?, is_active = ? WHERE id = ?",
        (name, phone or None, notes or None, 1 if is_active else 0, supplier_id),
    )
    if commit:
        conn.commit()


def amount_owed_piasters(conn: sqlite3.Connection, supplier_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(total_cost_piasters), 0) AS total FROM purchases WHERE supplier_id = ? AND is_paid = 0",
        (supplier_id,),
    ).fetchone()
    return row["total"]
