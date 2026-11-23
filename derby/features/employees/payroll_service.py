"""Advances/deductions/bonuses, the monthly payroll sheet, and "تسجيل
الدفع" -- which reuses the existing expenses service (new "مرتبات"
category, migration 0014) and the drawer ledger for a cash payment, so
a payroll payment is never double-counted against profit/cash: it is
an ordinary expense + an ordinary drawer entry, exactly like any other
cash outflow, just pre-filled from the payroll math.
"""
from __future__ import annotations

import calendar
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

from derby.core import audit_service
from derby.core.db import drawer_repo, employees_repo, expense_categories_repo, payroll_repo
from derby.core.utils.money import format_egp
from derby.features.employees.attendance_service import hours_for_period
from derby.features.expenses import expenses_service

PAYROLL_EXPENSE_CATEGORY_NAME = "مرتبات"


@dataclass
class PayrollSheetLine:
    employee: sqlite3.Row
    base_piasters: int
    bonuses_piasters: int = 0
    advances_piasters: int = 0
    deductions_piasters: int = 0
    bonus_line_ids: List[int] = field(default_factory=list)
    advance_line_ids: List[int] = field(default_factory=list)
    deduction_line_ids: List[int] = field(default_factory=list)

    @property
    def net_piasters(self) -> int:
        return self.base_piasters + self.bonuses_piasters - self.advances_piasters - self.deductions_piasters


def add_advance(conn: sqlite3.Connection, employee_id: int, amount_piasters: int, line_date: date, note: Optional[str], user: sqlite3.Row) -> sqlite3.Row:
    return _add_line(conn, employee_id, payroll_repo.KIND_ADVANCE, amount_piasters, line_date, note, user, "payroll_advance", "تسجيل سلفة")


def add_deduction(conn: sqlite3.Connection, employee_id: int, amount_piasters: int, line_date: date, note: Optional[str], user: sqlite3.Row) -> sqlite3.Row:
    return _add_line(conn, employee_id, payroll_repo.KIND_DEDUCTION, amount_piasters, line_date, note, user, "payroll_deduction", "تسجيل استقطاع")


def add_bonus(conn: sqlite3.Connection, employee_id: int, amount_piasters: int, line_date: date, note: Optional[str], user: sqlite3.Row) -> sqlite3.Row:
    return _add_line(conn, employee_id, payroll_repo.KIND_BONUS, amount_piasters, line_date, note, user, "payroll_bonus", "تسجيل حافز")


def _add_line(conn, employee_id, kind, amount_piasters, line_date, note, user, action, summary_verb) -> sqlite3.Row:
    if amount_piasters <= 0:
        raise ValueError("amount must be positive")
    line_id = payroll_repo.add_line(conn, employee_id, kind, amount_piasters, line_date.isoformat(), note, user["id"])
    audit_service.log(
        conn, action, user=user, entity_type="employee", entity_id=employee_id,
        summary_ar="{0}: {1}".format(summary_verb, format_egp(amount_piasters)),
        details={"amount_piasters": amount_piasters, "note": note},
    )
    return conn.execute("SELECT * FROM payroll_lines WHERE id = ?", (line_id,)).fetchone()


def build_sheet_line(conn: sqlite3.Connection, employee: sqlite3.Row, year: int, month: int) -> PayrollSheetLine:
    month_end = date(year, month, calendar.monthrange(year, month)[1])
    month_start = date(year, month, 1)

    if employee["pay_type"] == employees_repo.PAY_TYPE_DAILY:
        worked_hours = hours_for_period(conn, employee["id"], month_start.isoformat(), month_end.isoformat())
        worked_days = worked_hours / 8.0  # a standard 8h day -- the only reasonable default without a configurable shift length
        base_piasters = int(round(worked_days * employee["base_amount_piasters"]))
    else:
        base_piasters = employee["base_amount_piasters"]

    line = PayrollSheetLine(employee=employee, base_piasters=base_piasters)
    for row in payroll_repo.list_unapplied_lines(conn, employee["id"], month_end.isoformat()):
        if row["kind"] == payroll_repo.KIND_BONUS:
            line.bonuses_piasters += row["amount_piasters"]
            line.bonus_line_ids.append(row["id"])
        elif row["kind"] == payroll_repo.KIND_ADVANCE:
            line.advances_piasters += row["amount_piasters"]
            line.advance_line_ids.append(row["id"])
        elif row["kind"] == payroll_repo.KIND_DEDUCTION:
            line.deductions_piasters += row["amount_piasters"]
            line.deduction_line_ids.append(row["id"])
    return line


def build_month_sheet(conn: sqlite3.Connection, year: int, month: int) -> List[PayrollSheetLine]:
    return [build_sheet_line(conn, employee, year, month) for employee in employees_repo.list_employees(conn, active_only=True)]


def _payroll_category_id(conn: sqlite3.Connection) -> int:
    for category in expense_categories_repo.list_categories(conn):
        if category["name"] == PAYROLL_EXPENSE_CATEGORY_NAME:
            return category["id"]
    raise RuntimeError("payroll expense category is missing -- migration 0014 should have created it")


def record_payment(
    conn: sqlite3.Connection,
    line: PayrollSheetLine,
    year: int,
    month: int,
    payment_method: str,
    requesting_user: sqlite3.Row,
) -> sqlite3.Row:
    """"تسجيل الدفع": files an ordinary expense (مرتبات) for the net
    amount -- the SAME path every other expense goes through, so it
    shows up in reports/profit exactly like any other cost, with no
    separate payroll bookkeeping to keep in sync. A cash payment also
    gets the drawer entry that expenses_service.create_expense always
    creates for a cash expense; nothing extra is needed here for that.
    """
    year_month = "{0:04d}-{1:02d}".format(year, month)
    category_id = _payroll_category_id(conn)
    description = "مرتب {0} — {1}".format(line.employee["name"], year_month)

    # Paying before the month's last calendar day (common -- salaries are
    # often paid a day or two early) must never be rejected as "a future
    # expense date"; clamp to today's business date, never past it.
    month_end = date(year, month, calendar.monthrange(year, month)[1])
    expense_date = min(month_end, expenses_service.today_business_date(conn))

    expense = expenses_service.create_expense(
        conn, category_id, line.net_piasters, expense_date, description, requesting_user["id"],
    )
    # expenses_service always records a CASH drawer entry -- correct only
    # when payment_method is cash; an InstaPay payroll payment must not
    # leave a phantom cash outflow in the drawer, so it is reversed right
    # back out (a new append-only entry, never editing the one just made).
    if payment_method != "cash":
        drawer_repo.create_entry(
            conn, drawer_repo.TYPE_EXPENSE, line.net_piasters, ref_type="expense", ref_id=expense["id"],
            user_id=requesting_user["id"], note="مرتب مدفوع إنستاباي -- لا يخص الدرج", commit=True,
        )

    payment_id = payroll_repo.create_payment(
        conn, line.employee["id"], year_month, line.base_piasters, line.bonuses_piasters, line.advances_piasters,
        line.deductions_piasters, line.net_piasters, payment_method, expense["id"], requesting_user["id"],
    )
    payroll_repo.mark_lines_applied(conn, line.bonus_line_ids + line.advance_line_ids + line.deduction_line_ids, payment_id)

    audit_service.log(
        conn, "payroll_paid", user=requesting_user, entity_type="employee", entity_id=line.employee["id"],
        summary_ar="دفع مرتب {0} لشهر {1}: {2}".format(line.employee["name"], year_month, format_egp(line.net_piasters)),
        details={
            "year_month": year_month, "base_piasters": line.base_piasters, "bonuses_piasters": line.bonuses_piasters,
            "advances_piasters": line.advances_piasters, "deductions_piasters": line.deductions_piasters,
            "net_piasters": line.net_piasters, "payment_method": payment_method, "expense_id": expense["id"],
        },
    )
    return payroll_repo.get_payment(conn, payment_id)
