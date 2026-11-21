"""Data access for recipe_lines.

owner_type/owner_id is a small polymorphic reference (no FK, by design --
SQLite FKs can't target "whichever table owner_type names") to either a
products row or an addons row, so both a menu item and an add-on can
carry a recipe. A missing recipe for a given owner means "no stock
deduction for this item", not an error -- callers simply get an empty
list.
"""
from __future__ import annotations

import sqlite3
from typing import List

OWNER_PRODUCT = "product"
OWNER_ADDON = "addon"


def set_recipe(
    conn: sqlite3.Connection, owner_type: str, owner_id: int, lines: List[dict], commit: bool = True
) -> None:
    """Replaces the whole recipe for one owner (product or addon) with
    `lines`, each a dict with stock_item_id and qty_per_unit. Called from
    the product/add-on edit screen's "Recipe" section, which always saves
    the full set rather than individual add/remove calls."""
    conn.execute("DELETE FROM recipe_lines WHERE owner_type = ? AND owner_id = ?", (owner_type, owner_id))
    for line in lines:
        conn.execute(
            "INSERT INTO recipe_lines (owner_type, owner_id, stock_item_id, qty_per_unit) VALUES (?, ?, ?, ?)",
            (owner_type, owner_id, line["stock_item_id"], line["qty_per_unit"]),
        )
    if commit:
        conn.commit()


def list_recipe_lines(conn: sqlite3.Connection, owner_type: str, owner_id: int) -> List[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM recipe_lines WHERE owner_type = ? AND owner_id = ? ORDER BY id", (owner_type, owner_id)
    ).fetchall()


def has_recipe(conn: sqlite3.Connection, owner_type: str, owner_id: int) -> bool:
    return conn.execute(
        "SELECT 1 FROM recipe_lines WHERE owner_type = ? AND owner_id = ? LIMIT 1", (owner_type, owner_id)
    ).fetchone() is not None


def list_recipes_using_stock_item(conn: sqlite3.Connection, stock_item_id: int) -> List[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM recipe_lines WHERE stock_item_id = ? ORDER BY owner_type, owner_id", (stock_item_id,)
    ).fetchall()
