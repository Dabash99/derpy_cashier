"""Data access for the expense_categories table.

Like categories_repo (menu), never hard-deleted. Unlike tables/ps_devices,
disabling a category IN USE is allowed here -- it only hides it from new
entries; past expenses keep pointing at it and still display normally.
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional


def _next_sort_order(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT MAX(sort_order) AS max_order FROM expense_categories").fetchone()
    return (row["max_order"] or 0) + 1


def create_category(conn: sqlite3.Connection, name: str) -> int:
    sort_order = _next_sort_order(conn)
    cursor = conn.execute(
        "INSERT INTO expense_categories (name, sort_order, is_active) VALUES (?, ?, 1)", (name, sort_order)
    )
    conn.commit()
    return cursor.lastrowid


def get_category(conn: sqlite3.Connection, category_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM expense_categories WHERE id = ?", (category_id,)).fetchone()


def list_categories(conn: sqlite3.Connection, active_only: bool = False) -> List[sqlite3.Row]:
    if active_only:
        return conn.execute(
            "SELECT * FROM expense_categories WHERE is_active = 1 ORDER BY sort_order, id"
        ).fetchall()
    return conn.execute("SELECT * FROM expense_categories ORDER BY sort_order, id").fetchall()


def rename_category(conn: sqlite3.Connection, category_id: int, new_name: str) -> None:
    conn.execute("UPDATE expense_categories SET name = ? WHERE id = ?", (new_name, category_id))
    conn.commit()


def set_active(conn: sqlite3.Connection, category_id: int, is_active: bool) -> None:
    conn.execute(
        "UPDATE expense_categories SET is_active = ? WHERE id = ?", (1 if is_active else 0, category_id)
    )
    conn.commit()


def move_category(conn: sqlite3.Connection, category_id: int, direction: int) -> None:
    """Swap this category's sort_order with its neighbor. direction is -1 (up) or +1 (down)."""
    ordered = list_categories(conn)
    index = next((i for i, row in enumerate(ordered) if row["id"] == category_id), None)
    if index is None:
        return
    neighbor_index = index + direction
    if neighbor_index < 0 or neighbor_index >= len(ordered):
        return
    current_row = ordered[index]
    neighbor_row = ordered[neighbor_index]
    conn.execute(
        "UPDATE expense_categories SET sort_order = ? WHERE id = ?", (neighbor_row["sort_order"], current_row["id"])
    )
    conn.execute(
        "UPDATE expense_categories SET sort_order = ? WHERE id = ?", (current_row["sort_order"], neighbor_row["id"])
    )
    conn.commit()
