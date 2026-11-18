"""Drives the real expenses UI widgets directly (no screenshots, no
exec_() blocking) -- same pattern as the Phase 3/4 GUI tests."""
from __future__ import annotations

from datetime import date

import pytest
from PySide2.QtWidgets import QDialog

from derby.core.db import expense_categories_repo, expenses_repo, recurring_expenses_repo, users_repo
from derby.features.expenses.expense_categories_panel import ExpenseCategoriesPanel
from derby.features.expenses.expense_dialog import ExpenseDialog
from derby.features.expenses.expenses_screen import ExpensesScreen
from derby.features.expenses.receipt_viewer_dialog import ReceiptViewerDialog
from derby.features.expenses.recurring_due_dialog import RecurringDueDialog
from derby.features.expenses.recurring_management_panel import RecurringManagementPanel


@pytest.fixture()
def owner(db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    return users_repo.get_user(db_conn, owner_id)


@pytest.fixture()
def category_id(db_conn):
    return expense_categories_repo.list_categories(db_conn)[0]["id"]


def test_expense_dialog_add_flow(qapp, db_conn, owner):
    dialog = ExpenseDialog(db_conn, owner)
    dialog._amount_input.setText("50")
    dialog._date_input.setText("2026-01-10")
    dialog._description_input.setText("فاتورة")
    dialog._on_add()
    assert dialog.result() == dialog.Accepted

    expenses = expenses_repo.list_expenses(db_conn)
    assert len(expenses) == 1
    assert expenses[0]["amount_piasters"] == 5000
    assert expenses[0]["description"] == "فاتورة"


def test_expense_dialog_add_rejects_invalid_amount(qapp, db_conn, owner):
    dialog = ExpenseDialog(db_conn, owner)
    dialog._amount_input.setText("0")
    dialog._date_input.setText("2026-01-10")
    dialog._on_add()
    assert dialog.result() != dialog.Accepted
    assert dialog._error_label.text() != ""


def test_expense_dialog_prefills_from_existing_for_replace(qapp, db_conn, owner, category_id):
    from derby.features.expenses import expenses_service

    expense = expenses_service.create_expense(db_conn, category_id, 2000, date(2026, 1, 10), "القديم", owner["id"])
    dialog = ExpenseDialog(db_conn, owner, existing_expense=expense)
    assert dialog._amount_input.text() == "20.00"
    assert dialog._date_input.text() == "2026-01-10"
    assert dialog._description_input.text() == "القديم"


def test_expense_dialog_replace_requires_reason(qapp, db_conn, owner, category_id):
    from derby.features.expenses import expenses_service

    expense = expenses_service.create_expense(db_conn, category_id, 2000, date(2026, 1, 10), "القديم", owner["id"])
    dialog = ExpenseDialog(db_conn, owner, existing_expense=expense)
    dialog._amount_input.setText("30")
    dialog._on_replace()  # no reason typed
    assert dialog.result() != dialog.Accepted


def test_expense_dialog_replace_succeeds_with_reason(qapp, db_conn, owner, category_id):
    from derby.features.expenses import expenses_service

    expense = expenses_service.create_expense(db_conn, category_id, 2000, date(2026, 1, 10), "القديم", owner["id"])
    dialog = ExpenseDialog(db_conn, owner, existing_expense=expense)
    dialog._amount_input.setText("30")
    dialog._reason_input.setText("تصحيح")
    dialog._on_replace()
    assert dialog.result() == dialog.Accepted

    old = expenses_repo.get_expense(db_conn, expense["id"])
    assert old["status"] == "void"


def test_expense_dialog_void_only(qapp, db_conn, owner, category_id):
    from derby.features.expenses import expenses_service

    expense = expenses_service.create_expense(db_conn, category_id, 2000, date(2026, 1, 10), "", owner["id"])
    dialog = ExpenseDialog(db_conn, owner, existing_expense=expense)
    dialog._reason_input.setText("غلط")
    dialog._on_void_only()
    assert dialog.result() == dialog.Accepted
    assert expenses_repo.get_expense(db_conn, expense["id"])["status"] == "void"


def test_expense_categories_panel_add_rename_toggle(qapp, db_conn, owner):
    panel = ExpenseCategoriesPanel(db_conn, owner)
    panel._new_name_input.setText("دعاية")
    panel._on_add()
    categories = expense_categories_repo.list_categories(db_conn)
    assert any(c["name"] == "دعاية" for c in categories)

    new_id = next(c["id"] for c in categories if c["name"] == "دعاية")
    row = next(i for i in range(panel._list.count()) if panel._list.item(i).data(1000) == new_id)
    panel._list.setCurrentRow(row)
    panel._rename_input.setText("دعاية وتسويق")
    panel._on_rename()
    assert expense_categories_repo.get_category(db_conn, new_id)["name"] == "دعاية وتسويق"

    panel._list.setCurrentRow(row)
    panel._on_toggle_active()
    assert expense_categories_repo.get_category(db_conn, new_id)["is_active"] == 0


def test_recurring_management_panel_add_and_edit(qapp, db_conn, owner, category_id):
    panel = RecurringManagementPanel(db_conn, owner)
    panel._name_input.setText("إيجار")
    panel._amount_input.setText("1000")
    panel._day_input.setText("5")
    panel._on_save()

    templates = recurring_expenses_repo.list_templates(db_conn)
    assert len(templates) == 1
    assert templates[0]["amount_piasters"] == 100000
    assert templates[0]["day_of_month"] == 5

    panel._list.setCurrentRow(0)
    panel._amount_input.setText("1200")
    panel._on_save()
    assert recurring_expenses_repo.get_template(db_conn, templates[0]["id"])["amount_piasters"] == 120000


def test_recurring_management_panel_rejects_bad_day(qapp, db_conn, owner):
    panel = RecurringManagementPanel(db_conn, owner)
    panel._name_input.setText("إيجار")
    panel._amount_input.setText("1000")
    panel._day_input.setText("40")
    panel._on_save()
    assert recurring_expenses_repo.list_templates(db_conn) == []
    assert panel._message_label.text() != ""


def test_recurring_due_dialog_confirm_creates_expense_and_closes(qapp, db_conn, owner, category_id):
    template_id = recurring_expenses_repo.create_template(db_conn, category_id, "إيجار", 100000, 5)
    dialog = RecurringDueDialog(db_conn, owner, date(2026, 1, 5))

    # Drive the first (only) row's confirm button directly.
    row_layout = dialog._rows_host.itemAt(0).layout()
    amount_input = row_layout.itemAt(1).widget()
    confirm_button = row_layout.itemAt(2).widget()
    amount_input.setText("950")
    confirm_button.click()

    assert dialog.result() == dialog.Accepted
    expenses = expenses_repo.list_expenses(db_conn)
    assert len(expenses) == 1
    assert expenses[0]["amount_piasters"] == 95000
    assert recurring_expenses_repo.get_template(db_conn, template_id)["last_generated_month"] == "2026-01"


def test_recurring_due_dialog_skip_closes_without_expense(qapp, db_conn, owner, category_id):
    recurring_expenses_repo.create_template(db_conn, category_id, "إيجار", 100000, 5)
    dialog = RecurringDueDialog(db_conn, owner, date(2026, 1, 5))

    row_layout = dialog._rows_host.itemAt(0).layout()
    skip_button = row_layout.itemAt(3).widget()
    skip_button.click()

    assert dialog.result() == dialog.Accepted
    assert expenses_repo.list_expenses(db_conn) == []


def test_receipt_viewer_dialog_with_no_receipt(qapp, db_conn):
    dialog = ReceiptViewerDialog(None)
    assert dialog is not None  # builds without crashing


def test_expenses_screen_shows_rows_and_month_total(qapp, db_conn, owner, category_id):
    from derby.features.expenses import expenses_service

    expenses_service.create_expense(db_conn, category_id, 5000, date(2026, 1, 10), "فاتورة", owner["id"])
    screen = ExpensesScreen(db_conn, owner)
    screen._month_input.setText("2026-01")
    screen.reload()

    assert screen._table.rowCount() == 1
    assert "50.00" in screen._totals_label.text()


def test_expenses_screen_category_filter(qapp, db_conn, owner):
    from derby.features.expenses import expenses_service

    categories = expense_categories_repo.list_categories(db_conn)
    expenses_service.create_expense(db_conn, categories[0]["id"], 5000, date(2026, 1, 10), "", owner["id"])
    expenses_service.create_expense(db_conn, categories[1]["id"], 3000, date(2026, 1, 11), "", owner["id"])

    screen = ExpensesScreen(db_conn, owner)
    screen._month_input.setText("2026-01")
    screen.reload()
    assert screen._table.rowCount() == 2

    index = screen._category_filter.findData(categories[0]["id"])
    screen._category_filter.setCurrentIndex(index)
    assert screen._table.rowCount() == 1


def test_expenses_screen_opens_recurring_due_prompt_automatically(qapp, db_conn, owner, category_id, monkeypatch):
    recurring_expenses_repo.create_template(db_conn, category_id, "إيجار", 100000, 1)
    opened = []
    monkeypatch.setattr(QDialog, "exec_", lambda self: opened.append(True) or QDialog.Accepted)

    ExpensesScreen(db_conn, owner)  # today's business date defaults to "now", template day=1 always due

    assert opened  # the due dialog was shown during __init__
