from __future__ import annotations

from derby.core.db.users_repo import ROLE_CASHIER, ROLE_OWNER
from derby.features.auth.permissions import export_data, manage_expenses, view_reports


def test_expenses_reports_export_are_owner_only():
    assert manage_expenses(ROLE_OWNER) is True
    assert manage_expenses(ROLE_CASHIER) is False
    assert view_reports(ROLE_OWNER) is True
    assert view_reports(ROLE_CASHIER) is False
    assert export_data(ROLE_OWNER) is True
    assert export_data(ROLE_CASHIER) is False
