from __future__ import annotations

from derby.core.db.users_repo import ROLE_CASHIER, ROLE_OWNER
from derby.features.auth.permissions import (
    apply_discount_direct,
    manage_ps_devices,
    manage_tables,
    use_pos,
    use_ps,
    view_sales_all_dates,
    view_sales_today,
    view_tables,
    void_paid_order,
)


def test_both_roles_use_pos_and_view_tables():
    assert use_pos(ROLE_OWNER) is True
    assert use_pos(ROLE_CASHIER) is True
    assert view_tables(ROLE_OWNER) is True
    assert view_tables(ROLE_CASHIER) is True


def test_only_owner_manages_tables():
    assert manage_tables(ROLE_OWNER) is True
    assert manage_tables(ROLE_CASHIER) is False


def test_only_owner_applies_discount_directly():
    assert apply_discount_direct(ROLE_OWNER) is True
    assert apply_discount_direct(ROLE_CASHIER) is False


def test_only_owner_voids_paid_orders():
    assert void_paid_order(ROLE_OWNER) is True
    assert void_paid_order(ROLE_CASHIER) is False


def test_both_roles_view_sales_today_but_only_owner_sees_all_dates():
    assert view_sales_today(ROLE_OWNER) is True
    assert view_sales_today(ROLE_CASHIER) is True
    assert view_sales_all_dates(ROLE_OWNER) is True
    assert view_sales_all_dates(ROLE_CASHIER) is False


def test_both_roles_use_ps_but_only_owner_manages_devices():
    assert use_ps(ROLE_OWNER) is True
    assert use_ps(ROLE_CASHIER) is True
    assert manage_ps_devices(ROLE_OWNER) is True
    assert manage_ps_devices(ROLE_CASHIER) is False
