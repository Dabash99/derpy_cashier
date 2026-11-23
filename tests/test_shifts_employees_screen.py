"""Offscreen widget smoke tests for the الورديات والموظفين screen, for
both an owner (every tab) and a cashier (shift + attendance only)."""
from __future__ import annotations

from derby.core.db import users_repo
from derby.features.shifts.shifts_employees_screen import ShiftsEmployeesScreen


def test_owner_sees_every_tab(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    screen = ShiftsEmployeesScreen(db_conn, owner)
    titles = [screen._tabs.tabText(i) for i in range(screen._tabs.count())]
    assert len(titles) == 5  # shift, history, attendance, employees, payroll


def test_cashier_sees_only_shift_and_attendance(qapp, db_conn):
    cashier_id = users_repo.create_user(db_conn, "Cashier", users_repo.ROLE_CASHIER, "2222")
    cashier = users_repo.get_user(db_conn, cashier_id)
    screen = ShiftsEmployeesScreen(db_conn, cashier)
    assert screen._tabs.count() == 2
    assert not hasattr(screen, "_employees_panel")
    assert not hasattr(screen, "_payroll_panel")
    assert not hasattr(screen, "_history_panel")


def test_cashier_can_open_and_close_own_shift_through_the_panel(qapp, db_conn):
    cashier_id = users_repo.create_user(db_conn, "Cashier", users_repo.ROLE_CASHIER, "2222")
    cashier = users_repo.get_user(db_conn, cashier_id)
    screen = ShiftsEmployeesScreen(db_conn, cashier)
    panel = screen._shift_panel

    panel._opening_cash_input.setText("100")
    panel._on_open()
    assert panel._close_button.isEnabled() is True

    panel._counted_input.setText("100")
    panel._on_close()
    assert panel._open_button.isEnabled() is True
