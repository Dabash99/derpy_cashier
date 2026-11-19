"""First-run screen: creates the cafe name and the first (owner) user.

Shown only when the users table is empty.
"""
from __future__ import annotations

import sqlite3

from PySide2.QtCore import QRegExp, Qt, Signal
from PySide2.QtGui import QRegExpValidator
from PySide2.QtWidgets import (
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from derby.core.db import users_repo
from derby.core.db.settings_repo import set_value
from derby.core.i18n import ar
from derby.core.theme import icons
from derby.core.utils.pin_hash import is_valid_pin_format


class SetupScreen(QWidget):
    setup_completed = Signal()

    def __init__(self, conn: sqlite3.Connection, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(60, 60, 60, 60)
        layout.setSpacing(14)

        logo_label = QLabel()
        logo_label.setPixmap(icons.logo_pixmap("transparent", 140))
        logo_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo_label)

        title = QLabel(ar.SETUP_TITLE)
        title.setProperty("role", "title")
        layout.addWidget(title)

        self._cafe_name_input = QLineEdit()
        layout.addWidget(QLabel(ar.SETUP_CAFE_NAME_LABEL))
        layout.addWidget(self._cafe_name_input)

        self._owner_name_input = QLineEdit()
        layout.addWidget(QLabel(ar.SETUP_OWNER_NAME_LABEL))
        layout.addWidget(self._owner_name_input)

        pin_validator = QRegExpValidator(QRegExp(r"\d{0,6}"))

        self._pin_input = QLineEdit()
        self._pin_input.setEchoMode(QLineEdit.Password)
        self._pin_input.setValidator(pin_validator)
        layout.addWidget(QLabel(ar.SETUP_OWNER_PIN_LABEL))
        layout.addWidget(self._pin_input)

        self._pin_confirm_input = QLineEdit()
        self._pin_confirm_input.setEchoMode(QLineEdit.Password)
        self._pin_confirm_input.setValidator(pin_validator)
        layout.addWidget(QLabel(ar.SETUP_OWNER_PIN_CONFIRM_LABEL))
        layout.addWidget(self._pin_confirm_input)

        self._error_label = QLabel("")
        self._error_label.setProperty("role", "error")
        self._error_label.setWordWrap(True)
        layout.addWidget(self._error_label)

        submit_button = QPushButton(ar.SETUP_SUBMIT_BUTTON)
        submit_button.setProperty("variant", "primary")
        submit_button.clicked.connect(self._on_submit)
        layout.addWidget(submit_button)

        layout.addStretch(1)

    def _on_submit(self) -> None:
        cafe_name = self._cafe_name_input.text().strip()
        owner_name = self._owner_name_input.text().strip()
        pin = self._pin_input.text()
        pin_confirm = self._pin_confirm_input.text()

        if not cafe_name:
            self._show_error(ar.SETUP_ERROR_CAFE_NAME_REQUIRED)
            return
        if not owner_name:
            self._show_error(ar.SETUP_ERROR_OWNER_NAME_REQUIRED)
            return
        if not is_valid_pin_format(pin):
            self._show_error(ar.SETUP_ERROR_PIN_FORMAT)
            return
        if pin != pin_confirm:
            self._show_error(ar.SETUP_ERROR_PIN_MISMATCH)
            return

        set_value(self._conn, "cafe_name", cafe_name)
        users_repo.create_user(self._conn, owner_name, users_repo.ROLE_OWNER, pin)
        self.setup_completed.emit()

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
