from __future__ import annotations

import pytest

from derby.core.db import expenses_repo, supplies_repo, users_repo


@pytest.fixture()
def owner(db_conn):
    user_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    return users_repo.get_user(db_conn, user_id)


def test_create_and_get_supply(db_conn, owner):
    supply_id = supplies_repo.create_supply(
        db_conn, "سكر", "كيلو", supplies_repo.PRIORITY_NORMAL, None, owner["id"]
    )
    supply = supplies_repo.get_supply(db_conn, supply_id)
    assert supply["name"] == "سكر"
    assert supply["status"] == supplies_repo.STATUS_NEEDED
    assert supply["added_by"] == owner["id"]


def test_list_supplies_urgent_first(db_conn, owner):
    supplies_repo.create_supply(db_conn, "أكياس", None, supplies_repo.PRIORITY_NORMAL, None, owner["id"])
    urgent_id = supplies_repo.create_supply(db_conn, "حليب", None, supplies_repo.PRIORITY_URGENT, None, owner["id"])

    rows = supplies_repo.list_supplies(db_conn, status=supplies_repo.STATUS_NEEDED)
    assert rows[0]["id"] == urgent_id


def test_list_supplies_filters_by_status(db_conn, owner):
    needed_id = supplies_repo.create_supply(db_conn, "سكر", None, supplies_repo.PRIORITY_NORMAL, None, owner["id"])
    bought_id = supplies_repo.create_supply(db_conn, "شاي", None, supplies_repo.PRIORITY_NORMAL, None, owner["id"])
    supplies_repo.mark_bought(db_conn, bought_id, owner["id"])

    needed = [row["id"] for row in supplies_repo.list_supplies(db_conn, status=supplies_repo.STATUS_NEEDED)]
    bought = [row["id"] for row in supplies_repo.list_supplies(db_conn, status=supplies_repo.STATUS_BOUGHT)]
    assert needed == [needed_id]
    assert bought == [bought_id]


def test_mark_dropped(db_conn, owner):
    supply_id = supplies_repo.create_supply(db_conn, "سكر", None, supplies_repo.PRIORITY_NORMAL, None, owner["id"])
    supplies_repo.mark_dropped(db_conn, supply_id)
    assert supplies_repo.get_supply(db_conn, supply_id)["status"] == supplies_repo.STATUS_DROPPED


def test_update_supply(db_conn, owner):
    supply_id = supplies_repo.create_supply(db_conn, "سكر", None, supplies_repo.PRIORITY_NORMAL, None, owner["id"])
    supplies_repo.update_supply(db_conn, supply_id, "سكر أبيض", "٢ كيلو", supplies_repo.PRIORITY_URGENT, "ملاحظة")
    supply = supplies_repo.get_supply(db_conn, supply_id)
    assert supply["name"] == "سكر أبيض"
    assert supply["quantity_note"] == "٢ كيلو"
    assert supply["priority"] == supplies_repo.PRIORITY_URGENT
    assert supply["note"] == "ملاحظة"


def test_set_cost_and_expense(db_conn, owner):
    supply_id = supplies_repo.create_supply(db_conn, "سكر", None, supplies_repo.PRIORITY_NORMAL, None, owner["id"])
    supplies_repo.mark_bought(db_conn, supply_id, owner["id"])
    expense_id = expenses_repo.create_expense(db_conn, 1, 1500, "2024-01-01", "سكر", owner["id"])

    supplies_repo.set_cost_and_expense(db_conn, supply_id, 1500, expense_id=expense_id)

    supply = supplies_repo.get_supply(db_conn, supply_id)
    assert supply["cost_piasters"] == 1500
    assert supply["expense_id"] == expense_id
