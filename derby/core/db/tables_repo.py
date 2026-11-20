"""Data access for the `tables` table (dine-in tables, not DB tables)."""
from __future__ import annotations

import sqlite3
from typing import List, Optional


def _next_sort_order(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT MAX(sort_order) AS max_order FROM tables").fetchone()
    return (row["max_order"] or 0) + 1


def create_table(conn: sqlite3.Connection, name: str) -> int:
    sort_order = _next_sort_order(conn)
    cursor = conn.execute(
        "INSERT INTO tables (name, sort_order, is_active) VALUES (?, ?, 1)", (name, sort_order)
    )
    conn.commit()
    return cursor.lastrowid


def get_table(conn: sqlite3.Connection, table_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM tables WHERE id = ?", (table_id,)).fetchone()


def list_tables(conn: sqlite3.Connection, active_only: bool = False) -> List[sqlite3.Row]:
    if active_only:
        return conn.execute("SELECT * FROM tables WHERE is_active = 1 ORDER BY sort_order, id").fetchall()
    return conn.execute("SELECT * FROM tables ORDER BY sort_order, id").fetchall()


def rename_table(conn: sqlite3.Connection, table_id: int, new_name: str) -> None:
    conn.execute("UPDATE tables SET name = ? WHERE id = ?", (new_name, table_id))
    conn.commit()


def set_active(conn: sqlite3.Connection, table_id: int, is_active: bool) -> None:
    conn.execute("UPDATE tables SET is_active = ? WHERE id = ?", (1 if is_active else 0, table_id))
    conn.commit()


def move_table(conn: sqlite3.Connection, table_id: int, direction: int) -> None:
    """Swap this table's sort_order with its neighbor. direction is -1 (up) or +1 (down)."""
    ordered = list_tables(conn)
    index = next((i for i, row in enumerate(ordered) if row["id"] == table_id), None)
    if index is None:
        return
    neighbor_index = index + direction
    if neighbor_index < 0 or neighbor_index >= len(ordered):
        return
    current_row = ordered[index]
    neighbor_row = ordered[neighbor_index]
    conn.execute("UPDATE tables SET sort_order = ? WHERE id = ?", (neighbor_row["sort_order"], current_row["id"]))
    conn.execute("UPDATE tables SET sort_order = ? WHERE id = ?", (current_row["sort_order"], neighbor_row["id"]))
    conn.commit()
