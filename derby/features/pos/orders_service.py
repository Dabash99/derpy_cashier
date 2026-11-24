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

from derby.core import audit_service
from derby.core.db import (
    audit_repo,
    drawer_repo,
    orders_repo,
    products_repo,
    ps_sessions_repo,
    settings_repo,
    shifts_repo,
    users_repo,
)
from derby.core.events import bus
from derby.core.utils.business_date import business_date as compute_business_date
from derby.core.utils.money import format_egp
from derby.core.utils.time_utils import parse_utc_iso, utc_now
from derby.features.inventory import stock_service
from derby.features.pos import discount_math, owner_approval
from derby.features.pos.addon_selection import validate_and_snapshot_addons
from derby.features.pos.exceptions import (
    DeviceBusyError,
    DiscountExceedsSubtotalError,
    DiscountReasonRequiredError,
    InvalidTransitionError,
    PermissionDeniedError,
    QuantityOutOfRangeError,
    SessionRunningError,
    ShiftRequiredError,
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


def auto_cancel_empty_open_orders(conn: sqlite3.Connection, actor_user_id: Optional[int] = None) -> int:
    """Safety net for lazy order creation (opening a table/takeaway no
    longer creates a row until the first item is added): an order can
    still end up open with zero items -- e.g. every item was removed
    again, or the app closed mid-way through. Called once at startup and
    whenever the Cashier screen is left. A PlayStation device order with
    a RUNNING session is left alone even though it has no items yet
    (its ps_time line is only added when the session stops); one with no
    running session and no items is exactly the "leftover empty order"
    case the PS card's own إغلاق الفاتورة action also targets -- this
    sweep is what cleans it up if the cashier never clicks that."""
    cancelled = 0
    for order in orders_repo.list_open_orders(conn):
        if orders_repo.list_order_items(conn, order["id"]):
            continue
        if order["device_id"] is not None and ps_sessions_repo.get_running_session(conn, order["device_id"]) is not None:
            continue
        try:
            orders_repo.mark_order_cancelled(conn, order["id"], commit=False)
            audit_repo.log(conn, "auto_cancel_empty", user_id=actor_user_id, details="order={0}".format(order["id"]))
        except Exception:
            conn.rollback()
            raise
        cancelled += 1
    if cancelled:
        bus.notify()
    return cancelled


def create_takeaway_order(conn: sqlite3.Connection, user_id: int, label: Optional[str] = None) -> sqlite3.Row:
    # Takeaway orders are never shared/reused -- every "new takeaway" click
    # starts a fresh one, unlike a table which reopens its existing order.
    order_id = orders_repo.create_order(conn, None, user_id, label=(label or "").strip() or None)
    return orders_repo.get_order(conn, order_id)


def get_or_create_device_order(conn: sqlite3.Connection, device_id: int, user_id: int) -> sqlite3.Row:
    existing = orders_repo.get_open_order_for_device(conn, device_id)
    if existing is not None:
        return existing
    order_id = orders_repo.create_order(conn, None, user_id, device_id=device_id)
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
                bus.notify()
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
    bus.notify()
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
    bus.notify()


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
    bus.notify()


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
    preset_name: Optional[str] = None,
) -> sqlite3.Row:
    reason = (reason or "").strip()
    if not reason:
        raise DiscountReasonRequiredError("a reason is required")

    order = orders_repo.get_order(conn, order_id)
    _require_open(order)

    discount_piasters = discount_math.compute_discount_piasters(kind, amount, order["subtotal_piasters"])
    if discount_piasters > order["subtotal_piasters"]:
        raise DiscountExceedsSubtotalError("discount cannot exceed the subtotal")

    approver_id = owner_approval.resolve_approver(conn, requesting_user, approving_pin)

    try:
        orders_repo.set_order_discount(conn, order_id, discount_piasters, reason, approver_id, commit=False)
        recompute_totals(conn, order_id, commit=False)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    bus.notify()
    audit_service.log(
        conn, "discount_preset_used" if preset_name else "discount_applied", user=requesting_user,
        entity_type="order", entity_id=order_id,
        summary_ar="تطبيق خصم {0}{1} على فاتورة #{2}: {3}".format(
            format_egp(discount_piasters), " ({0})".format(preset_name) if preset_name else "", order_id, reason
        ),
        details={
            "kind": kind, "amount": amount, "discount_piasters": discount_piasters, "reason": reason,
            "approved_by": approver_id, "preset_name": preset_name,
        },
        severity=audit_service.SEVERITY_WARNING,
    )
    return orders_repo.get_order(conn, order_id)


def remove_discount(
    conn: sqlite3.Connection, order_id: int, requesting_user: sqlite3.Row, approving_pin: Optional[str] = None
) -> sqlite3.Row:
    order = orders_repo.get_order(conn, order_id)
    _require_open(order)

    approver_id = owner_approval.resolve_approver(conn, requesting_user, approving_pin)

    try:
        orders_repo.clear_order_discount(conn, order_id, commit=False)
        recompute_totals(conn, order_id, commit=False)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    bus.notify()
    audit_service.log(
        conn, "discount_removed", user=requesting_user, entity_type="order", entity_id=order_id,
        summary_ar="إلغاء خصم عن فاتورة #{0}".format(order_id), details={"approved_by": approver_id},
    )
    return orders_repo.get_order(conn, order_id)


# --- cancel / pay / void ----------------------------------------------------


def cancel(
    conn: sqlite3.Connection, order_id: int, requesting_user: sqlite3.Row, approving_pin: Optional[str] = None
) -> sqlite3.Row:
    order = orders_repo.get_order(conn, order_id)
    _require_open(order)

    has_items = len(orders_repo.list_order_items(conn, order_id)) > 0
    approver_id = None
    if has_items:
        approver_id = owner_approval.resolve_approver(conn, requesting_user, approving_pin)

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
    bus.notify()
    return orders_repo.get_order(conn, order_id)


def pay(conn: sqlite3.Connection, order_id: int, payment_method: str, requesting_user: sqlite3.Row) -> sqlite3.Row:
    order = orders_repo.get_order(conn, order_id)
    _require_open(order)
    if order["device_id"] is not None and ps_sessions_repo.get_running_session(conn, order["device_id"]) is not None:
        raise SessionRunningError("device {0} has a running session".format(order["device_id"]))
    if settings_repo.get(conn, "require_open_shift", "0") == "1" and shifts_repo.get_open_shift(conn) is None:
        raise ShiftRequiredError("a shift must be open before taking a payment")

    close_time = _close_time_setting(conn)
    today = compute_business_date(utc_now(), close_time).isoformat()
    # Opportunistic linking only (Phase 11 Part C) -- the shift REPORT
    # itself is computed by real time window (see shift_service.
    # build_shift_report), not by this column, so a NULL shift_id here
    # (no shift open, require_open_shift off) never loses any data.
    open_shift = shifts_repo.get_open_shift(conn)
    shift_id = open_shift["id"] if open_shift is not None else None

    try:
        invoice_no = orders_repo.next_invoice_no(conn)
        orders_repo.mark_order_paid(
            conn, order_id, invoice_no, requesting_user["id"], today, payment_method, commit=False
        )
        if shift_id is not None:
            orders_repo.set_shift_id(conn, order_id, shift_id, commit=False)
        stock_service.apply_sale_deductions(conn, order_id, requesting_user["id"])
        if payment_method == "cash":
            # InstaPay is deliberately excluded here -- it never touches
            # the physical drawer (see docs/SPEC.md and drawer_repo.py).
            paid_order = orders_repo.get_order(conn, order_id)
            drawer_repo.create_entry(
                conn, drawer_repo.TYPE_SALE_CASH, paid_order["total_piasters"], ref_type="order", ref_id=order_id,
                user_id=requesting_user["id"], shift_id=shift_id, commit=False,
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    bus.notify()
    return orders_repo.get_order(conn, order_id)


def void(conn: sqlite3.Connection, order_id: int, reason: str, requesting_user: sqlite3.Row) -> sqlite3.Row:
    if requesting_user["role"] != users_repo.ROLE_OWNER:
        audit_service.log(
            conn, "permission_denied", user=requesting_user, entity_type="order", entity_id=order_id,
            summary_ar="محاولة إبطال فاتورة #{0} بدون صلاحية".format(order_id), severity=audit_service.SEVERITY_WARNING,
        )
        raise PermissionDeniedError("only the owner can void a paid order")
    reason = (reason or "").strip()
    if not reason:
        raise VoidReasonRequiredError("a reason is required")

    order = orders_repo.get_order(conn, order_id)
    if order["status"] != "paid":
        raise InvalidTransitionError("order {0} is not paid (status={1})".format(order_id, order["status"]))

    try:
        stock_service.reverse_sale_deductions(conn, order_id, requesting_user["id"])
        orders_repo.mark_order_void(conn, order_id, requesting_user["id"], reason, commit=False)
        if order["customer_id"] is not None:
            from derby.features.customers import (
                customer_service,  # local import: avoids a cross-feature import at module load time
            )

            customer_service.reverse_credit_sale_on_void(conn, order, requesting_user, commit=False)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    bus.notify()
    if order["customer_id"] is not None:
        audit_service.log(
            conn, "credit_sale_void_reversed", user=requesting_user, entity_type="customer", entity_id=order["customer_id"],
            summary_ar="عكس بيع بالآجل بسبب إبطال فاتورة #{0}".format(order_id),
            details={"order_id": order_id, "amount_piasters": order["total_piasters"]},
            severity=audit_service.SEVERITY_WARNING,
        )
    audit_service.log(
        conn, "order_voided", user=requesting_user, entity_type="order", entity_id=order_id,
        summary_ar="إبطال فاتورة #{0}: {1}".format(order_id, reason),
        details={"total_piasters": order["total_piasters"], "payment_method": order["payment_method"], "reason": reason},
        severity=audit_service.SEVERITY_CRITICAL,
    )
    return orders_repo.get_order(conn, order_id)


# --- moving orders (generic: a table or a PlayStation device) --------------


def move_order(
    conn: sqlite3.Connection,
    order_id: int,
    target_table_id: Optional[int],
    requesting_user: sqlite3.Row,
    target_device_id: Optional[int] = None,
) -> sqlite3.Row:
    """Moves an order to a free table or a free device. table -> device is
    rejected if the device has an open order; device -> table is rejected if
    the table has an open order OR the device still has a running session
    (stop it first). Never merges -- a busy target is simply rejected."""
    order = orders_repo.get_order(conn, order_id)
    _require_open(order)

    if order["device_id"] is not None and ps_sessions_repo.get_running_session(conn, order["device_id"]) is not None:
        raise SessionRunningError("device {0} has a running session -- stop it before moving".format(order["device_id"]))

    if target_table_id is not None:
        busy_order = orders_repo.get_open_order_for_table(conn, target_table_id)
        if busy_order is not None and busy_order["id"] != order_id:
            raise TableBusyError("table {0} already has an open order".format(target_table_id))
    elif target_device_id is not None:
        busy_order = orders_repo.get_open_order_for_device(conn, target_device_id)
        if busy_order is not None and busy_order["id"] != order_id:
            raise DeviceBusyError("device {0} already has an open order".format(target_device_id))

    from_table_id = order["table_id"]
    from_device_id = order["device_id"]
    try:
        orders_repo.set_order_location(conn, order_id, table_id=target_table_id, device_id=target_device_id, commit=False)
        audit_repo.log(
            conn,
            "order_moved",
            user_id=requesting_user["id"],
            details="order={0} from_table={1} from_device={2} to_table={3} to_device={4}".format(
                order_id, from_table_id, from_device_id, target_table_id, target_device_id
            ),
        )
    except Exception:
        conn.rollback()
        raise
    bus.notify()
    return orders_repo.get_order(conn, order_id)


# --- removing a ps_time line (owner approval required, session kept, marked voided) -----


def remove_ps_item(
    conn: sqlite3.Connection,
    order_id: int,
    item_id: int,
    requesting_user: sqlite3.Row,
    approving_pin: Optional[str] = None,
) -> sqlite3.Row:
    order = orders_repo.get_order(conn, order_id)
    _require_open(order)
    item = orders_repo.get_order_item(conn, item_id)
    if item is None or item["kind"] != "ps_time":
        raise InvalidTransitionError("item {0} is not a ps_time line".format(item_id))

    approver_id = owner_approval.resolve_approver(conn, requesting_user, approving_pin)

    try:
        if item["ps_session_id"] is not None:
            ps_sessions_repo.mark_voided(conn, item["ps_session_id"], requesting_user["id"], commit=False)
        orders_repo.delete_order_item(conn, item_id, commit=False)
        recompute_totals(conn, order_id, commit=False)
        audit_repo.log(
            conn,
            "ps_line_removed",
            user_id=requesting_user["id"],
            details="order={0} item={1} approved_by={2}".format(order_id, item_id, approver_id),
        )
    except Exception:
        conn.rollback()
        raise
    bus.notify()
    return orders_repo.get_order(conn, order_id)
