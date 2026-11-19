"""Data access for the supplies (shopping list) table -- see
derby/features/supplies/supplies_service.py for the business rules
(who can set a cost, converting a bought item into an expense).
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from derby.core.utils.time_utils import to_utc_iso, utc_now

PRIORITY_NORMAL = "عادي"
PRIORITY_URGENT = "مستعجل"

STATUS_NEEDED = "needed"
STATUS_BOUGHT = "bought"
STATUS_DROPPED = "dropped"


def create_supply(
    conn: sqlite3.Connection,
    name: str,
    quantity_note: Optional[str],
    priority: str,
    note: Optional[str],
    added_by: int,
    commit: bool = True,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO supplies (name, quantity_note, priority, status, note, added_by, added_at_utc)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (name, quantity_note, priority, STATUS_NEEDED, note, added_by, to_utc_iso(utc_now())),
    )
    if commit:
        conn.commit()
    return cursor.lastrowid


def get_supply(conn: sqlite3.Connection, supply_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM supplies WHERE id = ?", (supply_id,)).fetchone()


def list_supplies(conn: sqlite3.Connection, status: Optional[str] = None) -> List[sqlite3.Row]:
    where = " WHERE status = ?" if status is not None else ""
    params = (status,) if status is not None else ()
    return conn.execute(
        "SELECT * FROM supplies"
        + where
        + " ORDER BY CASE priority WHEN '{0}' THEN 0 ELSE 1 END, added_at_utc".format(PRIORITY_URGENT),
        params,
    ).fetchall()


def update_supply(
    conn: sqlite3.Connection,
    supply_id: int,
    name: str,
    quantity_note: Optional[str],
    priority: str,
    note: Optional[str],
    commit: bool = True,
) -> None:
    conn.execute(
        "UPDATE supplies SET name = ?, quantity_note = ?, priority = ?, note = ? WHERE id = ?",
        (name, quantity_note, priority, note, supply_id),
    )
    if commit:
        conn.commit()


def mark_bought(conn: sqlite3.Connection, supply_id: int, bought_by: int, commit: bool = True) -> None:
    conn.execute(
        "UPDATE supplies SET status = ?, bought_by = ?, bought_at_utc = ? WHERE id = ?",
        (STATUS_BOUGHT, bought_by, to_utc_iso(utc_now()), supply_id),
    )
    if commit:
        conn.commit()


def mark_dropped(conn: sqlite3.Connection, supply_id: int, commit: bool = True) -> None:
    conn.execute("UPDATE supplies SET status = ? WHERE id = ?", (STATUS_DROPPED, supply_id))
    if commit:
        conn.commit()


def set_cost_and_expense(conn: sqlite3.Connection, supply_id: int, cost_piasters: int, expense_id: int, commit: bool = True) -> None:
    conn.execute(
        "UPDATE supplies SET cost_piasters = ?, expense_id = ? WHERE id = ?", (cost_piasters, expense_id, supply_id)
    )
    if commit:
        conn.commit()
