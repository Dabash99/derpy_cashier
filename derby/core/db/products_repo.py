"""Data access for the products table.

Never hard-deleted (see categories_repo for why) -- "is_active" is the
only removal available. Price changes and audit logging are a feature
layer concern (derby/features/menu), not this file's: this module only
ever does the SQL.
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from derby.core.utils.time_utils import to_utc_iso, utc_now


def _next_sort_order(conn: sqlite3.Connection, category_id: int) -> int:
    row = conn.execute(
        "SELECT MAX(sort_order) AS max_order FROM products WHERE category_id = ?", (category_id,)
    ).fetchone()
    return (row["max_order"] or 0) + 1


def create_product(
    conn: sqlite3.Connection,
    category_id: int,
    name_ar: str,
    name_en: str,
    price_piasters: int,
    image_file: Optional[str] = None,
    needs_price_review: bool = False,
    commit: bool = True,
) -> int:
    now = to_utc_iso(utc_now())
    sort_order = _next_sort_order(conn, category_id)
    cursor = conn.execute(
        """
        INSERT INTO products (
            category_id, name_ar, name_en, price_piasters, image_file,
            is_active, sort_order, needs_price_review, created_at_utc, updated_at_utc
        ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
        """,
        (
            category_id,
            name_ar,
            name_en or None,
            price_piasters,
            image_file,
            sort_order,
            1 if needs_price_review else 0,
            now,
            now,
        ),
    )
    if commit:
        conn.commit()
    return cursor.lastrowid


def get_product(conn: sqlite3.Connection, product_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()


def find_product_by_name(
    conn: sqlite3.Connection, category_id: int, name_ar: str
) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM products WHERE category_id = ? AND name_ar = ?", (category_id, name_ar)
    ).fetchone()


def is_name_duplicate(
    conn: sqlite3.Connection, category_id: int, name_ar: str, exclude_id: Optional[int] = None
) -> bool:
    row = conn.execute(
        "SELECT id FROM products WHERE category_id = ? AND name_ar = ? AND id != ?",
        (category_id, name_ar, exclude_id if exclude_id is not None else -1),
    ).fetchone()
    return row is not None


def list_products(
    conn: sqlite3.Connection, category_id: Optional[int] = None, active_only: bool = False
) -> List[sqlite3.Row]:
    clauses = []
    params: list = []
    if category_id is not None:
        clauses.append("category_id = ?")
        params.append(category_id)
    if active_only:
        clauses.append("is_active = 1")
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return conn.execute(
        "SELECT * FROM products" + where + " ORDER BY sort_order, id", tuple(params)
    ).fetchall()


def update_product(
    conn: sqlite3.Connection,
    product_id: int,
    category_id: int,
    name_ar: str,
    name_en: str,
    price_piasters: int,
    image_file: Optional[str],
    is_active: bool,
    commit: bool = True,
) -> None:
    """Full save from the product dialog. Always clears needs_price_review:
    if the owner is in the dialog setting a price, that price is final."""
    conn.execute(
        """
        UPDATE products
        SET category_id = ?, name_ar = ?, name_en = ?, price_piasters = ?,
            image_file = ?, is_active = ?, needs_price_review = 0, updated_at_utc = ?
        WHERE id = ?
        """,
        (
            category_id,
            name_ar,
            name_en or None,
            price_piasters,
            image_file,
            1 if is_active else 0,
            to_utc_iso(utc_now()),
            product_id,
        ),
    )
    if commit:
        conn.commit()


def set_price_from_import(
    conn: sqlite3.Connection, product_id: int, price_piasters: int, image_file: Optional[str], commit: bool = True
) -> None:
    """Used only by the CSV importer's "update price+image" option -- keeps
    needs_price_review set, since an imported price is still a placeholder."""
    conn.execute(
        """
        UPDATE products
        SET price_piasters = ?, image_file = COALESCE(?, image_file),
            needs_price_review = 1, updated_at_utc = ?
        WHERE id = ?
        """,
        (price_piasters, image_file, to_utc_iso(utc_now()), product_id),
    )
    if commit:
        conn.commit()


def confirm_price(conn: sqlite3.Connection, product_id: int) -> None:
    """Clears needs_price_review without changing the price (the "تأكيد
    السعر" quick action)."""
    conn.execute(
        "UPDATE products SET needs_price_review = 0, updated_at_utc = ? WHERE id = ?",
        (to_utc_iso(utc_now()), product_id),
    )
    conn.commit()


def set_active(conn: sqlite3.Connection, product_id: int, is_active: bool) -> None:
    conn.execute(
        "UPDATE products SET is_active = ?, updated_at_utc = ? WHERE id = ?",
        (1 if is_active else 0, to_utc_iso(utc_now()), product_id),
    )
    conn.commit()
