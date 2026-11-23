"""Data access for the employees table (owner-only management screen)."""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from derby.core.utils.time_utils import to_utc_iso, utc_now

PAY_TYPE_DAILY = "daily"
PAY_TYPE_MONTHLY = "monthly"


def create_employee(
    conn: sqlite3.Connection,
    name: str,
    phone: Optional[str],
    job_title: Optional[str],
    pay_type: str,
    base_amount_piasters: int,
    linked_user_id: Optional[int] = None,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO employees (name, phone, job_title, pay_type, base_amount_piasters, is_active, linked_user_id, created_at_utc)
        VALUES (?, ?, ?, ?, ?, 1, ?, ?)
        """,
        (name, phone, job_title, pay_type, base_amount_piasters, linked_user_id, to_utc_iso(utc_now())),
    )
    conn.commit()
    return cursor.lastrowid


def get_employee(conn: sqlite3.Connection, employee_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM employees WHERE id = ?", (employee_id,)).fetchone()


def list_employees(conn: sqlite3.Connection, active_only: bool = False) -> List[sqlite3.Row]:
    if active_only:
        return conn.execute("SELECT * FROM employees WHERE is_active = 1 ORDER BY name").fetchall()
    return conn.execute("SELECT * FROM employees ORDER BY name").fetchall()


def update_employee(
    conn: sqlite3.Connection,
    employee_id: int,
    name: str,
    phone: Optional[str],
    job_title: Optional[str],
    pay_type: str,
    base_amount_piasters: int,
    linked_user_id: Optional[int],
) -> None:
    conn.execute(
        """
        UPDATE employees
        SET name = ?, phone = ?, job_title = ?, pay_type = ?, base_amount_piasters = ?, linked_user_id = ?
        WHERE id = ?
        """,
        (name, phone, job_title, pay_type, base_amount_piasters, linked_user_id, employee_id),
    )
    conn.commit()


def set_active(conn: sqlite3.Connection, employee_id: int, is_active: bool) -> None:
    conn.execute("UPDATE employees SET is_active = ? WHERE id = ?", (1 if is_active else 0, employee_id))
    conn.commit()
