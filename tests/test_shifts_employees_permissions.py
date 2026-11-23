from __future__ import annotations

from derby.core.db.users_repo import ROLE_CASHIER, ROLE_OWNER
from derby.features.auth import permissions


def test_only_owner_manages_employees_and_sees_all_shifts():
    assert permissions.manage_employees(ROLE_OWNER) is True
    assert permissions.manage_employees(ROLE_CASHIER) is False
    assert permissions.manage_shifts_all(ROLE_OWNER) is True
    assert permissions.manage_shifts_all(ROLE_CASHIER) is False
    assert permissions.manage_attendance_corrections(ROLE_OWNER) is True
    assert permissions.manage_attendance_corrections(ROLE_CASHIER) is False


def test_both_roles_can_open_close_shift_and_clock_in_out():
    assert permissions.view_shift_report(ROLE_OWNER) is True
    assert permissions.view_shift_report(ROLE_CASHIER) is True
    assert permissions.clock_in_out(ROLE_OWNER) is True
    assert permissions.clock_in_out(ROLE_CASHIER) is True


def test_cashier_builds_a_screen_with_no_employees_or_payroll_panel(qapp, db_conn):
    """Direct-service-call guard: employee_service/payroll_service trust
    their caller (no role check inside them, same pattern as every
    other service here) -- the real enforcement point is that the
    screen never constructs an EmployeesPanel/PayrollPanel for a
    cashier at all (see also test_shifts_employees_screen.py)."""
    from derby.core.db import users_repo
    from derby.features.shifts.shifts_employees_screen import ShiftsEmployeesScreen

    cashier_id = users_repo.create_user(db_conn, "Cashier", ROLE_CASHIER, "2222")
    screen = ShiftsEmployeesScreen(db_conn, users_repo.get_user(db_conn, cashier_id))
    assert not hasattr(screen, "_employees_panel")
    assert not hasattr(screen, "_payroll_panel")
