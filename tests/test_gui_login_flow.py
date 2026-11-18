"""Exercises the real widget wiring (not just the underlying logic
modules) for login, lockout, and role-based sidebar visibility.
"""
from __future__ import annotations

from derby.core.db import users_repo
from derby.features.auth import lockout
from derby.features.auth.login_screen import LoginScreen
from derby.features.shell.main_window import MainWindow


def test_login_screen_locks_after_five_wrong_pins(qapp, db_conn):
    users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1234")
    screen = LoginScreen(db_conn)

    for _ in range(5):
        screen._pin_display.setText("0000")
        screen._on_login_clicked()

    assert lockout.is_locked(db_conn) is True
    assert screen._login_button.isEnabled() is False


def test_login_screen_succeeds_with_correct_pin(qapp, db_conn):
    user_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "5678")
    screen = LoginScreen(db_conn)

    received = []
    screen.login_succeeded.connect(lambda user: received.append(user))

    screen._pin_display.setText("5678")
    screen._on_login_clicked()

    assert len(received) == 1
    assert received[0]["id"] == user_id


def test_main_window_hides_sections_for_cashier(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    cashier_id = users_repo.create_user(db_conn, "Cashier", users_repo.ROLE_CASHIER, "2222")
    owner_row = users_repo.get_user(db_conn, owner_id)
    cashier_row = users_repo.get_user(db_conn, cashier_id)

    from derby.features.shell.idle_filter import IdleTimer

    owner_window = MainWindow(db_conn, owner_row, IdleTimer())
    assert "settings" in owner_window._screens
    assert "expenses" in owner_window._screens
    assert "reports" in owner_window._screens
    assert "menu" in owner_window._screens

    cashier_window = MainWindow(db_conn, cashier_row, IdleTimer())
    assert "settings" not in cashier_window._screens
    assert "expenses" not in cashier_window._screens
    assert "reports" not in cashier_window._screens
    assert "menu" not in cashier_window._screens
    assert "pos" in cashier_window._screens
