"""Expense business logic: creating/voiding+replacing expenses, the
recurring-template "due this month" prompt, and category management --
all with audit logging. No UI code here, same split as orders_service.py.
"""
from __future__ import annotations

import calendar
import sqlite3
from datetime import date
from datetime import time as time_of_day
from pathlib import Path
from typing import List, Optional

from derby.core.db import (
    audit_repo,
    drawer_repo,
    expense_categories_repo,
    expenses_repo,
    recurring_expenses_repo,
    settings_repo,
)
from derby.core.utils.business_date import business_date as compute_business_date
from derby.core.utils.time_utils import utc_now
from derby.features.expenses import receipts
from derby.features.expenses.exceptions import (
    FutureDateError,
    InvalidAmountError,
    InvalidReceiptImageError,
    VoidReasonRequiredError,
)


def today_business_date(conn: sqlite3.Connection) -> date:
    close_time_text = settings_repo.get(conn, "business_close_time", "23:59") or "23:59"
    hour_str, minute_str = close_time_text.split(":")
    close_time = time_of_day(int(hour_str), int(minute_str))
    return compute_business_date(utc_now(), close_time)


def _save_receipt_or_raise(receipt_source_path: Optional[Path]) -> Optional[str]:
    if receipt_source_path is None:
        return None
    try:
        return receipts.save_receipt_image(receipt_source_path)
    except receipts.InvalidImageError as error:
        raise InvalidReceiptImageError(str(error))


def create_expense(
    conn: sqlite3.Connection,
    category_id: int,
    amount_piasters: int,
    expense_date: date,
    description: Optional[str],
    user_id: int,
    receipt_source_path: Optional[Path] = None,
    recurring_id: Optional[int] = None,
) -> sqlite3.Row:
    if amount_piasters <= 0:
        raise InvalidAmountError("amount must be greater than zero")
    if expense_date > today_business_date(conn):
        raise FutureDateError("expense_date cannot be in the future")

    receipt_file = _save_receipt_or_raise(receipt_source_path)
    try:
        expense_id = expenses_repo.create_expense(
            conn, category_id, amount_piasters, expense_date.isoformat(), description, user_id,
            receipt_file=receipt_file, recurring_id=recurring_id, commit=False,
        )
        # Every expense entered through this screen is assumed paid in
        # cash from the drawer -- a purchase's own auto-filed expense
        # (stock_service._file_purchase_expense) bypasses this function
        # and records its own drawer_entries row instead, so purchases
        # are never double-counted here.
        drawer_repo.create_entry(
            conn, drawer_repo.TYPE_EXPENSE, -amount_piasters, ref_type="expense", ref_id=expense_id, user_id=user_id, commit=False
        )
        audit_repo.log(
            conn, "expense_created", user_id=user_id,
            details="expense={0} category={1} amount={2}".format(expense_id, category_id, amount_piasters),
        )
    except Exception:
        conn.rollback()
        raise
    return expenses_repo.get_expense(conn, expense_id)


def void_expense(conn: sqlite3.Connection, expense_id: int, reason: str, user_id: int) -> sqlite3.Row:
    """Voids without a replacement -- a straightforward cancellation."""
    reason = (reason or "").strip()
    if not reason:
        raise VoidReasonRequiredError("a reason is required")
    expense = expenses_repo.get_expense(conn, expense_id)
    try:
        expenses_repo.void_expense(conn, expense_id, user_id, reason, commit=False)
        # The ledger is append-only (see drawer_repo) -- voiding never
        # edits/removes the original drawer_entries row, it adds a
        # reversing one so expected cash is corrected going forward.
        drawer_repo.create_entry(
            conn, drawer_repo.TYPE_EXPENSE, expense["amount_piasters"], ref_type="expense", ref_id=expense_id,
            user_id=user_id, note="عكس: {0}".format(reason), commit=False,
        )
        audit_repo.log(conn, "expense_voided", user_id=user_id, details="expense={0} reason={1}".format(expense_id, reason))
    except Exception:
        conn.rollback()
        raise
    return expenses_repo.get_expense(conn, expense_id)


def replace_expense(
    conn: sqlite3.Connection,
    expense_id: int,
    reason: str,
    category_id: int,
    amount_piasters: int,
    expense_date: date,
    description: Optional[str],
    user_id: int,
    receipt_source_path: Optional[Path] = None,
) -> sqlite3.Row:
    """"Edit" = void the old row (reason required) + insert a replacement
    linked via replaced_by_id, atomically."""
    reason = (reason or "").strip()
    if not reason:
        raise VoidReasonRequiredError("a reason is required")
    if amount_piasters <= 0:
        raise InvalidAmountError("amount must be greater than zero")
    if expense_date > today_business_date(conn):
        raise FutureDateError("expense_date cannot be in the future")

    old_expense = expenses_repo.get_expense(conn, expense_id)
    receipt_file = _save_receipt_or_raise(receipt_source_path)
    try:
        new_id = expenses_repo.create_expense(
            conn, category_id, amount_piasters, expense_date.isoformat(), description, user_id,
            receipt_file=receipt_file, recurring_id=old_expense["recurring_id"], commit=False,
        )
        drawer_repo.create_entry(
            conn, drawer_repo.TYPE_EXPENSE, -amount_piasters, ref_type="expense", ref_id=new_id, user_id=user_id, commit=False
        )
        expenses_repo.void_expense(conn, expense_id, user_id, reason, replaced_by_id=new_id, commit=False)
        drawer_repo.create_entry(
            conn, drawer_repo.TYPE_EXPENSE, old_expense["amount_piasters"], ref_type="expense", ref_id=expense_id,
            user_id=user_id, note="عكس: {0}".format(reason), commit=False,
        )
        audit_repo.log(
            conn, "expense_replaced", user_id=user_id,
            details="old_expense={0} new_expense={1} old_amount={2} new_amount={3} reason={4}".format(
                expense_id, new_id, old_expense["amount_piasters"], amount_piasters, reason
            ),
        )
    except Exception:
        conn.rollback()
        raise
    return expenses_repo.get_expense(conn, new_id)


# --- recurring templates -----------------------------------------------------


def due_day_for_month(day_of_month: int, year: int, month: int) -> int:
    """Clamps a template's day_of_month to the month's actual last day
    (e.g. day 31 in February becomes 28 or 29)."""
    last_day = calendar.monthrange(year, month)[1]
    return min(day_of_month, last_day)


def due_templates_for_month(conn: sqlite3.Connection, today: date) -> List[sqlite3.Row]:
    """Active templates whose (clamped) day has arrived this month and
    that have no expense generated for this month yet."""
    year_month = "{0:04d}-{1:02d}".format(today.year, today.month)
    due = []
    for template in recurring_expenses_repo.list_templates(conn, active_only=True):
        if template["last_generated_month"] == year_month:
            continue
        due_day = due_day_for_month(template["day_of_month"], today.year, today.month)
        if today.day >= due_day:
            due.append(template)
    return due


def confirm_recurring(
    conn: sqlite3.Connection, template_id: int, amount_piasters: int, expense_date: date, user_id: int
) -> sqlite3.Row:
    """The owner confirmed a due template (amount is editable -- bills vary)."""
    template = recurring_expenses_repo.get_template(conn, template_id)
    year_month = "{0:04d}-{1:02d}".format(expense_date.year, expense_date.month)
    expense = create_expense(
        conn, template["category_id"], amount_piasters, expense_date, template["name"], user_id,
        recurring_id=template_id,
    )
    recurring_expenses_repo.set_last_generated_month(conn, template_id, year_month)
    return expense


def skip_recurring(conn: sqlite3.Connection, template_id: int, today: date, user_id: int) -> None:
    year_month = "{0:04d}-{1:02d}".format(today.year, today.month)
    recurring_expenses_repo.set_last_generated_month(conn, template_id, year_month)
    audit_repo.log(conn, "recurring_skipped", user_id=user_id, details="template={0} month={1}".format(template_id, year_month))


def add_recurring_template(
    conn: sqlite3.Connection, category_id: int, name: str, amount_piasters: int, day_of_month: int, user_id: int
) -> sqlite3.Row:
    if amount_piasters <= 0:
        raise InvalidAmountError("amount must be greater than zero")
    template_id = recurring_expenses_repo.create_template(conn, category_id, name, amount_piasters, day_of_month)
    audit_repo.log(
        conn, "recurring_template_changed", user_id=user_id,
        details="template={0} created name={1} amount={2} day={3}".format(template_id, name, amount_piasters, day_of_month),
    )
    return recurring_expenses_repo.get_template(conn, template_id)


def update_recurring_template(
    conn: sqlite3.Connection,
    template_id: int,
    category_id: int,
    name: str,
    amount_piasters: int,
    day_of_month: int,
    user_id: int,
) -> sqlite3.Row:
    if amount_piasters <= 0:
        raise InvalidAmountError("amount must be greater than zero")
    old = recurring_expenses_repo.get_template(conn, template_id)
    recurring_expenses_repo.update_template(conn, template_id, category_id, name, amount_piasters, day_of_month)
    audit_repo.log(
        conn, "recurring_template_changed", user_id=user_id,
        details="template={0} amount {1}->{2}".format(template_id, old["amount_piasters"], amount_piasters),
    )
    return recurring_expenses_repo.get_template(conn, template_id)


def set_recurring_active(conn: sqlite3.Connection, template_id: int, is_active: bool, user_id: int) -> None:
    recurring_expenses_repo.set_active(conn, template_id, is_active)
    audit_repo.log(
        conn, "recurring_template_changed", user_id=user_id,
        details="template={0} is_active={1}".format(template_id, is_active),
    )


# --- expense categories (disabling one in use is allowed; it only hides
# it from new entries, past expenses keep showing it normally) -------------


def add_category(conn: sqlite3.Connection, name: str, user_id: int) -> sqlite3.Row:
    category_id = expense_categories_repo.create_category(conn, name)
    audit_repo.log(conn, "expense_category_changed", user_id=user_id, details="category={0} created name={1}".format(category_id, name))
    return expense_categories_repo.get_category(conn, category_id)


def rename_category(conn: sqlite3.Connection, category_id: int, new_name: str, user_id: int) -> None:
    expense_categories_repo.rename_category(conn, category_id, new_name)
    audit_repo.log(conn, "expense_category_changed", user_id=user_id, details="category={0} renamed to {1}".format(category_id, new_name))


def set_category_active(conn: sqlite3.Connection, category_id: int, is_active: bool, user_id: int) -> None:
    expense_categories_repo.set_active(conn, category_id, is_active)
    audit_repo.log(
        conn, "expense_category_changed", user_id=user_id, details="category={0} is_active={1}".format(category_id, is_active)
    )


def move_category(conn: sqlite3.Connection, category_id: int, direction: int, user_id: int) -> None:
    expense_categories_repo.move_category(conn, category_id, direction)
