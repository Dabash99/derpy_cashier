"""Data access for drawer_entries (the immutable cash ledger) and
drawer_counts (physical counts and their difference vs expected).

drawer_entries rows are never updated or deleted -- a correction is
always a new reversing row (see stock_service/drawer_service callers).
InstaPay sales never produce a drawer_entries row at all: they are not
cash, so they must never appear in the drawer math (see docs/SPEC.md).
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from derby.core.utils.time_utils import to_utc_iso, utc_now

TYPE_OPENING = "opening"
TYPE_SALE_CASH = "sale_cash"
TYPE_EXPENSE = "expense"
TYPE_PURCHASE = "purchase"
TYPE_DEPOSIT = "deposit"
TYPE_WITHDRAWAL = "withdrawal"
TYPE_REFUND = "refund"
TYPE_COUNT_ADJUSTMENT = "count_adjustment"


def create_entry(
    conn: sqlite3.Connection,
    entry_type: str,
    amount_delta_piasters: int,
    ref_type: Optional[str] = None,
    ref_id: Optional[int] = None,
    user_id: Optional[int] = None,
    note: Optional[str] = None,
    is_historical: bool = False,
    shift_id: Optional[int] = None,
    commit: bool = True,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO drawer_entries (entry_type, amount_delta_piasters, ref_type, ref_id, user_id, note, is_historical, shift_id, created_at_utc)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (entry_type, amount_delta_piasters, ref_type, ref_id, user_id, note, 1 if is_historical else 0, shift_id, to_utc_iso(utc_now())),
    )
    if commit:
        conn.commit()
    return cursor.lastrowid


def get_last_opening_entry(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    """The most recent LIVE (non-historical) 'opening' entry -- the drawer's
    live expected-cash balance starts counting from here, never from a
    backfilled historical row (see migrations.py's Phase 9 backfill)."""
    return conn.execute(
        "SELECT * FROM drawer_entries WHERE entry_type = 'opening' AND is_historical = 0 ORDER BY id DESC LIMIT 1"
    ).fetchone()


def sum_live_entries_from_id(conn: sqlite3.Connection, since_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(amount_delta_piasters), 0) AS total FROM drawer_entries "
        "WHERE is_historical = 0 AND id >= ?",
        (since_id,),
    ).fetchone()
    return row["total"]


def list_entries(
    conn: sqlite3.Connection,
    start_utc: Optional[str] = None,
    end_utc: Optional[str] = None,
    user_id: Optional[int] = None,
) -> List[sqlite3.Row]:
    clauses = []
    params: list = []
    if start_utc is not None:
        clauses.append("created_at_utc >= ?")
        params.append(start_utc)
    if end_utc is not None:
        clauses.append("created_at_utc <= ?")
        params.append(end_utc)
    if user_id is not None:
        clauses.append("user_id = ?")
        params.append(user_id)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return conn.execute(
        "SELECT * FROM drawer_entries" + where + " ORDER BY created_at_utc, id", tuple(params)
    ).fetchall()


def create_count(
    conn: sqlite3.Connection,
    expected_piasters: int,
    counted_piasters: int,
    user_id: int,
    denominations_json: Optional[str] = None,
    commit: bool = True,
) -> int:
    difference = counted_piasters - expected_piasters
    cursor = conn.execute(
        """
        INSERT INTO drawer_counts (expected_piasters, counted_piasters, difference_piasters, denominations_json, user_id, created_at_utc)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (expected_piasters, counted_piasters, difference, denominations_json, user_id, to_utc_iso(utc_now())),
    )
    if commit:
        conn.commit()
    return cursor.lastrowid


def list_counts(
    conn: sqlite3.Connection, start_utc: Optional[str] = None, end_utc: Optional[str] = None, user_id: Optional[int] = None
) -> List[sqlite3.Row]:
    clauses = []
    params: list = []
    if start_utc is not None:
        clauses.append("created_at_utc >= ?")
        params.append(start_utc)
    if end_utc is not None:
        clauses.append("created_at_utc <= ?")
        params.append(end_utc)
    if user_id is not None:
        clauses.append("user_id = ?")
        params.append(user_id)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return conn.execute(
        "SELECT * FROM drawer_counts" + where + " ORDER BY created_at_utc DESC, id DESC", tuple(params)
    ).fetchall()


def get_last_count(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM drawer_counts ORDER BY created_at_utc DESC, id DESC LIMIT 1").fetchone()


# --- extra_drawer_entries (Part D) --------------------------------------
#
# drawer_entries.entry_type is CHECK-constrained (migration 0009) to a
# fixed set that does not include a customer cash payment -- rather than
# widen that constraint, this is a second, parallel append-only ledger
# (migration 0015) with its own entry_type set, UNIONed into the live
# expected-cash balance by timestamp (see expected_cash_since_utc below)
# instead of by id, since ids across two different tables are not
# comparable.

TYPE_CUSTOMER_PAYMENT_CASH = "customer_payment_cash"


def create_extra_entry(
    conn: sqlite3.Connection,
    entry_type: str,
    amount_delta_piasters: int,
    ref_type: Optional[str] = None,
    ref_id: Optional[int] = None,
    shift_id: Optional[int] = None,
    user_id: Optional[int] = None,
    note: Optional[str] = None,
    commit: bool = True,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO extra_drawer_entries (entry_type, amount_delta_piasters, ref_type, ref_id, shift_id, user_id, note, created_at_utc)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (entry_type, amount_delta_piasters, ref_type, ref_id, shift_id, user_id, note, to_utc_iso(utc_now())),
    )
    if commit:
        conn.commit()
    return cursor.lastrowid


def sum_extra_entries_since(conn: sqlite3.Connection, since_utc: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(amount_delta_piasters), 0) AS total FROM extra_drawer_entries WHERE created_at_utc >= ?",
        (since_utc,),
    ).fetchone()
    return row["total"]


def list_extra_entries(
    conn: sqlite3.Connection, start_utc: Optional[str] = None, end_utc: Optional[str] = None
) -> List[sqlite3.Row]:
    clauses = []
    params: list = []
    if start_utc is not None:
        clauses.append("created_at_utc >= ?")
        params.append(start_utc)
    if end_utc is not None:
        clauses.append("created_at_utc <= ?")
        params.append(end_utc)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return conn.execute("SELECT * FROM extra_drawer_entries" + where + " ORDER BY created_at_utc, id", tuple(params)).fetchall()
