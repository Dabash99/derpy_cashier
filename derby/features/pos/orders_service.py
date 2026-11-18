"""The cart/order state machine: open -> paid, open -> cancelled,
paid -> void. No UI code here -- every function takes plain data and a
sqlite3 connection, so it's fully testable without Qt.

Transaction discipline: every repo call here passes commit=False and the
function finishes with exactly one commit (either an audit_repo.log(...)
call, which commits as a side effect, or an explicit conn.commit()). If
anything raises after a write has started, we roll back everything.
"""
from __future__ import annotations

import sqlite3
from datetime import time as time_of_day
from typing import List, Optional

from derby.core.db import audit_repo, orders_repo, products_repo, settings_repo, users_repo
from derby.core.utils.business_date import business_date as compute_business_date
from derby.core.utils.time_utils import parse_utc_iso, utc_now
from derby.features.pos import discount_math, owner_approval
from derby.features.pos.addon_selection import validate_and_snapshot_addons
from derby.features.pos.exceptions import (
    DiscountExceedsSubtotalError,
    DiscountReasonRequiredError,
    InvalidTransitionError,
    PermissionDeniedError,
    QuantityOutOfRangeError,
    TableBusyError,
    VoidReasonRequiredError,
)

MIN_QTY = 1
MAX_QTY = 99


def _require_open(order: sqlite3.Row) -> None:
    if order["status"] != "open":
        raise InvalidTransitionError("order {0} is not open (status={1})".format(order["id"], order["status"]))


def _close_time_setting(conn: sqlite3.Connection) -> time_of_day:
    text = settings_repo.get(conn, "business_close_time", "23:59") or "23:59"
    hour_str, minute_str = text.split(":")
    return time_of_day(int(hour_str), int(minute_str))


def is_from_previous_business_day(conn: sqlite3.Connection, order: sqlite3.Row) -> bool:
    """An open order has no business_date yet (that's only assigned at
    payment) -- this compares when it was opened against "today" using the
    same close-time rule, for the tables screen's "من يوم سابق" badge."""
    close_time = _close_time_setting(conn)
    opened_business_date = compute_business_date(parse_utc_iso(order["opened_at_utc"]), close_time)
    today_business_date = compute_business_date(utc_now(), close_time)
    return opened_business_date != today_business_date


# --- opening orders ----------------------------------------------------


def get_or_create_table_order(conn: sqlite3.Connection, table_id: int, user_id: int) -> sqlite3.Row:
    existing = orders_repo.get_open_order_for_table(conn, table_id)
    if existing is not None:
        return existing
    order_id = orders_repo.create_order(conn, table_id, user_id)
    return orders_repo.get_order(conn, order_id)


def create_takeaway_order(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row:
    # Takeaway orders are never shared/reused -- every "new takeaway" click
    # starts a fresh one, unlike a table which reopens its existing order.
    order_id = orders_repo.create_order(conn, None, user_id)
    return orders_repo.get_order(conn, order_id)


# --- totals --------------------------------------------------------------


def recompute_totals(conn: sqlite3.Connection, order_id: int, commit: bool = True) -> None:
    items = orders_repo.list_order_items(conn, order_id)
    subtotal = sum(item["line_total_piasters"] for item in items)
    order = orders_repo.get_order(conn, order_id)
    discount = order["discount_piasters"]
    if discount > subtotal:
        # Items were removed after a discount was applied -- the discount
        # can never exceed the (now smaller) subtotal.
        discount = subtotal
    total = subtotal - discount
    orders_repo.update_order_totals(conn, order_id, subtotal, discount, total, commit=commit)


# --- cart lines ------------------------------------------------------------


def add_item(
    conn: sqlite3.Connection,
    order_id: int,
    product_id: int,
    qty: int,
    addon_ids: List[int],
    note: Optional[str],
    user_id: int,
) -> sqlite3.Row:
    if not (MIN_QTY <= qty <= MAX_QTY):
        raise QuantityOutOfRangeError("qty must be between {0} and {1}".format(MIN_QTY, MAX_QTY))

    order = orders_repo.get_order(conn, order_id)
    _require_open(order)

    product = products_repo.get_product(conn, product_id)
    addon_snapshots = validate_and_snapshot_addons(conn, product_id, addon_ids)
    addon_id_set = frozenset(snapshot.addon_id for snapshot in addon_snapshots)
    addon_total_per_unit = sum(snapshot.price_delta_piasters for snapshot in addon_snapshots)
    unit_price = product["price_piasters"]
    normalized_note = note.strip() if note else None

    try:
        if not normalized_note:
            merge_target = _find_mergeable_item(conn, order_id, product_id, addon_id_set)
            if merge_target is not None:
                new_qty = merge_target["qty"] + qty
                if new_qty > MAX_QTY:
                    raise QuantityOutOfRangeError("merged quantity would exceed {0}".format(MAX_QTY))
                line_total = (unit_price + addon_total_per_unit) * new_qty
                orders_repo.update_item_qty(conn, merge_target["id"], new_qty, line_total, commit=False)
                recompute_totals(conn, order_id, commit=False)
                conn.commit()
                return orders_repo.get_order_item(conn, merge_target["id"])

        line_total = (unit_price + addon_total_per_unit) * qty
        item_id = orders_repo.create_order_item(
            conn, order_id, "product", product_id, product["name_ar"], unit_price, qty, line_total, normalized_note, commit=False
        )
        for snapshot in addon_snapshots:
            orders_repo.create_item_addon(
                conn, item_id, snapshot.addon_id, snapshot.name, snapshot.price_delta_piasters, commit=False
            )
        recompute_totals(conn, order_id, commit=False)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return orders_repo.get_order_item(conn, item_id)


def _find_mergeable_item(conn, order_id, product_id, addon_id_set) -> Optional[sqlite3.Row]:
    for existing_item in orders_repo.list_order_items(conn, order_id):
        if existing_item["kind"] != "product" or existing_item["product_id"] != product_id:
            continue
        if existing_item["note"]:
            continue
        existing_addon_ids = frozenset(
            row["addon_id"] for row in orders_repo.list_item_addons(conn, existing_item["id"])
        )
        if existing_addon_ids == addon_id_set:
            return existing_item
    return None


def change_qty(conn: sqlite3.Connection, order_id: int, item_id: int, new_qty: int) -> None:
    if not (MIN_QTY <= new_qty <= MAX_QTY):
        raise QuantityOutOfRangeError("qty must be between {0} and {1}".format(MIN_QTY, MAX_QTY))
    order = orders_repo.get_order(conn, order_id)
    _require_open(order)
    item = orders_repo.get_order_item(conn, item_id)
    addon_total_per_unit = sum(
        row["price_delta_snapshot_piasters"] for row in orders_repo.list_item_addons(conn, item_id)
    )
    line_total = (item["unit_price_snapshot_piasters"] + addon_total_per_unit) * new_qty
    try:
        orders_repo.update_item_qty(conn, item_id, new_qty, line_total, commit=False)
        recompute_totals(conn, order_id, commit=False)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def remove_item(conn: sqlite3.Connection, order_id: int, item_id: int) -> None:
    order = orders_repo.get_order(conn, order_id)
    _require_open(order)
    try:
        orders_repo.delete_order_item(conn, item_id, commit=False)
        recompute_totals(conn, order_id, commit=False)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def set_item_note(conn: sqlite3.Connection, order_id: int, item_id: int, note: Optional[str]) -> None:
    order = orders_repo.get_order(conn, order_id)
    _require_open(order)
    orders_repo.update_item_note(conn, item_id, note.strip() if note else None)


# --- discounts ---------------------------------------------------------


def apply_discount(
    conn: sqlite3.Connection,
    order_id: int,
    kind: str,
    amount: int,
    reason: str,
    requesting_user: sqlite3.Row,
    approving_pin: Optional[str] = None,
) -> sqlite3.Row:
    reason = (reason or "").strip()
    if not reason:
        raise DiscountReasonRequiredError("a reason is required")

    order = orders_repo.get_order(conn, order_id)
    _require_open(order)

    discount_piasters = discount_math.compute_discount_piasters(kind, amount, order["subtotal_piasters"])
    if discount_piasters > order["subtotal_piasters"]:
        raise DiscountExceedsSubtotalError("discount cannot exceed the subtotal")

    approver_id = _resolve_approver(conn, requesting_user, approving_pin)

    try:
        orders_repo.set_order_discount(conn, order_id, discount_piasters, reason, approver_id, commit=False)
        recompute_totals(conn, order_id, commit=False)
        audit_repo.log(
            conn,
            "discount_applied",
            user_id=requesting_user["id"],
            details="order={0} amount={1} reason={2} approved_by={3}".format(
                order_id, discount_piasters, reason, approver_id
            ),
        )
    except Exception:
        conn.rollback()
        raise
    return orders_repo.get_order(conn, order_id)


def remove_discount(
    conn: sqlite3.Connection, order_id: int, requesting_user: sqlite3.Row, approving_pin: Optional[str] = None
) -> sqlite3.Row:
    order = orders_repo.get_order(conn, order_id)
    _require_open(order)

    approver_id = _resolve_approver(conn, requesting_user, approving_pin)

    try:
        orders_repo.clear_order_discount(conn, order_id, commit=False)
        recompute_totals(conn, order_id, commit=False)
        audit_repo.log(
            conn,
            "discount_removed",
            user_id=requesting_user["id"],
            details="order={0} approved_by={1}".format(order_id, approver_id),
        )
    except Exception:
        conn.rollback()
        raise
    return orders_repo.get_order(conn, order_id)


def _resolve_approver(conn: sqlite3.Connection, requesting_user: sqlite3.Row, approving_pin: Optional[str]) -> int:
    """Owner acting on their own order needs no extra PIN. A cashier always
    does -- verify_owner_pin raises if it's wrong/locked out."""
    if requesting_user["role"] == users_repo.ROLE_OWNER:
        return requesting_user["id"]
    owner = owner_approval.verify_owner_pin(conn, approving_pin or "")
    return owner["id"]


# --- cancel / pay / void ----------------------------------------------------


def cancel(
    conn: sqlite3.Connection, order_id: int, requesting_user: sqlite3.Row, approving_pin: Optional[str] = None
) -> sqlite3.Row:
    order = orders_repo.get_order(conn, order_id)
    _require_open(order)

    has_items = len(orders_repo.list_order_items(conn, order_id)) > 0
    approver_id = None
    if has_items:
        approver_id = _resolve_approver(conn, requesting_user, approving_pin)

    try:
        orders_repo.mark_order_cancelled(conn, order_id, commit=False)
        audit_repo.log(
            conn,
            "order_cancelled",
            user_id=requesting_user["id"],
            details="order={0} approved_by={1}".format(order_id, approver_id),
        )
    except Exception:
        conn.rollback()
        raise
    return orders_repo.get_order(conn, order_id)


def pay(conn: sqlite3.Connection, order_id: int, payment_method: str, requesting_user: sqlite3.Row) -> sqlite3.Row:
    order = orders_repo.get_order(conn, order_id)
    _require_open(order)

    close_time = _close_time_setting(conn)
    today = compute_business_date(utc_now(), close_time).isoformat()

    try:
        invoice_no = orders_repo.next_invoice_no(conn)
        orders_repo.mark_order_paid(
            conn, order_id, invoice_no, requesting_user["id"], today, payment_method, commit=False
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return orders_repo.get_order(conn, order_id)


def void(conn: sqlite3.Connection, order_id: int, reason: str, requesting_user: sqlite3.Row) -> sqlite3.Row:
    if requesting_user["role"] != users_repo.ROLE_OWNER:
        raise PermissionDeniedError("only the owner can void a paid order")
    reason = (reason or "").strip()
    if not reason:
        raise VoidReasonRequiredError("a reason is required")

    order = orders_repo.get_order(conn, order_id)
    if order["status"] != "paid":
        raise InvalidTransitionError("order {0} is not paid (status={1})".format(order_id, order["status"]))

    try:
        orders_repo.mark_order_void(conn, order_id, requesting_user["id"], reason, commit=False)
        audit_repo.log(
            conn, "order_voided", user_id=requesting_user["id"], details="order={0} reason={1}".format(order_id, reason)
        )
    except Exception:
        conn.rollback()
        raise
    return orders_repo.get_order(conn, order_id)


# --- moving orders (Phase 4 will reuse this for PlayStation devices) -------


def move_order(conn: sqlite3.Connection, order_id: int, target_table_id: Optional[int], requesting_user: sqlite3.Row) -> sqlite3.Row:
    order = orders_repo.get_order(conn, order_id)
    _require_open(order)

    if target_table_id is not None:
        busy_order = orders_repo.get_open_order_for_table(conn, target_table_id)
        if busy_order is not None and busy_order["id"] != order_id:
            raise TableBusyError("table {0} already has an open order".format(target_table_id))

    from_table_id = order["table_id"]
    try:
        orders_repo.set_order_table(conn, order_id, target_table_id, commit=False)
        audit_repo.log(
            conn,
            "order_moved",
            user_id=requesting_user["id"],
            details="order={0} from_table={1} to_table={2}".format(order_id, from_table_id, target_table_id),
        )
    except Exception:
        conn.rollback()
        raise
    return orders_repo.get_order(conn, order_id)
