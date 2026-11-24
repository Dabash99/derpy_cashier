"""Customers and آجل (credit) sales/payments.

A credit sale is a normal paid order with payment_method left NULL and
customer_id set (see orders_repo.mark_order_paid_on_credit) -- it counts
as revenue (reports already include it: report_service's payment_methods
loop treats customer_id IS NOT NULL as the 'credit' bucket) and as an
open receivable (customer_ledger), but never touches the cash drawer --
drawer_service never sees a 'sale_cash' entry for it. A cash CUSTOMER
PAYMENT is the opposite: it does not change revenue, but it does put
real cash in the drawer (via extra_drawer_entries -- drawer_entries'
CHECK constraint is never widened, see drawer_repo.py).
"""
from __future__ import annotations

import sqlite3
from datetime import time as time_of_day
from typing import Optional

from derby.core import audit_service
from derby.core.db import (
    customer_ledger_repo,
    customers_repo,
    drawer_repo,
    orders_repo,
    ps_sessions_repo,
    settings_repo,
    shifts_repo,
)
from derby.core.events import bus
from derby.core.utils.business_date import business_date as compute_business_date
from derby.core.utils.money import format_egp
from derby.core.utils.time_utils import utc_now
from derby.features.customers.exceptions import InvalidAmountError, NameRequiredError
from derby.features.inventory import stock_service
from derby.features.pos import owner_approval
from derby.features.pos.exceptions import CreditNotAllowedError, SessionRunningError, ShiftRequiredError

ROLE_OWNER = "owner"
ROLE_CASHIER = "cashier"


def _close_time_setting(conn: sqlite3.Connection) -> time_of_day:
    text = settings_repo.get(conn, "business_close_time", "23:59") or "23:59"
    hour_str, minute_str = text.split(":")
    return time_of_day(int(hour_str), int(minute_str))


def today_business_date(conn: sqlite3.Connection) -> str:
    return compute_business_date(utc_now(), _close_time_setting(conn)).isoformat()


# --- customer CRUD -------------------------------------------------------


def create_customer(
    conn: sqlite3.Connection, name: str, phone: Optional[str], notes: Optional[str],
    credit_limit_piasters: Optional[int], requesting_user: sqlite3.Row,
) -> sqlite3.Row:
    name = (name or "").strip()
    if not name:
        raise NameRequiredError("name is required")
    customer_id = customers_repo.create_customer(conn, name, phone, notes, credit_limit_piasters)
    audit_service.log(
        conn, "customer_created", user=requesting_user, entity_type="customer", entity_id=customer_id,
        summary_ar="إضافة عميل: {0}".format(name), details={"name": name, "credit_limit_piasters": credit_limit_piasters},
    )
    return customers_repo.get_customer(conn, customer_id)


def update_customer(
    conn: sqlite3.Connection, customer_id: int, name: str, phone: Optional[str], notes: Optional[str],
    credit_limit_piasters: Optional[int], requesting_user: sqlite3.Row,
) -> sqlite3.Row:
    name = (name or "").strip()
    if not name:
        raise NameRequiredError("name is required")
    customers_repo.update_customer(conn, customer_id, name, phone, notes, credit_limit_piasters)
    audit_service.log(
        conn, "customer_updated", user=requesting_user, entity_type="customer", entity_id=customer_id,
        summary_ar="تعديل بيانات عميل: {0}".format(name),
    )
    return customers_repo.get_customer(conn, customer_id)


def set_active(conn: sqlite3.Connection, customer_id: int, is_active: bool, requesting_user: sqlite3.Row) -> None:
    customer = customers_repo.get_customer(conn, customer_id)
    customers_repo.set_active(conn, customer_id, is_active)
    audit_service.log(
        conn, "customer_deactivated" if not is_active else "customer_updated", user=requesting_user,
        entity_type="customer", entity_id=customer_id,
        summary_ar="{0} عميل: {1}".format("تعطيل" if not is_active else "تفعيل", customer["name"]),
    )


def balance_piasters(conn: sqlite3.Connection, customer_id: int) -> int:
    return customer_ledger_repo.balance_for_customer(conn, customer_id)


def is_overdue(conn: sqlite3.Connection, customer_id: int, overdue_days: int, today) -> bool:
    balance = balance_piasters(conn, customer_id)
    if balance <= 0:
        return False
    last_charge = customer_ledger_repo.last_charge_business_date(conn, customer_id)
    if last_charge is None:
        return False
    from datetime import date as date_cls

    age = (today - date_cls.fromisoformat(last_charge)).days
    return age > overdue_days


# --- credit sale ----------------------------------------------------------


def credit_sale(
    conn: sqlite3.Connection,
    order_id: int,
    customer_id: int,
    requesting_user: sqlite3.Row,
    approving_pin: Optional[str] = None,
) -> sqlite3.Row:
    order = orders_repo.get_order(conn, order_id)
    if order["status"] != "open":
        raise ValueError("order {0} is not open".format(order_id))
    if order["device_id"] is not None and ps_sessions_repo.get_running_session(conn, order["device_id"]) is not None:
        raise SessionRunningError("device {0} has a running session".format(order["device_id"]))
    if settings_repo.get(conn, "require_open_shift", "0") == "1" and shifts_repo.get_open_shift(conn) is None:
        raise ShiftRequiredError("a shift must be open before taking a payment")

    if requesting_user["role"] == ROLE_CASHIER and settings_repo.get(conn, "cashiers_may_sell_on_credit", "1") != "1":
        raise CreditNotAllowedError("cashiers may not sell on credit")

    customer = customers_repo.get_customer(conn, customer_id)
    limit = customer["credit_limit_piasters"]
    if limit is None:
        limit = int(settings_repo.get(conn, "default_customer_credit_limit_piasters", "0") or "0")
    current_balance = customer_ledger_repo.balance_for_customer(conn, customer_id)
    projected_balance = current_balance + order["total_piasters"]

    exceeded_limit = limit > 0 and projected_balance > limit
    approver_id = requesting_user["id"]
    if exceeded_limit:
        approver_id = owner_approval.resolve_approver(conn, requesting_user, approving_pin)

    today = today_business_date(conn)
    try:
        invoice_no = orders_repo.next_invoice_no(conn)
        orders_repo.mark_order_paid_on_credit(conn, order_id, invoice_no, requesting_user["id"], today, customer_id, commit=False)
        stock_service.apply_sale_deductions(conn, order_id, requesting_user["id"])
        paid_order = orders_repo.get_order(conn, order_id)
        customer_ledger_repo.add_entry(
            conn, customer_id, today, customer_ledger_repo.TYPE_CHARGE, paid_order["total_piasters"],
            order_id=order_id, user_id=requesting_user["id"], commit=False,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    bus.notify()

    audit_service.log(
        conn, "credit_sale", user=requesting_user, entity_type="customer", entity_id=customer_id,
        summary_ar="بيع بالآجل لـ {0}: {1}".format(customer["name"], format_egp(paid_order["total_piasters"])),
        details={
            "order_id": order_id, "amount_piasters": paid_order["total_piasters"],
            "projected_balance_piasters": projected_balance, "limit_piasters": limit,
            "exceeded_limit": exceeded_limit, "approved_by": approver_id,
        },
        severity=audit_service.SEVERITY_WARNING if exceeded_limit else audit_service.SEVERITY_INFO,
    )
    if exceeded_limit:
        audit_service.log(
            conn, "credit_limit_exceeded_approved", user=requesting_user, entity_type="customer", entity_id=customer_id,
            summary_ar="تجاوز حد الآجل لـ {0} بموافقة المالك".format(customer["name"]),
            details={"limit_piasters": limit, "projected_balance_piasters": projected_balance, "approved_by": approver_id},
            severity=audit_service.SEVERITY_WARNING,
        )
    return orders_repo.get_order(conn, order_id)


def reverse_credit_sale_on_void(conn: sqlite3.Connection, order: sqlite3.Row, requesting_user: sqlite3.Row, commit: bool = False) -> None:
    """Called by orders_service.void() -- a no-op unless this order was
    actually sold on آجل. Writes a REVERSAL row (never edits/removes the
    original charge, same append-only discipline as drawer_entries)."""
    if order["customer_id"] is None:
        return
    business_date = order["business_date"] or today_business_date(conn)
    customer_ledger_repo.add_entry(
        conn, order["customer_id"], business_date, customer_ledger_repo.TYPE_REVERSAL, -order["total_piasters"],
        order_id=order["id"], user_id=requesting_user["id"], note="عكس بسبب إبطال الفاتورة", commit=commit,
    )


# --- customer payments ------------------------------------------------------


def record_payment(
    conn: sqlite3.Connection,
    customer_id: int,
    amount_piasters: int,
    payment_method: str,
    requesting_user: sqlite3.Row,
    note: Optional[str] = None,
) -> sqlite3.Row:
    if amount_piasters <= 0:
        raise InvalidAmountError("amount must be positive")
    customer = customers_repo.get_customer(conn, customer_id)
    today = today_business_date(conn)
    open_shift = shifts_repo.get_open_shift(conn)
    shift_id = open_shift["id"] if open_shift is not None else None

    try:
        customer_ledger_repo.add_entry(
            conn, customer_id, today, customer_ledger_repo.TYPE_PAYMENT, -amount_piasters,
            payment_method=payment_method, user_id=requesting_user["id"], note=note, commit=False,
        )
        if payment_method == "cash":
            drawer_repo.create_extra_entry(
                conn, drawer_repo.TYPE_CUSTOMER_PAYMENT_CASH, amount_piasters, ref_type="customer", ref_id=customer_id,
                shift_id=shift_id, user_id=requesting_user["id"], note=note, commit=False,
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    bus.notify()

    audit_service.log(
        conn, "customer_payment_recorded", user=requesting_user, entity_type="customer", entity_id=customer_id,
        summary_ar="دفعة من {0}: {1} ({2})".format(customer["name"], format_egp(amount_piasters), payment_method),
        details={"amount_piasters": amount_piasters, "payment_method": payment_method, "note": note},
    )
    return customers_repo.get_customer(conn, customer_id)
