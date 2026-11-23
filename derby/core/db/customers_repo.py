"""Data access for the customers table."""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from derby.core.utils.time_utils import to_utc_iso, utc_now


def create_customer(
    conn: sqlite3.Connection, name: str, phone: Optional[str], notes: Optional[str], credit_limit_piasters: Optional[int]
) -> int:
    cursor = conn.execute(
        "INSERT INTO customers (name, phone, notes, credit_limit_piasters, is_active, created_at_utc) VALUES (?, ?, ?, ?, 1, ?)",
        (name, phone, notes, credit_limit_piasters, to_utc_iso(utc_now())),
    )
    conn.commit()
    return cursor.lastrowid


def get_customer(conn: sqlite3.Connection, customer_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()


def list_customers(conn: sqlite3.Connection, active_only: bool = False, search_text: Optional[str] = None) -> List[sqlite3.Row]:
    clauses = []
    params: list = []
    if active_only:
        clauses.append("is_active = 1")
    if search_text:
        clauses.append("(name LIKE ? OR phone LIKE ?)")
        like = "%{0}%".format(search_text)
        params.extend([like, like])
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return conn.execute("SELECT * FROM customers" + where + " ORDER BY name", tuple(params)).fetchall()


def update_customer(
    conn: sqlite3.Connection, customer_id: int, name: str, phone: Optional[str], notes: Optional[str], credit_limit_piasters: Optional[int]
) -> None:
    conn.execute(
        "UPDATE customers SET name = ?, phone = ?, notes = ?, credit_limit_piasters = ? WHERE id = ?",
        (name, phone, notes, credit_limit_piasters, customer_id),
    )
    conn.commit()


def set_active(conn: sqlite3.Connection, customer_id: int, is_active: bool) -> None:
    conn.execute("UPDATE customers SET is_active = ? WHERE id = ?", (1 if is_active else 0, customer_id))
    conn.commit()
