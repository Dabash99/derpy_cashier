"""Data access for the attendance table (clock in/out + manual corrections)."""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from derby.core.utils.time_utils import to_utc_iso, utc_now


def clock_in(conn: sqlite3.Connection, employee_id: int, business_date: str, commit: bool = True) -> int:
    cursor = conn.execute(
        "INSERT INTO attendance (employee_id, business_date, clock_in_utc, created_at_utc) VALUES (?, ?, ?, ?)",
        (employee_id, business_date, to_utc_iso(utc_now()), to_utc_iso(utc_now())),
    )
    if commit:
        conn.commit()
    return cursor.lastrowid


def clock_out(conn: sqlite3.Connection, attendance_id: int, commit: bool = True) -> None:
    conn.execute("UPDATE attendance SET clock_out_utc = ? WHERE id = ?", (to_utc_iso(utc_now()), attendance_id))
    if commit:
        conn.commit()


def get_open_attendance(conn: sqlite3.Connection, employee_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM attendance WHERE employee_id = ? AND clock_out_utc IS NULL ORDER BY id DESC LIMIT 1",
        (employee_id,),
    ).fetchone()


def get_attendance(conn: sqlite3.Connection, attendance_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM attendance WHERE id = ?", (attendance_id,)).fetchone()


def list_for_employee(
    conn: sqlite3.Connection, employee_id: int, start_date: Optional[str] = None, end_date: Optional[str] = None
) -> List[sqlite3.Row]:
    clauses = ["employee_id = ?"]
    params: list = [employee_id]
    if start_date is not None:
        clauses.append("business_date >= ?")
        params.append(start_date)
    if end_date is not None:
        clauses.append("business_date <= ?")
        params.append(end_date)
    where = " WHERE " + " AND ".join(clauses)
    return conn.execute("SELECT * FROM attendance" + where + " ORDER BY business_date", tuple(params)).fetchall()


def correct(
    conn: sqlite3.Connection,
    attendance_id: int,
    clock_in_utc: Optional[str],
    clock_out_utc: Optional[str],
    reason: str,
    corrected_by: int,
) -> None:
    conn.execute(
        "UPDATE attendance SET clock_in_utc = ?, clock_out_utc = ?, corrected_by = ?, correction_reason = ? WHERE id = ?",
        (clock_in_utc, clock_out_utc, corrected_by, reason, attendance_id),
    )
    conn.commit()
