"""Data access for the shifts table. One physical drawer/till -- at most
one shift is ever open at a time, across both roles (see shift_service
for the enforcement; this module is plain CRUD/queries only).
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from derby.core.utils.time_utils import to_utc_iso, utc_now

STATUS_OPEN = "open"
STATUS_CLOSED = "closed"


def create_shift(
    conn: sqlite3.Connection, user_id: int, business_date: str, opening_cash_piasters: int, commit: bool = True
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO shifts (user_id, business_date, opened_at_utc, opening_cash_piasters, status)
        VALUES (?, ?, ?, ?, 'open')
        """,
        (user_id, business_date, to_utc_iso(utc_now()), opening_cash_piasters),
    )
    if commit:
        conn.commit()
    return cursor.lastrowid


def get_shift(conn: sqlite3.Connection, shift_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM shifts WHERE id = ?", (shift_id,)).fetchone()


def get_open_shift(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    """At most one shift is ever open (one physical till) -- see
    shift_service.open_shift, which enforces this before INSERTing."""
    return conn.execute("SELECT * FROM shifts WHERE status = 'open' ORDER BY id DESC LIMIT 1").fetchone()


def close_shift(
    conn: sqlite3.Connection,
    shift_id: int,
    counted_cash_piasters: int,
    expected_cash_piasters: int,
    notes: Optional[str],
    handed_over_to_user_id: Optional[int] = None,
    commit: bool = True,
) -> None:
    difference = counted_cash_piasters - expected_cash_piasters
    conn.execute(
        """
        UPDATE shifts
        SET closed_at_utc = ?, counted_cash_piasters = ?, expected_cash_piasters = ?,
            difference_piasters = ?, notes = ?, handed_over_to_user_id = ?, status = 'closed'
        WHERE id = ?
        """,
        (to_utc_iso(utc_now()), counted_cash_piasters, expected_cash_piasters, difference, notes, handed_over_to_user_id, shift_id),
    )
    if commit:
        conn.commit()


def list_shifts(
    conn: sqlite3.Connection,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_id: Optional[int] = None,
) -> List[sqlite3.Row]:
    clauses = []
    params: list = []
    if start_date is not None:
        clauses.append("business_date >= ?")
        params.append(start_date)
    if end_date is not None:
        clauses.append("business_date <= ?")
        params.append(end_date)
    if user_id is not None:
        clauses.append("user_id = ?")
        params.append(user_id)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return conn.execute("SELECT * FROM shifts" + where + " ORDER BY opened_at_utc DESC", tuple(params)).fetchall()


def list_open_shifts_opened_before(conn: sqlite3.Connection, cutoff_utc: str) -> List[sqlite3.Row]:
    """Shifts still open that were opened before `cutoff_utc` -- used by
    the dashboard's "شيفت فات ميعاده بدون قفل" warning (a shift still
    open past the current business-day close)."""
    return conn.execute(
        "SELECT * FROM shifts WHERE status = 'open' AND opened_at_utc < ? ORDER BY opened_at_utc", (cutoff_utc,)
    ).fetchall()
