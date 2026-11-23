"""قائمة إعادة الطلب: from low-stock items, a shopping list grouped by
supplier with a suggested quantity -- target_qty if the owner set one
(stock_items.target_qty, migration 0016), else min_qty x 2 as a simple
default. The supplier for each item is inferred from its most recent
purchase (purchases_repo.last_supplier_name_for_stock_item) rather than
a new fixed column, since stock_items never had one.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Dict, List

from derby.core.db import purchases_repo, stock_items_repo
from derby.core.i18n import ar

_DEFAULT_TARGET_MULTIPLIER = 2.0


@dataclass
class ReorderLine:
    stock_item: sqlite3.Row
    target_qty: float
    suggested_qty: float
    supplier_name: str


def _target_qty(item: sqlite3.Row) -> float:
    if item["target_qty"] is not None and item["target_qty"] > 0:
        return item["target_qty"]
    return item["min_qty"] * _DEFAULT_TARGET_MULTIPLIER


def build_reorder_list(conn: sqlite3.Connection) -> Dict[str, List[ReorderLine]]:
    """Returns {supplier_name: [ReorderLine, ...]} -- "بدون مورد" groups
    items that have never been purchased (or were bought with no
    supplier on the purchase)."""
    grouped: Dict[str, List[ReorderLine]] = {}
    for item in stock_items_repo.list_low_stock(conn):
        target = _target_qty(item)
        suggested = max(0.0, target - item["current_qty"])
        supplier_name = purchases_repo.last_supplier_name_for_stock_item(conn, item["id"]) or ar.REORDER_LIST_NO_SUPPLIER
        grouped.setdefault(supplier_name, []).append(
            ReorderLine(stock_item=item, target_qty=target, suggested_qty=suggested, supplier_name=supplier_name)
        )
    return grouped


def set_target_qty(conn: sqlite3.Connection, stock_item_id: int, target_qty: float, requesting_user: sqlite3.Row) -> None:
    from derby.core import audit_service

    conn.execute("UPDATE stock_items SET target_qty = ? WHERE id = ?", (target_qty, stock_item_id))
    conn.commit()
    item = stock_items_repo.get_stock_item(conn, stock_item_id)
    audit_service.log(
        conn, "reorder_target_changed", user=requesting_user, entity_type="stock_item", entity_id=stock_item_id,
        summary_ar="تعديل مستوى إعادة الطلب لـ {0}: {1}".format(item["name"], target_qty),
    )


def format_quantity(qty: float, unit: str) -> str:
    if qty == int(qty):
        return "{0:d} {1}".format(int(qty), unit)
    return "{0:.2f} {1}".format(qty, unit)


def build_plain_text(conn: sqlite3.Connection, cafe_name: str) -> str:
    grouped = build_reorder_list(conn)
    if not grouped:
        return ar.REORDER_LIST_EMPTY
    lines = ["*{0}*".format(cafe_name), ar.REORDER_LIST_TITLE, ""]
    for supplier_name, items in grouped.items():
        lines.append("*{0}*".format(supplier_name))
        for line in items:
            lines.append(
                "- {0}: {1}".format(line.stock_item["name"], format_quantity(line.suggested_qty, line.stock_item["unit"]))
            )
        lines.append("")
    return "\n".join(lines).strip()
