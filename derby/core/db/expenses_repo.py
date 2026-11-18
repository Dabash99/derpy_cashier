"""Data access for the expenses table.

Never deleted, never updated in place for a changed amount/date/category --
"editing" an expense is VOID the old row + INSERT a replacement linked via
replaced_by_id, both inside one transaction composed by expenses_service.
Write functions take `commit=False` so that service layer can do that
atomically, same pattern as orders_repo.
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from derby.core.utils.time_utils import to_utc_iso, utc_now

STATUS_ACTIVE = "active"
STATUS_VOID = "void"


def create_expense(
    conn: sqlite3.Connection,
    category_id: int,
    amount_piasters: int,
    expense_date: str,
    description: Optional[str],
    created_by: int,
    receipt_file: Optional[str] = None,
    recurring_id: Optional[int] = None,
    commit: bool = True,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO expenses (
            category_id, amount_piasters, expense_date, description, receipt_file,
            recurring_id, status, created_by, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            category_id, amount_piasters, expense_date, description, receipt_file,
            recurring_id, STATUS_ACTIVE, created_by, to_utc_iso(utc_now()),
        ),
    )
    if commit:
        conn.commit()
    return cursor.lastrowid


def get_expense(conn: sqlite3.Connection, expense_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()


def list_expenses(
    conn: sqlite3.Connection,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    category_id: Optional[int] = None,
    status: Optional[str] = None,
) -> List[sqlite3.Row]:
    clauses = []
    params: list = []
    if start_date is not None:
        clauses.append("expense_date >= ?")
        params.append(start_date)
    if end_date is not None:
        clauses.append("expense_date <= ?")
        params.append(end_date)
    if category_id is not None:
        clauses.append("category_id = ?")
        params.append(category_id)
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return conn.execute(
        "SELECT * FROM expenses" + where + " ORDER BY expense_date, id", tuple(params)
    ).fetchall()


def void_expense(
    conn: sqlite3.Connection,
    expense_id: int,
    voided_by: int,
    void_reason: str,
    replaced_by_id: Optional[int] = None,
    commit: bool = True,
) -> None:
    conn.execute(
        """
        UPDATE expenses
        SET status = ?, voided_by = ?, voided_at_utc = ?, void_reason = ?, replaced_by_id = ?
        WHERE id = ?
        """,
        (STATUS_VOID, voided_by, to_utc_iso(utc_now()), void_reason, replaced_by_id, expense_id),
    )
    if commit:
        conn.commit()
