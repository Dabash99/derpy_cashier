from __future__ import annotations

import pytest

from derby.core.db import expenses_repo, users_repo
from derby.features.pos.exceptions import PermissionDeniedError
from derby.features.supplies import supplies_service
from derby.features.supplies.exceptions import InvalidCostError, SupplyNameRequiredError, SupplyNotBoughtError


@pytest.fixture()
def owner(db_conn):
    user_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    return users_repo.get_user(db_conn, user_id)


@pytest.fixture()
def cashier(db_conn):
    user_id = users_repo.create_user(db_conn, "Cashier", users_repo.ROLE_CASHIER, "2222")
    return users_repo.get_user(db_conn, user_id)


def test_add_supply_requires_a_name(db_conn, owner):
    with pytest.raises(SupplyNameRequiredError):
        supplies_service.add_supply(db_conn, "   ", None, supplies_service.PRIORITY_NORMAL, None, owner["id"])


def _audit_actions(db_conn):
    return [row["action"] for row in db_conn.execute("SELECT action FROM audit_log").fetchall()]


def test_add_supply_logs_audit_entry(db_conn, owner):
    supply = supplies_service.add_supply(db_conn, "سكر", "كيلو", supplies_service.PRIORITY_NORMAL, None, owner["id"])
    assert "supply_added" in _audit_actions(db_conn)
    assert supply["status"] == supplies_service.STATUS_NEEDED


def test_mark_bought_then_cancel(db_conn, owner):
    supply = supplies_service.add_supply(db_conn, "سكر", None, supplies_service.PRIORITY_NORMAL, None, owner["id"])
    bought = supplies_service.mark_bought(db_conn, supply["id"], owner["id"])
    assert bought["status"] == supplies_service.STATUS_BOUGHT
    assert bought["bought_by"] == owner["id"]

    supply2 = supplies_service.add_supply(db_conn, "شاي", None, supplies_service.PRIORITY_NORMAL, None, owner["id"])
    dropped = supplies_service.cancel_supply(db_conn, supply2["id"], owner["id"])
    assert dropped["status"] == supplies_service.STATUS_DROPPED


def test_convert_to_expense_requires_bought_status(db_conn, owner):
    supply = supplies_service.add_supply(db_conn, "سكر", None, supplies_service.PRIORITY_NORMAL, None, owner["id"])
    with pytest.raises(SupplyNotBoughtError):
        supplies_service.convert_to_expense(db_conn, supply["id"], category_id=1, cost_piasters=500, requesting_user=owner)


def test_convert_to_expense_rejects_non_owner(db_conn, owner, cashier):
    supply = supplies_service.add_supply(db_conn, "سكر", None, supplies_service.PRIORITY_NORMAL, None, owner["id"])
    supplies_service.mark_bought(db_conn, supply["id"], cashier["id"])
    with pytest.raises(PermissionDeniedError):
        supplies_service.convert_to_expense(db_conn, supply["id"], category_id=1, cost_piasters=500, requesting_user=cashier)


def test_convert_to_expense_rejects_non_positive_cost(db_conn, owner):
    supply = supplies_service.add_supply(db_conn, "سكر", None, supplies_service.PRIORITY_NORMAL, None, owner["id"])
    supplies_service.mark_bought(db_conn, supply["id"], owner["id"])
    with pytest.raises(InvalidCostError):
        supplies_service.convert_to_expense(db_conn, supply["id"], category_id=1, cost_piasters=0, requesting_user=owner)


def test_convert_to_expense_creates_linked_expense(db_conn, owner):
    category_id = 5  # "أدوات شغل" per the seeded expense_categories in migration 5
    supply = supplies_service.add_supply(db_conn, "فناجين", "٢٤ قطعة", supplies_service.PRIORITY_NORMAL, None, owner["id"])
    supplies_service.mark_bought(db_conn, supply["id"], owner["id"])

    result = supplies_service.convert_to_expense(db_conn, supply["id"], category_id, 2500, owner)

    assert result["cost_piasters"] == 2500
    assert result["expense_id"] is not None
    expense = expenses_repo.get_expense(db_conn, result["expense_id"])
    assert expense["amount_piasters"] == 2500
    assert expense["category_id"] == category_id
    assert expense["description"] == "فناجين"

    assert "supply_converted_to_expense" in _audit_actions(db_conn)


def test_copy_list_as_text_lists_only_needed_urgent_first(db_conn, owner):
    supplies_service.add_supply(db_conn, "أكياس", None, supplies_service.PRIORITY_NORMAL, None, owner["id"])
    supplies_service.add_supply(db_conn, "حليب", "٢ لتر", supplies_service.PRIORITY_URGENT, None, owner["id"])
    bought = supplies_service.add_supply(db_conn, "شاي", None, supplies_service.PRIORITY_NORMAL, None, owner["id"])
    supplies_service.mark_bought(db_conn, bought["id"], owner["id"])

    text = supplies_service.copy_list_as_text(db_conn)
    lines = text.splitlines()
    assert len(lines) == 2
    assert "حليب" in lines[0] and supplies_service.PRIORITY_URGENT in lines[0]
    assert "أكياس" in lines[1]
    assert "شاي" not in text
