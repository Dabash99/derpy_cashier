"""PIN-only login screen. No username: the PIN itself identifies the user.

Accepts digits both from the on-screen keypad buttons and from a physical
keyboard, since the cashier PC may or may not have a touchscreen.
"""
from __future__ import annotations

import sqlite3

from PySide2.QtCore import QRegExp, Qt, QTimer, Signal
from PySide2.QtGui import QRegExpValidator
from PySide2.QtWidgets import (
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from derby.core.db import audit_repo, users_repo
from derby.core.i18n import ar
from derby.features.auth import lockout

MAX_PIN_LENGTH = 6


class LoginScreen(QWidget):
    login_succeeded = Signal(object)  # sqlite3.Row of the logged-in user

    def __init__(self, conn: sqlite3.Connection, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._build_ui()
        self._lock_timer = QTimer(self)
        self._lock_timer.setInterval(1000)
        self._lock_timer.timeout.connect(self._refresh_lock_state)
        self._refresh_lock_state()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(60, 40, 60, 40)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel(ar.LOGIN_TITLE)
        title.setProperty("role", "title")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        self._pin_display = QLineEdit()
        self._pin_display.setEchoMode(QLineEdit.Password)
        self._pin_display.setAlignment(Qt.AlignCenter)
        self._pin_display.setValidator(QRegExpValidator(QRegExp(r"\d{{0,{0}}}".format(MAX_PIN_LENGTH))))
        self._pin_display.setMaxLength(MAX_PIN_LENGTH)
        self._pin_display.returnPressed.connect(self._on_login_clicked)
        layout.addWidget(self._pin_display)

        keypad_layout = QGridLayout()
        keypad_layout.setSpacing(8)
        digit_positions = [
            ("1", 0, 0), ("2", 0, 1), ("3", 0, 2),
            ("4", 1, 0), ("5", 1, 1), ("6", 1, 2),
            ("7", 2, 0), ("8", 2, 1), ("9", 2, 2),
            (ar.LOGIN_CLEAR_BUTTON, 3, 0), ("0", 3, 1),
        ]
        for label, row, col in digit_positions:
            button = QPushButton(label)
            button.setMinimumHeight(48)
            if label == ar.LOGIN_CLEAR_BUTTON:
                button.clicked.connect(self._pin_display.clear)
            else:
                button.clicked.connect(lambda _checked=False, d=label: self._append_digit(d))
            keypad_layout.addWidget(button, row, col)
        layout.addLayout(keypad_layout)

        self._login_button = QPushButton(ar.LOGIN_BUTTON)
        self._login_button.setMinimumHeight(48)
        self._login_button.clicked.connect(self._on_login_clicked)
        layout.addWidget(self._login_button)

        self._error_label = QLabel("")
        self._error_label.setProperty("role", "error")
        self._error_label.setAlignment(Qt.AlignCenter)
        self._error_label.setWordWrap(True)
        layout.addWidget(self._error_label)

    def _append_digit(self, digit: str) -> None:
        if len(self._pin_display.text()) < MAX_PIN_LENGTH:
            self._pin_display.setText(self._pin_display.text() + digit)

    def _on_login_clicked(self) -> None:
        remaining = lockout.get_lock_remaining(self._conn)
        if remaining is not None:
            self._show_lock_message(remaining)
            return

        pin = self._pin_display.text()
        if not users_repo.has_any_users(self._conn):
            self._error_label.setText(ar.LOGIN_ERROR_NO_ACTIVE_USERS)
            return

        user = users_repo.find_active_user_by_pin(self._conn, pin)
        if user is None:
            lockout.record_failed_attempt(self._conn)
            self._pin_display.clear()
            remaining_after = lockout.get_lock_remaining(self._conn)
            if remaining_after is not None:
                self._show_lock_message(remaining_after)
            else:
                self._error_label.setText(ar.LOGIN_ERROR_WRONG_PIN)
            return

        lockout.reset_failed_attempts(self._conn)
        audit_repo.log(self._conn, "login", user_id=user["id"])
        self._pin_display.clear()
        self._error_label.setText("")
        self.login_succeeded.emit(user)

    def _show_lock_message(self, remaining) -> None:
        total_seconds = max(0, int(remaining.total_seconds()))
        minutes, seconds = divmod(total_seconds, 60)
        self._error_label.setText(ar.LOGIN_ERROR_LOCKED.format(minutes=minutes, seconds=seconds))
        self._login_button.setEnabled(False)
        if not self._lock_timer.isActive():
            self._lock_timer.start()

    def _refresh_lock_state(self) -> None:
        remaining = lockout.get_lock_remaining(self._conn)
        if remaining is None:
            self._lock_timer.stop()
            self._login_button.setEnabled(True)
            if self._error_label.text().startswith(ar.LOGIN_ERROR_LOCKED.split("{")[0]):
                self._error_label.setText("")
        else:
            self._show_lock_message(remaining)

    def showEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().showEvent(event)
        self._pin_display.clear()
        self._pin_display.setFocus()
        self._refresh_lock_state()
