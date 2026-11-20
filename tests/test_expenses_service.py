from __future__ import annotations

from datetime import date, timedelta

import pytest

from derby.core.db import expense_categories_repo, expenses_repo, recurring_expenses_repo, users_repo
from derby.features.expenses import expenses_service
from derby.features.expenses.exceptions import FutureDateError, InvalidAmountError, VoidReasonRequiredError


@pytest.fixture()
def owner_id(db_conn):
    return users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")


@pytest.fixture()
def category_id(db_conn):
    return expense_categories_repo.list_categories(db_conn)[0]["id"]


def test_migration_seeds_six_categories(db_conn):
    categories = expense_categories_repo.list_categories(db_conn)
    assert [c["name"] for c in categories] == ["إيجار", "كهرباء", "مياه", "صيانة", "أدوات شغل", "أخرى"]


def test_create_expense(db_conn, owner_id, category_id):
    expense = expenses_service.create_expense(db_conn, category_id, 5000, date(2026, 1, 10), "فاتورة", owner_id)
    assert expense["status"] == "active"
    assert expense["amount_piasters"] == 5000
    assert expense["expense_date"] == "2026-01-10"


def test_create_expense_rejects_non_positive_amount(db_conn, owner_id, category_id):
    with pytest.raises(InvalidAmountError):
        expenses_service.create_expense(db_conn, category_id, 0, date(2026, 1, 10), "", owner_id)
    with pytest.raises(InvalidAmountError):
        expenses_service.create_expense(db_conn, category_id, -100, date(2026, 1, 10), "", owner_id)


def test_create_expense_rejects_future_date(db_conn, owner_id, category_id):
    future = expenses_service.today_business_date(db_conn) + timedelta(days=1)
    with pytest.raises(FutureDateError):
        expenses_service.create_expense(db_conn, category_id, 100, future, "", owner_id)


def test_void_expense_requires_reason(db_conn, owner_id, category_id):
    expense = expenses_service.create_expense(db_conn, category_id, 5000, date(2026, 1, 10), "", owner_id)
    with pytest.raises(VoidReasonRequiredError):
        expenses_service.void_expense(db_conn, expense["id"], "", owner_id)


def test_void_expense(db_conn, owner_id, category_id):
    expense = expenses_service.create_expense(db_conn, category_id, 5000, date(2026, 1, 10), "", owner_id)
    voided = expenses_service.void_expense(db_conn, expense["id"], "غلط", owner_id)
    assert voided["status"] == "void"
    assert voided["void_reason"] == "غلط"
    assert voided["replaced_by_id"] is None


def test_replace_expense_is_atomic_and_linked(db_conn, owner_id, category_id):
    expense = expenses_service.create_expense(db_conn, category_id, 5000, date(2026, 1, 10), "القديم", owner_id)
    replacement = expenses_service.replace_expense(
        db_conn, expense["id"], "تصحيح المبلغ", category_id, 7500, date(2026, 1, 10), "الجديد", owner_id
    )
    old = expenses_repo.get_expense(db_conn, expense["id"])
    assert old["status"] == "void"
    assert old["replaced_by_id"] == replacement["id"]
    assert replacement["status"] == "active"
    assert replacement["amount_piasters"] == 7500


def test_totals_ignore_voided_expenses(db_conn, owner_id, category_id):
    e1 = expenses_service.create_expense(db_conn, category_id, 5000, date(2026, 1, 10), "", owner_id)
    expenses_service.create_expense(db_conn, category_id, 3000, date(2026, 1, 11), "", owner_id)
    expenses_service.void_expense(db_conn, e1["id"], "غلط", owner_id)

    active = expenses_repo.list_expenses(db_conn, start_date="2026-01-01", end_date="2026-01-31", status="active")
    assert sum(e["amount_piasters"] for e in active) == 3000


def test_audit_log_entries_for_create_void_replace(db_conn, owner_id, category_id):
    expense = expenses_service.create_expense(db_conn, category_id, 5000, date(2026, 1, 10), "", owner_id)
    expenses_service.replace_expense(db_conn, expense["id"], "سبب", category_id, 6000, date(2026, 1, 10), "", owner_id)

    actions = [row["action"] for row in db_conn.execute("SELECT action FROM audit_log ORDER BY id")]
    assert "expense_created" in actions
    assert "expense_replaced" in actions


# --- recurring templates -----------------------------------------------------


def test_due_day_clamped_for_short_month():
    assert expenses_service.due_day_for_month(31, 2026, 2) == 28  # 2026 is not a leap year
    assert expenses_service.due_day_for_month(31, 2024, 2) == 29  # 2024 is a leap year
    assert expenses_service.due_day_for_month(31, 2026, 1) == 31


def test_due_templates_for_month(db_conn, category_id):
    template_id = recurring_expenses_repo.create_template(db_conn, category_id, "إيجار", 100000, 5)
    assert expenses_service.due_templates_for_month(db_conn, date(2026, 1, 4)) == []
    due = expenses_service.due_templates_for_month(db_conn, date(2026, 1, 5))
    assert [t["id"] for t in due] == [template_id]


def test_due_day_31_clamped_in_february_triggers_on_28th(db_conn, category_id):
    recurring_expenses_repo.create_template(db_conn, category_id, "اشتراك", 10000, 31)
    assert expenses_service.due_templates_for_month(db_conn, date(2026, 2, 27)) == []
    due = expenses_service.due_templates_for_month(db_conn, date(2026, 2, 28))
    assert len(due) == 1


def test_confirm_recurring_creates_expense_and_sets_last_generated_month(db_conn, owner_id, category_id):
    template = recurring_expenses_repo.create_template(db_conn, category_id, "إيجار", 100000, 5)
    expense = expenses_service.confirm_recurring(db_conn, template, 95000, date(2026, 1, 5), owner_id)
    assert expense["amount_piasters"] == 95000  # amount was editable
    assert expense["recurring_id"] == template

    reloaded_template = recurring_expenses_repo.get_template(db_conn, template)
    assert reloaded_template["last_generated_month"] == "2026-01"


def test_no_double_prompt_in_the_same_month_after_confirm(db_conn, owner_id, category_id):
    template = recurring_expenses_repo.create_template(db_conn, category_id, "إيجار", 100000, 5)
    expenses_service.confirm_recurring(db_conn, template, 100000, date(2026, 1, 5), owner_id)
    assert expenses_service.due_templates_for_month(db_conn, date(2026, 1, 20)) == []


def test_skip_recurring_prevents_reprompt_without_creating_expense(db_conn, owner_id, category_id):
    template = recurring_expenses_repo.create_template(db_conn, category_id, "إيجار", 100000, 5)
    expenses_service.skip_recurring(db_conn, template, date(2026, 1, 5), owner_id)

    assert expenses_service.due_templates_for_month(db_conn, date(2026, 1, 20)) == []
    assert expenses_repo.list_expenses(db_conn) == []


def test_due_again_next_month_after_skip(db_conn, owner_id, category_id):
    template = recurring_expenses_repo.create_template(db_conn, category_id, "إيجار", 100000, 5)
    expenses_service.skip_recurring(db_conn, template, date(2026, 1, 5), owner_id)
    due = expenses_service.due_templates_for_month(db_conn, date(2026, 2, 5))
    assert len(due) == 1


def test_recurring_template_changes_are_audited(db_conn, owner_id, category_id):
    template = expenses_service.add_recurring_template(db_conn, category_id, "إيجار", 100000, 5, owner_id)
    expenses_service.update_recurring_template(db_conn, template["id"], category_id, "إيجار", 120000, 5, owner_id)
    actions = [row["action"] for row in db_conn.execute("SELECT action FROM audit_log ORDER BY id")]
    assert actions.count("recurring_template_changed") == 2


# --- categories ---------------------------------------------------------


def test_disabling_category_in_use_is_allowed(db_conn, owner_id, category_id):
    expenses_service.create_expense(db_conn, category_id, 5000, date(2026, 1, 10), "", owner_id)
    expenses_service.set_category_active(db_conn, category_id, False, owner_id)
    category = expense_categories_repo.get_category(db_conn, category_id)
    assert category["is_active"] == 0
    # The existing expense still points at it and is unaffected.
    expenses = expenses_repo.list_expenses(db_conn)
    assert expenses[0]["category_id"] == category_id
