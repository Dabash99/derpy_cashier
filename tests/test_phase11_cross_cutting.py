"""Cross-cutting Phase 11 checks: every new permission key exists and
gates correctly, and a cashier cannot reach an owner-only Phase 11
screen/service directly (not just that the sidebar hides the button).
"""
from __future__ import annotations

from derby.core.db.users_repo import ROLE_CASHIER, ROLE_OWNER
from derby.features.auth import permissions


def test_manage_backups_is_owner_only():
    assert permissions.manage_backups(ROLE_OWNER) is True
    assert permissions.manage_backups(ROLE_CASHIER) is False


def test_every_new_phase11_permission_key_is_defined_and_sane():
    # Every key the task asked for, each checked for the right default
    # shape (owner-only vs shared-by-both) in one place.
    owner_only = [
        permissions.view_audit_log, permissions.manage_backups, permissions.manage_employees,
        permissions.manage_shifts_all, permissions.manage_attendance_corrections, permissions.manage_customers,
        permissions.manage_discount_presets, permissions.manage_alerts_settings,
    ]
    for check in owner_only:
        assert check(ROLE_OWNER) is True
        assert check(ROLE_CASHIER) is False

    shared = [
        permissions.view_shift_report, permissions.clock_in_out, permissions.view_customers,
        permissions.record_customer_payment,
    ]
    for check in shared:
        assert check(ROLE_OWNER) is True
        assert check(ROLE_CASHIER) is True


def test_cashier_cannot_build_owner_only_phase11_screens_directly(qapp, db_conn):
    """Constructing the widget directly (bypassing the sidebar) must
    still not expose owner-only sub-panels/data to a cashier -- the
    screen itself must respect the role, not just the sidebar button."""
    from derby.core.db import users_repo

    cashier_id = users_repo.create_user(db_conn, "Cashier", ROLE_CASHIER, "2222")
    cashier = users_repo.get_user(db_conn, cashier_id)

    from derby.features.shifts.shifts_employees_screen import ShiftsEmployeesScreen

    screen = ShiftsEmployeesScreen(db_conn, cashier)
    assert not hasattr(screen, "_employees_panel")
    assert not hasattr(screen, "_payroll_panel")
    assert not hasattr(screen, "_history_panel")


def test_cashier_cannot_void_or_exceed_credit_limit_without_owner_pin(db_conn):
    """Direct service-call guard (not UI-level): orders_service.void and
    customer_service.credit_sale both re-check permission/approval
    themselves, so calling them directly as a cashier -- skipping
    whatever button visibility the UI enforces -- still fails."""
    from derby.core.db import categories_repo, products_repo, tables_repo, users_repo
    from derby.features.customers import customer_service
    from derby.features.pos import orders_service
    from derby.features.pos.exceptions import PermissionDeniedError, WrongApprovalPinError

    owner_id = users_repo.create_user(db_conn, "Owner", ROLE_OWNER, "1111")
    cashier_id = users_repo.create_user(db_conn, "Cashier", ROLE_CASHIER, "2222")
    owner = users_repo.get_user(db_conn, owner_id)
    cashier = users_repo.get_user(db_conn, cashier_id)

    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 2500)
    table = tables_repo.list_tables(db_conn)[0]

    order = orders_service.get_or_create_table_order(db_conn, table["id"], cashier["id"])
    orders_service.add_item(db_conn, order["id"], product_id, 1, [], None, cashier["id"])
    paid = orders_service.pay(db_conn, order["id"], "cash", cashier)
    try:
        orders_service.void(db_conn, paid["id"], "test", cashier)
        assert False, "expected PermissionDeniedError"
    except PermissionDeniedError:
        pass

    customer = customer_service.create_customer(db_conn, "محمد", None, None, 1000, owner)
    order2 = orders_service.get_or_create_table_order(db_conn, table["id"], cashier["id"])
    orders_service.add_item(db_conn, order2["id"], product_id, 1, [], None, cashier["id"])
    try:
        customer_service.credit_sale(db_conn, order2["id"], customer["id"], cashier, approving_pin="9999")
        assert False, "expected WrongApprovalPinError"
    except WrongApprovalPinError:
        pass
