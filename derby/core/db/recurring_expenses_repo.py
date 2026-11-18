"""Data access for the recurring_expenses table (templates like rent that
recur monthly). Generating the actual expense each month is a decision
made by derby/features/expenses/expenses_service.py, never silently here.
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from derby.core.utils.time_utils import to_utc_iso, utc_now


def create_template(
    conn: sqlite3.Connection, category_id: int, name: str, amount_piasters: int, day_of_month: int
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO recurring_expenses (category_id, name, amount_piasters, day_of_month, is_active, created_at_utc)
        VALUES (?, ?, ?, ?, 1, ?)
        """,
        (category_id, name, amount_piasters, day_of_month, to_utc_iso(utc_now())),
    )
    conn.commit()
    return cursor.lastrowid


def get_template(conn: sqlite3.Connection, template_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM recurring_expenses WHERE id = ?", (template_id,)).fetchone()


def list_templates(conn: sqlite3.Connection, active_only: bool = False) -> List[sqlite3.Row]:
    if active_only:
        return conn.execute("SELECT * FROM recurring_expenses WHERE is_active = 1 ORDER BY id").fetchall()
    return conn.execute("SELECT * FROM recurring_expenses ORDER BY id").fetchall()


def update_template(
    conn: sqlite3.Connection,
    template_id: int,
    category_id: int,
    name: str,
    amount_piasters: int,
    day_of_month: int,
) -> None:
    conn.execute(
        """
        UPDATE recurring_expenses SET category_id = ?, name = ?, amount_piasters = ?, day_of_month = ?
        WHERE id = ?
        """,
        (category_id, name, amount_piasters, day_of_month, template_id),
    )
    conn.commit()


def set_active(conn: sqlite3.Connection, template_id: int, is_active: bool) -> None:
    conn.execute("UPDATE recurring_expenses SET is_active = ? WHERE id = ?", (1 if is_active else 0, template_id))
    conn.commit()


def set_last_generated_month(conn: sqlite3.Connection, template_id: int, year_month: str, commit: bool = True) -> None:
    conn.execute("UPDATE recurring_expenses SET last_generated_month = ? WHERE id = ?", (year_month, template_id))
    if commit:
        conn.commit()
