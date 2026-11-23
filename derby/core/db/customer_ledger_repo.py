"""Data access for customer_ledger -- append-only by convention (no code
path ever UPDATEs or DELETEs a row; a correction is always a new
'reversal'/'adjustment' row, same discipline as drawer_entries).

Sign convention: 'charge' is stored positive (increases the balance the
customer owes), 'payment' and 'reversal' are stored negative (reduce
it), 'adjustment' carries whatever signed amount the owner enters. The
balance is always just SUM(amount_piasters).
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from derby.core.utils.time_utils import to_utc_iso, utc_now

TYPE_CHARGE = "charge"
TYPE_PAYMENT = "payment"
TYPE_ADJUSTMENT = "adjustment"
TYPE_REVERSAL = "reversal"


def add_entry(
    conn: sqlite3.Connection,
    customer_id: int,
    business_date: str,
    entry_type: str,
    amount_piasters: int,
    order_id: Optional[int] = None,
    payment_method: Optional[str] = None,
    user_id: Optional[int] = None,
    note: Optional[str] = None,
    commit: bool = True,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO customer_ledger (customer_id, business_date, entry_type, amount_piasters, order_id, payment_method, user_id, note, created_at_utc)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (customer_id, business_date, entry_type, amount_piasters, order_id, payment_method, user_id, note, to_utc_iso(utc_now())),
    )
    if commit:
        conn.commit()
    return cursor.lastrowid


def list_for_customer(conn: sqlite3.Connection, customer_id: int) -> List[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM customer_ledger WHERE customer_id = ? ORDER BY created_at_utc, id", (customer_id,)
    ).fetchall()


def balance_for_customer(conn: sqlite3.Connection, customer_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(amount_piasters), 0) AS total FROM customer_ledger WHERE customer_id = ?", (customer_id,)
    ).fetchone()
    return row["total"]


def last_activity_at(conn: sqlite3.Connection, customer_id: int) -> Optional[str]:
    row = conn.execute(
        "SELECT created_at_utc FROM customer_ledger WHERE customer_id = ? ORDER BY created_at_utc DESC LIMIT 1", (customer_id,)
    ).fetchone()
    return row["created_at_utc"] if row is not None else None


def last_charge_business_date(conn: sqlite3.Connection, customer_id: int) -> Optional[str]:
    """The most recent CHARGE's business_date -- used for a simple
    "overdue" flag (balance > 0 and this is older than N days), a
    reasonable approximation rather than full per-invoice aging."""
    row = conn.execute(
        "SELECT business_date FROM customer_ledger WHERE customer_id = ? AND entry_type = 'charge' ORDER BY business_date DESC LIMIT 1",
        (customer_id,),
    ).fetchone()
    return row["business_date"] if row is not None else None


def ledger_entries_between(conn: sqlite3.Connection, start_utc: str, end_utc: str) -> List[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM customer_ledger WHERE created_at_utc >= ? AND created_at_utc <= ? ORDER BY created_at_utc",
        (start_utc, end_utc),
    ).fetchall()


def total_outstanding(conn: sqlite3.Connection) -> int:
    """Sum of every customer's POSITIVE balance only -- a customer who
    has overpaid (a negative balance) must never offset someone else's
    receivable in this total."""
    total = 0
    for customer in conn.execute("SELECT id FROM customers WHERE is_active = 1").fetchall():
        balance = balance_for_customer(conn, customer["id"])
        if balance > 0:
            total += balance
    return total
