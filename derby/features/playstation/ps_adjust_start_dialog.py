""""ضبط وقت البدء" on a running session (the customer arrived earlier, or
the cashier forgot to start it). The new time is read as today's Cairo
wall-clock time; ps_service rejects anything in the future or more than
12 hours in the past. A cashier needs the owner's PIN, same as a discount.
"""
from __future__ import annotations

import sqlite3
from datetime import timezone

from PySide2.QtWidgets import QDialog, QFormLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from derby.core.db import ps_sessions_repo, users_repo
from derby.core.i18n import ar
from derby.core.utils.time_utils import parse_utc_iso, to_cairo, utc_now
from derby.features.playstation import ps_service
from derby.features.pos.exceptions import (
    ApprovalLockedOutError,
    InvalidTransitionError,
    WrongApprovalPinError,
)


class PsAdjustStartDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, device_id: int, requesting_user: sqlite3.Row, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._device_id = device_id
        self._requesting_user = requesting_user
        self.setWindowTitle(ar.PS_ADJUST_START_TITLE)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        running = ps_sessions_repo.get_running_session(self._conn, self._device_id)
        current_cairo = to_cairo(parse_utc_iso(running["started_at_utc"])) if running is not None else to_cairo(utc_now())

        self._time_input = QLineEdit(current_cairo.strftime("%H:%M"))
        form.addRow(ar.PS_ADJUST_START_LABEL, self._time_input)

        self._pin_input = QLineEdit()
        self._pin_input.setEchoMode(QLineEdit.Password)
        if self._requesting_user["role"] != users_repo.ROLE_OWNER:
            form.addRow(ar.DISCOUNT_OWNER_PIN_LABEL, self._pin_input)

        self._error_label = QLabel("")
        self._error_label.setProperty("role", "error")
        self._error_label.setWordWrap(True)
        layout.addWidget(self._error_label)

        save_button = QPushButton(ar.PS_ADJUST_START_BUTTON)
        save_button.clicked.connect(self._on_save)
        layout.addWidget(save_button)

    def _on_save(self) -> None:
        running = ps_sessions_repo.get_running_session(self._conn, self._device_id)
        if running is None:
            self.reject()
            return

        try:
            hour_str, minute_str = self._time_input.text().strip().split(":")
            reference_day = to_cairo(parse_utc_iso(running["started_at_utc"])).date()
            new_cairo = to_cairo(parse_utc_iso(running["started_at_utc"])).replace(
                year=reference_day.year, month=reference_day.month, day=reference_day.day,
                hour=int(hour_str), minute=int(minute_str), second=0, microsecond=0,
            )
        except (ValueError, IndexError):
            self._error_label.setText(ar.PS_ADJUST_START_ERROR_FORMAT)
            return

        new_utc = new_cairo.astimezone(timezone.utc)

        try:
            ps_service.adjust_session_start(
                self._conn, self._device_id, new_utc, self._requesting_user, approving_pin=self._pin_input.text()
            )
        except InvalidTransitionError as error:
            self._error_label.setText(str(error))
            return
        except WrongApprovalPinError:
            self._error_label.setText(ar.DISCOUNT_ERROR_WRONG_PIN)
            return
        except ApprovalLockedOutError:
            self._error_label.setText(ar.LOGIN_ERROR_LOCKED.format(minutes=0, seconds=0))
            return
        self.accept()
