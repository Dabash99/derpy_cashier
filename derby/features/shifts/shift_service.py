"""Shift open/close/handover and the shift report. One physical drawer
-- at most one shift is open at a time, across both roles -- so opening
a shift reuses the drawer's own opening balance (drawer_service) rather
than inventing a second cash concept, and closing a shift runs the
drawer's own count. The report itself is built from the real wall-clock
window [opened_at_utc, closed_at_utc or now] rather than from shift_id
stamps on individual rows (see orders_service.pay), so it is correct
even though not every write path threads shift_id through.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import time as time_of_day
from typing import Dict, Optional

from derby.core import audit_service
from derby.core.db import drawer_repo, orders_repo, shifts_repo
from derby.core.events import bus
from derby.core.utils.business_date import business_date as compute_business_date
from derby.core.utils.money import format_egp
from derby.core.utils.time_utils import to_utc_iso, utc_now
from derby.features.inventory import drawer_service
from derby.features.shifts.exceptions import NoOpenShiftError, ShiftAlreadyOpenError

_PAYMENT_METHODS = ("cash", "instapay", "credit")


@dataclass
class ShiftReport:
    shift_id: int
    sales_by_method_piasters: Dict[str, int] = field(default_factory=lambda: {m: 0 for m in _PAYMENT_METHODS})
    orders_by_method_count: Dict[str, int] = field(default_factory=lambda: {m: 0 for m in _PAYMENT_METHODS})
    order_count: int = 0
    void_count: int = 0
    discount_total_piasters: int = 0
    expenses_cash_piasters: int = 0
    opening_cash_piasters: int = 0
    expected_cash_piasters: int = 0
    counted_cash_piasters: Optional[int] = None
    difference_piasters: Optional[int] = None


def _close_time_setting(conn: sqlite3.Connection):
    from derby.core.db import settings_repo

    text = settings_repo.get(conn, "business_close_time", "23:59") or "23:59"
    hour_str, minute_str = text.split(":")
    return time_of_day(int(hour_str), int(minute_str))


def build_shift_report(conn: sqlite3.Connection, shift: sqlite3.Row) -> ShiftReport:
    start = shift["opened_at_utc"]
    end = shift["closed_at_utc"] or to_utc_iso(utc_now())

    report = ShiftReport(shift_id=shift["id"])
    for order in orders_repo.list_paid_between(conn, start, end):
        method_key = "credit" if order["customer_id"] else (order["payment_method"] or "cash")
        if method_key not in report.sales_by_method_piasters:
            method_key = "cash"
        report.sales_by_method_piasters[method_key] += order["total_piasters"]
        report.orders_by_method_count[method_key] += 1
        report.discount_total_piasters += order["discount_piasters"]
        report.order_count += 1

    report.void_count = len(orders_repo.list_voided_between(conn, start, end))

    entries = drawer_repo.list_entries(conn, start_utc=start, end_utc=end)
    report.expenses_cash_piasters = -sum(
        e["amount_delta_piasters"] for e in entries if e["entry_type"] == drawer_repo.TYPE_EXPENSE
    )

    report.opening_cash_piasters = shift["opening_cash_piasters"]
    report.expected_cash_piasters = shift["expected_cash_piasters"] or drawer_service.expected_cash_piasters(conn) or 0
    report.counted_cash_piasters = shift["counted_cash_piasters"]
    report.difference_piasters = shift["difference_piasters"]
    return report


def report_summary_text(report: ShiftReport) -> str:
    lines = [
        "مبيعات نقدي: {0} ({1} فاتورة)".format(format_egp(report.sales_by_method_piasters["cash"]), report.orders_by_method_count["cash"]),
        "مبيعات إنستاباي: {0} ({1} فاتورة)".format(format_egp(report.sales_by_method_piasters["instapay"]), report.orders_by_method_count["instapay"]),
        "مبيعات آجل: {0} ({1} فاتورة)".format(format_egp(report.sales_by_method_piasters["credit"]), report.orders_by_method_count["credit"]),
        "عدد الفواتير: {0}".format(report.order_count),
        "فواتير مبطلة: {0}".format(report.void_count),
        "إجمالي الخصومات: {0}".format(format_egp(report.discount_total_piasters)),
        "مصروفات نقدية: {0}".format(format_egp(report.expenses_cash_piasters)),
        "الكاش المتوقع: {0}".format(format_egp(report.expected_cash_piasters)),
    ]
    if report.counted_cash_piasters is not None:
        lines.append("الكاش المعدود: {0}".format(format_egp(report.counted_cash_piasters)))
        lines.append("الفرق: {0}".format(format_egp(report.difference_piasters or 0)))
    return "\n".join(lines)


def today_business_date(conn: sqlite3.Connection) -> str:
    return compute_business_date(utc_now(), _close_time_setting(conn)).isoformat()


def get_open_shift(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    return shifts_repo.get_open_shift(conn)


def open_shift(conn: sqlite3.Connection, requesting_user: sqlite3.Row, opening_cash_piasters: int) -> sqlite3.Row:
    if shifts_repo.get_open_shift(conn) is not None:
        raise ShiftAlreadyOpenError("a shift is already open")

    if drawer_service.has_open_drawer(conn):
        opening_cash_piasters = drawer_service.expected_cash_piasters(conn) or 0
    else:
        drawer_service.open_drawer(conn, opening_cash_piasters, requesting_user["id"])

    business_date = today_business_date(conn)
    shift_id = shifts_repo.create_shift(conn, requesting_user["id"], business_date, opening_cash_piasters)
    audit_service.log(
        conn, "shift_opened", user=requesting_user, entity_type="shift", entity_id=shift_id,
        summary_ar="فتح وردية برصيد افتتاحي {0}".format(format_egp(opening_cash_piasters)),
        details={"opening_cash_piasters": opening_cash_piasters},
    )
    bus.notify()
    return shifts_repo.get_shift(conn, shift_id)


def close_shift(
    conn: sqlite3.Connection,
    shift: sqlite3.Row,
    counted_cash_piasters: int,
    notes: Optional[str],
    requesting_user: sqlite3.Row,
    handed_over_to_user_id: Optional[int] = None,
    denominations: Optional[Dict[str, int]] = None,
) -> "tuple[sqlite3.Row, ShiftReport]":
    if shift["status"] != "open":
        raise NoOpenShiftError("shift {0} is not open".format(shift["id"]))

    drawer_service.record_count(conn, counted_cash_piasters, requesting_user["id"], denominations=denominations)
    expected = drawer_service.expected_cash_piasters(conn) or 0
    shifts_repo.close_shift(
        conn, shift["id"], counted_cash_piasters, expected, notes, handed_over_to_user_id=handed_over_to_user_id
    )
    closed_shift = shifts_repo.get_shift(conn, shift["id"])
    report = build_shift_report(conn, closed_shift)

    difference = report.difference_piasters or 0
    audit_service.log(
        conn, "shift_closed", user=requesting_user, entity_type="shift", entity_id=shift["id"],
        summary_ar="إغلاق وردية — فرق {0}".format(format_egp(difference)),
        details={
            "expected_cash_piasters": report.expected_cash_piasters, "counted_cash_piasters": counted_cash_piasters,
            "difference_piasters": difference, "order_count": report.order_count, "void_count": report.void_count,
        },
        severity=audit_service.SEVERITY_WARNING if difference != 0 else audit_service.SEVERITY_INFO,
    )
    bus.notify()
    return closed_shift, report


def handover_shift(
    conn: sqlite3.Connection,
    shift: sqlite3.Row,
    counted_cash_piasters: int,
    notes: Optional[str],
    requesting_user: sqlite3.Row,
    next_user: sqlite3.Row,
    denominations: Optional[Dict[str, int]] = None,
) -> "tuple[sqlite3.Row, ShiftReport, sqlite3.Row]":
    """Closes the current shift (counted = the SAME physical count used
    to open the next one -- no cash actually changes hands between the
    two steps) and opens a new one for `next_user` in one flow."""
    closed_shift, report = close_shift(
        conn, shift, counted_cash_piasters, notes, requesting_user, handed_over_to_user_id=next_user["id"],
        denominations=denominations,
    )
    new_shift = open_shift(conn, next_user, counted_cash_piasters)
    audit_service.log(
        conn, "shift_handover", user=requesting_user, entity_type="shift", entity_id=closed_shift["id"],
        summary_ar="تسليم وردية من {0} إلى {1}".format(requesting_user["name"], next_user["name"]),
        details={"from_user_id": requesting_user["id"], "to_user_id": next_user["id"], "new_shift_id": new_shift["id"]},
    )
    return closed_shift, report, new_shift
