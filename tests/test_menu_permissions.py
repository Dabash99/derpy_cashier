from __future__ import annotations

from derby.core.db.users_repo import ROLE_CASHIER, ROLE_OWNER
from derby.features.auth.permissions import can_manage_menu


def test_only_owner_can_manage_menu():
    assert can_manage_menu(ROLE_OWNER) is True
    assert can_manage_menu(ROLE_CASHIER) is False
