"""Read-only aggregate queries for derby/features/reports/report_service.py.

Kept separate from orders_repo/expenses_repo because these queries join
across tables (orders+order_items+products+categories, or
order_items+ps_sessions) rather than operating on one table -- the
Python-side aggregation (grouping, totals, rounding rules) stays in
report_service; this module only ever returns raw rows.
"""
from __future__ import annotations

import sqlite3
from typing import List, Sequence


def list_paid_orders_in_range(conn: sqlite3.Connection, start_date: str, end_date: str) -> List[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM orders WHERE status = 'paid' AND business_date BETWEEN ? AND ? "
        "ORDER BY business_date, paid_at_utc",
        (start_date, end_date),
    ).fetchall()


def list_product_item_rows(conn: sqlite3.Connection, order_ids: Sequence[int]) -> List[sqlite3.Row]:
    """One row per product line of the given (paid) orders, with the
    product's CURRENT category name (not a historical snapshot -- the
    schema has no category snapshot on order_items)."""
    if not order_ids:
        return []
    placeholders = ",".join("?" for _ in order_ids)
    return conn.execute(
        """
        SELECT oi.name_snapshot AS name, oi.qty AS qty, oi.line_total_piasters AS revenue_piasters,
               c.name AS category_name
        FROM order_items oi
        LEFT JOIN products p ON p.id = oi.product_id
        LEFT JOIN categories c ON c.id = p.category_id
        WHERE oi.kind = 'product' AND oi.order_id IN ({0})
        """.format(placeholders),
        tuple(order_ids),
    ).fetchall()


def list_ps_item_rows(conn: sqlite3.Connection, order_ids: Sequence[int]) -> List[sqlite3.Row]:
    """One row per PlayStation line of the given (paid) orders. Lines whose
    session was later removed (voided) no longer exist in order_items, so
    they are excluded automatically -- no extra filter needed here."""
    if not order_ids:
        return []
    placeholders = ",".join("?" for _ in order_ids)
    return conn.execute(
        """
        SELECT oi.line_total_piasters AS revenue_piasters, oi.ps_session_id AS ps_session_id,
               ps.device_name_snapshot AS device_name, ps.actual_minutes AS actual_minutes
        FROM order_items oi
        LEFT JOIN ps_sessions ps ON ps.id = oi.ps_session_id
        WHERE oi.kind = 'ps_time' AND oi.order_id IN ({0})
        """.format(placeholders),
        tuple(order_ids),
    ).fetchall()
