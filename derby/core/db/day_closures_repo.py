"""Data access for the day_closures table. A closure is never deleted --
rebuilding one bumps `revision` and overwrites the report/numbers, and
`stale` flags one whose underlying totals changed after it was built.
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from derby.core.utils.time_utils import to_utc_iso, utc_now


def create_closure(
    conn: sqlite3.Connection,
    business_date: str,
    trigger: str,
    report_text: str,
    invoice_count: int,
    net_sales_piasters: int,
    expenses_piasters: int,
    profit_piasters: int,
    open_orders_count: int,
    running_sessions_count: int,
    commit: bool = True,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO day_closures (
            business_date, revision, built_at_utc, trigger, report_text, invoice_count,
            net_sales_piasters, expenses_piasters, profit_piasters, open_orders_count,
            running_sessions_count, stale
        ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (
            business_date, to_utc_iso(utc_now()), trigger, report_text, invoice_count,
            net_sales_piasters, expenses_piasters, profit_piasters, open_orders_count, running_sessions_count,
        ),
    )
    if commit:
        conn.commit()
    return cursor.lastrowid


def get_closure(conn: sqlite3.Connection, closure_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM day_closures WHERE id = ?", (closure_id,)).fetchone()


def get_closure_by_date(conn: sqlite3.Connection, business_date: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM day_closures WHERE business_date = ?", (business_date,)).fetchone()


def get_last_closure(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM day_closures ORDER BY business_date DESC LIMIT 1").fetchone()


def list_closures(conn: sqlite3.Connection, limit: Optional[int] = None) -> List[sqlite3.Row]:
    query = "SELECT * FROM day_closures ORDER BY business_date DESC"
    if limit is not None:
        query += " LIMIT {0}".format(int(limit))
    return conn.execute(query).fetchall()


def list_recent_closures(conn: sqlite3.Connection, since_business_date: str) -> List[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM day_closures WHERE business_date >= ? ORDER BY business_date", (since_business_date,)
    ).fetchall()


def list_unsent_closures(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM day_closures WHERE sent_at_utc IS NULL ORDER BY business_date"
    ).fetchall()


def rebuild_closure(
    conn: sqlite3.Connection,
    closure_id: int,
    report_text: str,
    invoice_count: int,
    net_sales_piasters: int,
    expenses_piasters: int,
    profit_piasters: int,
    open_orders_count: int,
    running_sessions_count: int,
    commit: bool = True,
) -> None:
    conn.execute(
        """
        UPDATE day_closures
        SET revision = revision + 1, built_at_utc = ?, report_text = ?, invoice_count = ?,
            net_sales_piasters = ?, expenses_piasters = ?, profit_piasters = ?, open_orders_count = ?,
            running_sessions_count = ?, sent_at_utc = NULL, sent_by = NULL, stale = 0
        WHERE id = ?
        """,
        (
            to_utc_iso(utc_now()), report_text, invoice_count, net_sales_piasters, expenses_piasters,
            profit_piasters, open_orders_count, running_sessions_count, closure_id,
        ),
    )
    if commit:
        conn.commit()


def set_backup_status(
    conn: sqlite3.Connection,
    closure_id: int,
    backup_file_name: Optional[str],
    primary_status: Optional[str],
    secondary_status: Optional[str],
    message: Optional[str],
    commit: bool = True,
) -> None:
    conn.execute(
        """
        UPDATE day_closures
        SET backup_file_name = ?, backup_primary_status = ?, backup_secondary_status = ?, backup_message = ?
        WHERE id = ?
        """,
        (backup_file_name, primary_status, secondary_status, message, closure_id),
    )
    if commit:
        conn.commit()


def mark_sent(conn: sqlite3.Connection, closure_id: int, sent_by: int, commit: bool = True) -> None:
    conn.execute(
        "UPDATE day_closures SET sent_at_utc = ?, sent_by = ? WHERE id = ?",
        (to_utc_iso(utc_now()), sent_by, closure_id),
    )
    if commit:
        conn.commit()


def mark_stale(conn: sqlite3.Connection, closure_id: int, commit: bool = True) -> None:
    conn.execute("UPDATE day_closures SET stale = 1 WHERE id = ?", (closure_id,))
    if commit:
        conn.commit()
