from __future__ import annotations

from derby.core.db.users_repo import ROLE_CASHIER, ROLE_OWNER
from derby.features.auth import permissions


def test_only_owner_manages_inventory():
    assert permissions.manage_inventory(ROLE_OWNER) is True
    assert permissions.manage_inventory(ROLE_CASHIER) is False


def test_both_roles_can_view_and_operate_the_drawer():
    assert permissions.view_drawer(ROLE_OWNER) is True
    assert permissions.view_drawer(ROLE_CASHIER) is True
    assert permissions.manage_drawer(ROLE_OWNER) is True
    assert permissions.manage_drawer(ROLE_CASHIER) is True


def test_only_owner_sees_goods_review_stock_value():
    assert permissions.view_goods_review(ROLE_OWNER) is True
    assert permissions.view_goods_review(ROLE_CASHIER) is False


def test_only_owner_sees_profit_report():
    assert permissions.view_profit_report(ROLE_OWNER) is True
    assert permissions.view_profit_report(ROLE_CASHIER) is False


def test_only_owner_sees_cost_data():
    assert permissions.view_cost_data(ROLE_OWNER) is True
    assert permissions.view_cost_data(ROLE_CASHIER) is False
