"""Data access for addon_groups, addons, and the product<->group links.

An addon group (e.g. "الإضافات") has a min/max number of selectable addons
(e.g. "اختر من ١ إلى ٣") and is attached to one or more products.
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional

# --- groups ------------------------------------------------------------


def _next_group_sort_order(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT MAX(sort_order) AS max_order FROM addon_groups").fetchone()
    return (row["max_order"] or 0) + 1


def create_group(
    conn: sqlite3.Connection, name: str, min_select: int = 0, max_select: Optional[int] = None
) -> int:
    sort_order = _next_group_sort_order(conn)
    cursor = conn.execute(
        "INSERT INTO addon_groups (name, min_select, max_select, sort_order, is_active) "
        "VALUES (?, ?, ?, ?, 1)",
        (name, min_select, max_select, sort_order),
    )
    conn.commit()
    return cursor.lastrowid


def get_group(conn: sqlite3.Connection, group_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM addon_groups WHERE id = ?", (group_id,)).fetchone()


def list_groups(conn: sqlite3.Connection, active_only: bool = False) -> List[sqlite3.Row]:
    if active_only:
        return conn.execute(
            "SELECT * FROM addon_groups WHERE is_active = 1 ORDER BY sort_order, id"
        ).fetchall()
    return conn.execute("SELECT * FROM addon_groups ORDER BY sort_order, id").fetchall()


def update_group(
    conn: sqlite3.Connection, group_id: int, name: str, min_select: int, max_select: Optional[int]
) -> None:
    conn.execute(
        "UPDATE addon_groups SET name = ?, min_select = ?, max_select = ? WHERE id = ?",
        (name, min_select, max_select, group_id),
    )
    conn.commit()


def set_group_active(conn: sqlite3.Connection, group_id: int, is_active: bool) -> None:
    conn.execute(
        "UPDATE addon_groups SET is_active = ? WHERE id = ?", (1 if is_active else 0, group_id)
    )
    conn.commit()


# --- addons --------------------------------------------------------------


def _next_addon_sort_order(conn: sqlite3.Connection, group_id: int) -> int:
    row = conn.execute(
        "SELECT MAX(sort_order) AS max_order FROM addons WHERE group_id = ?", (group_id,)
    ).fetchone()
    return (row["max_order"] or 0) + 1


def create_addon(conn: sqlite3.Connection, group_id: int, name: str, price_delta_piasters: int) -> int:
    sort_order = _next_addon_sort_order(conn, group_id)
    cursor = conn.execute(
        "INSERT INTO addons (group_id, name, price_delta_piasters, sort_order, is_active) "
        "VALUES (?, ?, ?, ?, 1)",
        (group_id, name, price_delta_piasters, sort_order),
    )
    conn.commit()
    return cursor.lastrowid


def list_addons(conn: sqlite3.Connection, group_id: int, active_only: bool = False) -> List[sqlite3.Row]:
    if active_only:
        return conn.execute(
            "SELECT * FROM addons WHERE group_id = ? AND is_active = 1 ORDER BY sort_order, id",
            (group_id,),
        ).fetchall()
    return conn.execute(
        "SELECT * FROM addons WHERE group_id = ? ORDER BY sort_order, id", (group_id,)
    ).fetchall()


def update_addon(conn: sqlite3.Connection, addon_id: int, name: str, price_delta_piasters: int) -> None:
    conn.execute(
        "UPDATE addons SET name = ?, price_delta_piasters = ? WHERE id = ?",
        (name, price_delta_piasters, addon_id),
    )
    conn.commit()


def set_addon_active(conn: sqlite3.Connection, addon_id: int, is_active: bool) -> None:
    conn.execute("UPDATE addons SET is_active = ? WHERE id = ?", (1 if is_active else 0, addon_id))
    conn.commit()


# --- product <-> group links ----------------------------------------------


def get_product_group_ids(conn: sqlite3.Connection, product_id: int) -> List[int]:
    rows = conn.execute(
        "SELECT group_id FROM product_addon_groups WHERE product_id = ?", (product_id,)
    ).fetchall()
    return [row["group_id"] for row in rows]


def set_product_addon_groups(conn: sqlite3.Connection, product_id: int, group_ids: List[int]) -> None:
    """Replaces the full set of groups attached to a product."""
    conn.execute("DELETE FROM product_addon_groups WHERE product_id = ?", (product_id,))
    conn.executemany(
        "INSERT INTO product_addon_groups (product_id, group_id) VALUES (?, ?)",
        [(product_id, group_id) for group_id in group_ids],
    )
    conn.commit()
