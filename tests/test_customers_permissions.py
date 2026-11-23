from __future__ import annotations

from derby.core.db.users_repo import ROLE_CASHIER, ROLE_OWNER
from derby.features.auth import permissions


def test_both_roles_view_customers_and_record_payments():
    assert permissions.view_customers(ROLE_OWNER) is True
    assert permissions.view_customers(ROLE_CASHIER) is True
    assert permissions.record_customer_payment(ROLE_OWNER) is True
    assert permissions.record_customer_payment(ROLE_CASHIER) is True


def test_sell_on_credit_respects_the_cashier_setting():
    assert permissions.sell_on_credit(ROLE_OWNER, cashiers_may_sell_on_credit=False) is True
    assert permissions.sell_on_credit(ROLE_CASHIER, cashiers_may_sell_on_credit=False) is False
    assert permissions.sell_on_credit(ROLE_CASHIER, cashiers_may_sell_on_credit=True) is True


def test_only_owner_manages_customers_records():
    assert permissions.manage_customers(ROLE_OWNER) is True
    assert permissions.manage_customers(ROLE_CASHIER) is False
