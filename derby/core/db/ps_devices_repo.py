"""Data access for the `ps_devices` table (PlayStation devices)."""
from __future__ import annotations

import sqlite3
from typing import List, Optional


def _next_sort_order(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT MAX(sort_order) AS max_order FROM ps_devices").fetchone()
    return (row["max_order"] or 0) + 1


def create_device(
    conn: sqlite3.Connection, name: str, single_rate_piasters_per_hour: int = 0, multi_rate_piasters_per_hour: int = 0
) -> int:
    sort_order = _next_sort_order(conn)
    cursor = conn.execute(
        "INSERT INTO ps_devices (name, single_rate_piasters_per_hour, multi_rate_piasters_per_hour, sort_order, is_active) "
        "VALUES (?, ?, ?, ?, 1)",
        (name, single_rate_piasters_per_hour, multi_rate_piasters_per_hour, sort_order),
    )
    conn.commit()
    return cursor.lastrowid


def get_device(conn: sqlite3.Connection, device_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM ps_devices WHERE id = ?", (device_id,)).fetchone()


def list_devices(conn: sqlite3.Connection, active_only: bool = False) -> List[sqlite3.Row]:
    if active_only:
        return conn.execute("SELECT * FROM ps_devices WHERE is_active = 1 ORDER BY sort_order, id").fetchall()
    return conn.execute("SELECT * FROM ps_devices ORDER BY sort_order, id").fetchall()


def rename_device(conn: sqlite3.Connection, device_id: int, new_name: str) -> None:
    conn.execute("UPDATE ps_devices SET name = ? WHERE id = ?", (new_name, device_id))
    conn.commit()


def set_rates(
    conn: sqlite3.Connection, device_id: int, single_rate_piasters_per_hour: int, multi_rate_piasters_per_hour: int
) -> None:
    conn.execute(
        "UPDATE ps_devices SET single_rate_piasters_per_hour = ?, multi_rate_piasters_per_hour = ? WHERE id = ?",
        (single_rate_piasters_per_hour, multi_rate_piasters_per_hour, device_id),
    )
    conn.commit()


def set_active(conn: sqlite3.Connection, device_id: int, is_active: bool) -> None:
    conn.execute("UPDATE ps_devices SET is_active = ? WHERE id = ?", (1 if is_active else 0, device_id))
    conn.commit()


def move_device(conn: sqlite3.Connection, device_id: int, direction: int) -> None:
    """Swap this device's sort_order with its neighbor. direction is -1 (up) or +1 (down)."""
    ordered = list_devices(conn)
    index = next((i for i, row in enumerate(ordered) if row["id"] == device_id), None)
    if index is None:
        return
    neighbor_index = index + direction
    if neighbor_index < 0 or neighbor_index >= len(ordered):
        return
    current_row = ordered[index]
    neighbor_row = ordered[neighbor_index]
    conn.execute("UPDATE ps_devices SET sort_order = ? WHERE id = ?", (neighbor_row["sort_order"], current_row["id"]))
    conn.execute("UPDATE ps_devices SET sort_order = ? WHERE id = ?", (current_row["sort_order"], neighbor_row["id"]))
    conn.commit()
