from __future__ import annotations

from derby.core.db.users_repo import ROLE_CASHIER, ROLE_OWNER
from derby.features.auth.permissions import manage_supplies_costs, view_supplies


def test_both_roles_can_view_supplies():
    assert view_supplies(ROLE_OWNER) is True
    assert view_supplies(ROLE_CASHIER) is True


def test_only_owner_can_manage_supplies_costs():
    assert manage_supplies_costs(ROLE_OWNER) is True
    assert manage_supplies_costs(ROLE_CASHIER) is False
