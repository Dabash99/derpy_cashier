"""Data access for payroll_lines (advances/deductions/bonuses) and
payroll_payments (the monthly "تسجيل الدفع" result)."""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from derby.core.utils.time_utils import to_utc_iso, utc_now

KIND_ADVANCE = "advance"
KIND_DEDUCTION = "deduction"
KIND_BONUS = "bonus"


def add_line(
    conn: sqlite3.Connection, employee_id: int, kind: str, amount_piasters: int, line_date: str, note: Optional[str], user_id: int
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO payroll_lines (employee_id, kind, amount_piasters, line_date, note, created_by, created_at_utc)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (employee_id, kind, amount_piasters, line_date, note, user_id, to_utc_iso(utc_now())),
    )
    conn.commit()
    return cursor.lastrowid


def list_unapplied_lines(conn: sqlite3.Connection, employee_id: int, up_to_date: str) -> List[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM payroll_lines WHERE employee_id = ? AND applied_in_payment_id IS NULL AND line_date <= ? ORDER BY line_date",
        (employee_id, up_to_date),
    ).fetchall()


def mark_lines_applied(conn: sqlite3.Connection, line_ids: List[int], payment_id: int) -> None:
    for line_id in line_ids:
        conn.execute("UPDATE payroll_lines SET applied_in_payment_id = ? WHERE id = ?", (payment_id, line_id))
    conn.commit()


def create_payment(
    conn: sqlite3.Connection,
    employee_id: int,
    year_month: str,
    base_piasters: int,
    bonuses_piasters: int,
    advances_piasters: int,
    deductions_piasters: int,
    net_piasters: int,
    payment_method: str,
    expense_id: Optional[int],
    user_id: int,
    commit: bool = True,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO payroll_payments (
            employee_id, year_month, base_piasters, bonuses_piasters, advances_piasters,
            deductions_piasters, net_piasters, payment_method, expense_id, created_by, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            employee_id, year_month, base_piasters, bonuses_piasters, advances_piasters,
            deductions_piasters, net_piasters, payment_method, expense_id, user_id, to_utc_iso(utc_now()),
        ),
    )
    if commit:
        conn.commit()
    return cursor.lastrowid


def list_payments(conn: sqlite3.Connection, employee_id: Optional[int] = None, year_month: Optional[str] = None) -> List[sqlite3.Row]:
    clauses = []
    params: list = []
    if employee_id is not None:
        clauses.append("employee_id = ?")
        params.append(employee_id)
    if year_month is not None:
        clauses.append("year_month = ?")
        params.append(year_month)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return conn.execute("SELECT * FROM payroll_payments" + where + " ORDER BY created_at_utc DESC", tuple(params)).fetchall()


def get_payment(conn: sqlite3.Connection, payment_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM payroll_payments WHERE id = ?", (payment_id,)).fetchone()
