"""Inventory business logic: purchases (with weighted-average costing),
recipe-based stock deduction at checkout, waste, stocktake, and the
repair/recompute path. No UI code here, same split as orders_service.py.

Transaction discipline matches orders_service.py: every repo call here
passes commit=False and the function finishes with exactly one commit
(via audit_repo.log, which commits as a side effect, or an explicit
conn.commit()). Any exception after a write has started rolls back
everything.
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from derby.core.db import (
    audit_repo,
    drawer_repo,
    expense_categories_repo,
    expenses_repo,
    orders_repo,
    ps_devices_repo,
    ps_sessions_repo,
    purchases_repo,
    recipes_repo,
    stock_items_repo,
    stock_movements_repo,
)
from derby.features.inventory.exceptions import InvalidQuantityError, WasteReasonRequiredError

SUPPLIES_EXPENSE_CATEGORY_NAME = "مشتريات"


# --- weighted-average costing ------------------------------------------------


def _apply_weighted_average(conn: sqlite3.Connection, stock_item_id: int, qty_added: float, unit_cost_piasters: float) -> None:
    item = stock_items_repo.get_stock_item(conn, stock_item_id)
    # A purchase is always a positive addition, so the weighted average is
    # computed against the stock's current, non-negative balance -- a
    # stock item that had gone negative (oversold) does not get to drag
    # the new average down further just because its sign is negative.
    existing_qty = max(item["current_qty"], 0.0)
    existing_value = existing_qty * item["avg_cost_piasters"]
    added_value = qty_added * unit_cost_piasters
    new_qty_basis = existing_qty + qty_added
    new_avg_cost = (existing_value + added_value) / new_qty_basis if new_qty_basis > 0 else unit_cost_piasters
    new_current_qty = item["current_qty"] + qty_added
    stock_items_repo.set_qty_and_cost(conn, stock_item_id, new_current_qty, new_avg_cost, commit=False)


def record_purchase(
    conn: sqlite3.Connection,
    supplier_id: Optional[int],
    purchase_date: str,
    lines: List[dict],
    is_paid: bool,
    user_id: int,
    note: Optional[str] = None,
) -> sqlite3.Row:
    """lines: a list of {stock_item_id, qty, unit_cost_piasters} dicts.
    Increases each stock item's quantity and recomputes its weighted
    average cost. If is_paid, also files a normal expense under
    "مشتريات" (so expense reports stay correct without double-counting --
    see report_service's COGS exclusion) and a drawer_entries row."""
    if not lines:
        raise InvalidQuantityError("a purchase needs at least one line")
    total_cost_piasters = sum(int(round(line["qty"] * line["unit_cost_piasters"])) for line in lines)

    try:
        purchase_id = purchases_repo.create_purchase(
            conn, supplier_id, purchase_date, total_cost_piasters, is_paid, user_id, note=note, commit=False
        )
        for line in lines:
            if line["qty"] <= 0:
                raise InvalidQuantityError("purchase quantity must be positive")
            line_total = int(round(line["qty"] * line["unit_cost_piasters"]))
            purchases_repo.create_purchase_line(
                conn, purchase_id, line["stock_item_id"], line["qty"], line["unit_cost_piasters"], line_total, commit=False
            )
            _apply_weighted_average(conn, line["stock_item_id"], line["qty"], line["unit_cost_piasters"])
            stock_movements_repo.create_movement(
                conn, line["stock_item_id"], stock_movements_repo.TYPE_PURCHASE, line["qty"],
                unit_cost_snapshot_piasters=line["unit_cost_piasters"], ref_type="purchase", ref_id=purchase_id,
                user_id=user_id, commit=False,
            )
        if is_paid:
            _file_purchase_expense(conn, purchase_id, total_cost_piasters, purchase_date, user_id)
        audit_repo.log(
            conn, "purchase_recorded", user_id=user_id,
            details="purchase={0} total={1} paid={2}".format(purchase_id, total_cost_piasters, is_paid),
        )
    except Exception:
        conn.rollback()
        raise
    return purchases_repo.get_purchase(conn, purchase_id)


def _supplies_category_id(conn: sqlite3.Connection) -> int:
    for category in expense_categories_repo.list_categories(conn):
        if category["name"] == SUPPLIES_EXPENSE_CATEGORY_NAME:
            return category["id"]
    # Belt-and-braces: migration 0009 always inserts this category, but a
    # fresh test DB built without running that migration's INSERT (e.g. a
    # hand-rolled schema) should still work rather than crash.
    return expense_categories_repo.create_category(conn, SUPPLIES_EXPENSE_CATEGORY_NAME)


def _file_purchase_expense(conn: sqlite3.Connection, purchase_id: int, total_cost_piasters: int, purchase_date: str, user_id: int) -> None:
    category_id = _supplies_category_id(conn)
    expense_id = expenses_repo.create_expense(
        conn, category_id, total_cost_piasters, purchase_date, "مشتريات مخزون", user_id, commit=False
    )
    purchases_repo.mark_paid(conn, purchase_id, expense_id, commit=False)
    drawer_repo.create_entry(
        conn, drawer_repo.TYPE_PURCHASE, -total_cost_piasters, ref_type="purchase", ref_id=purchase_id,
        user_id=user_id, commit=False,
    )


def mark_purchase_paid(conn: sqlite3.Connection, purchase_id: int, user_id: int) -> sqlite3.Row:
    purchase = purchases_repo.get_purchase(conn, purchase_id)
    if purchase["is_paid"]:
        from derby.features.inventory.exceptions import PurchaseAlreadyPaidError

        raise PurchaseAlreadyPaidError("purchase {0} is already paid".format(purchase_id))
    try:
        _file_purchase_expense(conn, purchase_id, purchase["total_cost_piasters"], purchase["purchase_date"], user_id)
        audit_repo.log(conn, "purchase_marked_paid", user_id=user_id, details="purchase={0}".format(purchase_id))
    except Exception:
        conn.rollback()
        raise
    return purchases_repo.get_purchase(conn, purchase_id)


# --- recipe-based deduction at checkout -------------------------------------


def _deduct_recipe(
    conn: sqlite3.Connection,
    owner_type: str,
    owner_id: int,
    multiplier: float,
    ref_type: str,
    ref_id: int,
    user_id: Optional[int],
) -> int:
    """Deducts qty_per_unit * multiplier of every stock item in this
    owner's recipe (a product or an add-on), and returns the total cost
    of that deduction in whole piasters. Stock is allowed to go negative
    -- the cafe must never be blocked from selling -- the low-stock
    screen is what surfaces the resulting warning."""
    total_cost_piasters = 0.0
    for recipe_line in recipes_repo.list_recipe_lines(conn, owner_type, owner_id):
        stock_item_id = recipe_line["stock_item_id"]
        qty_delta = -(recipe_line["qty_per_unit"] * multiplier)
        item = stock_items_repo.get_stock_item(conn, stock_item_id)
        cost_piasters = abs(qty_delta) * item["avg_cost_piasters"]
        total_cost_piasters += cost_piasters
        stock_items_repo.set_qty_and_cost(conn, stock_item_id, item["current_qty"] + qty_delta, item["avg_cost_piasters"], commit=False)
        stock_movements_repo.create_movement(
            conn, stock_item_id, stock_movements_repo.TYPE_SALE, qty_delta,
            unit_cost_snapshot_piasters=item["avg_cost_piasters"], ref_type=ref_type, ref_id=ref_id,
            user_id=user_id, commit=False,
        )
    return int(round(total_cost_piasters))


def apply_sale_deductions(conn: sqlite3.Connection, order_id: int, user_id: Optional[int]) -> None:
    """Called once, atomically, when an order is marked paid (see
    orders_service.pay). For every product line with a recipe, deducts
    stock for the line itself and for each of its add-ons, and stores the
    resulting total line cost as cost_at_sale_piasters -- a line with no
    recipe at all (and no addon recipes) gets cost_at_sale_piasters = 0,
    not NULL, so a paid order's items are unambiguous once sold; NULL
    stays reserved for an item that predates this phase's migration."""
    for item in orders_repo.list_order_items(conn, order_id):
        if item["kind"] == "product":
            line_cost = _deduct_recipe(
                conn, recipes_repo.OWNER_PRODUCT, item["product_id"], item["qty"], "order_item", item["id"], user_id
            )
            for addon in orders_repo.list_item_addons(conn, item["id"]):
                if addon["addon_id"] is None:
                    continue
                line_cost += _deduct_recipe(
                    conn, recipes_repo.OWNER_ADDON, addon["addon_id"], item["qty"], "order_item", item["id"], user_id
                )
            orders_repo.set_cost_at_sale(conn, item["id"], line_cost, commit=False)
        elif item["kind"] == "ps_time":
            orders_repo.set_cost_at_sale(conn, item["id"], _ps_item_cost(conn, item), commit=False)


def _ps_item_cost(conn: sqlite3.Connection, order_item: sqlite3.Row) -> int:
    """A PlayStation time line has no stock -- its only possible cost is
    the device's optional owner-set hourly electricity/wear cost
    (0 by default), pro-rated by the billed minutes."""
    if order_item["ps_session_id"] is None:
        return 0
    session = ps_sessions_repo.get_session(conn, order_item["ps_session_id"])
    if session is None or session["billed_minutes"] is None:
        return 0
    device = ps_devices_repo.get_device(conn, session["device_id"])
    if device is None or device["hourly_cost_piasters"] == 0:
        return 0
    return int(round(device["hourly_cost_piasters"] * session["billed_minutes"] / 60.0))


def reverse_sale_deductions(conn: sqlite3.Connection, order_id: int, user_id: Optional[int]) -> None:
    """Called when a paid order is voided (see orders_service.void): every
    stock_movements row this order's items caused gets an equal-and-
    opposite 'return' movement, and stock_items.current_qty is restored
    to match. Original rows are never edited -- the ledger stays
    append-only."""
    for item in orders_repo.list_order_items(conn, order_id):
        for movement in stock_movements_repo.list_movements_for_ref(conn, "order_item", item["id"]):
            if movement["movement_type"] != stock_movements_repo.TYPE_SALE:
                continue
            reversed_qty = -movement["qty_delta"]
            stock_item = stock_items_repo.get_stock_item(conn, movement["stock_item_id"])
            stock_items_repo.set_qty_and_cost(
                conn, movement["stock_item_id"], stock_item["current_qty"] + reversed_qty, stock_item["avg_cost_piasters"], commit=False
            )
            stock_movements_repo.create_movement(
                conn, movement["stock_item_id"], stock_movements_repo.TYPE_RETURN, reversed_qty,
                unit_cost_snapshot_piasters=movement["unit_cost_snapshot_piasters"], ref_type="order_item", ref_id=item["id"],
                user_id=user_id, commit=False,
            )


# --- waste / stocktake -------------------------------------------------------


def record_waste(conn: sqlite3.Connection, stock_item_id: int, qty: float, reason: str, user_id: int) -> sqlite3.Row:
    if qty <= 0:
        raise InvalidQuantityError("waste quantity must be positive")
    reason = (reason or "").strip()
    if not reason:
        raise WasteReasonRequiredError("a reason is required")
    item = stock_items_repo.get_stock_item(conn, stock_item_id)
    try:
        stock_items_repo.set_qty_and_cost(conn, stock_item_id, item["current_qty"] - qty, item["avg_cost_piasters"], commit=False)
        stock_movements_repo.create_movement(
            conn, stock_item_id, stock_movements_repo.TYPE_WASTE, -qty,
            unit_cost_snapshot_piasters=item["avg_cost_piasters"], user_id=user_id, note=reason, commit=False,
        )
        audit_repo.log(conn, "stock_waste", user_id=user_id, details="item={0} qty={1} reason={2}".format(stock_item_id, qty, reason))
    except Exception:
        conn.rollback()
        raise
    return stock_items_repo.get_stock_item(conn, stock_item_id)


def waste_cost_piasters(conn: sqlite3.Connection, start_date_iso: str, end_date_iso: str) -> int:
    return stock_movements_repo.sum_waste_cost_in_range(conn, start_date_iso, end_date_iso)


def record_stocktake(conn: sqlite3.Connection, stock_item_id: int, counted_qty: float, user_id: int, note: Optional[str] = None) -> sqlite3.Row:
    """Creates an adjustment movement for (counted - current) and moves
    current_qty to the counted value. Returns the item row; the caller
    reads the difference off (counted_qty - returned current_qty before
    this call) if it wants to show the value of the difference."""
    item = stock_items_repo.get_stock_item(conn, stock_item_id)
    difference = counted_qty - item["current_qty"]
    try:
        if difference != 0:
            stock_movements_repo.create_movement(
                conn, stock_item_id, stock_movements_repo.TYPE_ADJUSTMENT, difference,
                unit_cost_snapshot_piasters=item["avg_cost_piasters"], user_id=user_id, note=note, commit=False,
            )
        stock_items_repo.set_qty_and_cost(conn, stock_item_id, counted_qty, item["avg_cost_piasters"], commit=False)
        audit_repo.log(
            conn, "stocktake", user_id=user_id,
            details="item={0} counted={1} difference={2}".format(stock_item_id, counted_qty, difference),
        )
    except Exception:
        conn.rollback()
        raise
    return stock_items_repo.get_stock_item(conn, stock_item_id)


# --- repair -------------------------------------------------------------


def recompute_current_qty(conn: sqlite3.Connection, stock_item_id: int) -> float:
    """current_qty must always equal the sum of this item's movements --
    the repair path if it is ever suspected to have drifted."""
    total = stock_movements_repo.sum_qty_delta(conn, stock_item_id)
    item = stock_items_repo.get_stock_item(conn, stock_item_id)
    stock_items_repo.set_qty_and_cost(conn, stock_item_id, total, item["avg_cost_piasters"])
    return total


def stock_value_piasters(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(current_qty * avg_cost_piasters), 0) AS total FROM stock_items WHERE is_active = 1"
    ).fetchone()
    return int(round(row["total"]))
