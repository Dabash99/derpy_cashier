"""The plain key/value settings fields (not users, not update-check)."""
from __future__ import annotations

import re
import sqlite3

from PySide2.QtCore import Signal
from PySide2.QtWidgets import QFormLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget

from derby.core import audit_service
from derby.core.db import settings_repo
from derby.core.i18n import ar

_CLOSE_TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_AUDITED_KEYS = (
    ("cafe_name", ar.SETTINGS_CAFE_NAME_LABEL),
    ("business_close_time", ar.SETTINGS_CLOSE_TIME_LABEL),
    ("ps_min_minutes", ar.SETTINGS_PS_MIN_MINUTES_LABEL),
    ("rounding_step_egp", ar.SETTINGS_ROUNDING_STEP_LABEL),
    ("auto_lock_minutes", ar.SETTINGS_AUTO_LOCK_LABEL),
)


class GeneralSettingsForm(QWidget):
    saved = Signal()

    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row = None, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        form = QFormLayout()
        outer.addLayout(form)

        self._cafe_name_input = QLineEdit()
        form.addRow(ar.SETTINGS_CAFE_NAME_LABEL, self._cafe_name_input)

        self._close_time_input = QLineEdit()
        self._close_time_input.setPlaceholderText("23:59")
        form.addRow(ar.SETTINGS_CLOSE_TIME_LABEL, self._close_time_input)

        self._ps_min_minutes_input = QSpinBox()
        self._ps_min_minutes_input.setRange(1, 180)
        form.addRow(ar.SETTINGS_PS_MIN_MINUTES_LABEL, self._ps_min_minutes_input)

        self._rounding_step_input = QSpinBox()
        self._rounding_step_input.setRange(1, 100)
        form.addRow(ar.SETTINGS_ROUNDING_STEP_LABEL, self._rounding_step_input)

        # whatsapp_number and the backup folders moved to the dedicated
        # "النسخ الاحتياطي والإقفال" tab (Phase 7), which has richer
        # validation (Egyptian-number hint, same-drive warning, folder
        # test buttons) -- editing them in two places would be confusing.

        self._auto_lock_input = QSpinBox()
        self._auto_lock_input.setRange(1, 120)
        form.addRow(ar.SETTINGS_AUTO_LOCK_LABEL, self._auto_lock_input)

        self._error_label = QLabel("")
        self._error_label.setProperty("role", "error")
        self._error_label.setWordWrap(True)
        outer.addWidget(self._error_label)

        save_button = QPushButton(ar.SETTINGS_SAVE_BUTTON)
        save_button.clicked.connect(self._on_save)
        outer.addWidget(save_button)

    def reload(self) -> None:
        values = settings_repo.get_all(self._conn)
        self._cafe_name_input.setText(values["cafe_name"])
        self._close_time_input.setText(values["business_close_time"])
        self._ps_min_minutes_input.setValue(int(values["ps_min_minutes"]))
        self._rounding_step_input.setValue(int(values["rounding_step_egp"]))
        self._auto_lock_input.setValue(int(values["auto_lock_minutes"]))
        self._error_label.setText("")

    def _on_save(self) -> None:
        close_time_text = self._close_time_input.text().strip()
        if not _CLOSE_TIME_PATTERN.match(close_time_text):
            self._error_label.setText(ar.SETTINGS_ERROR_INVALID_TIME)
            return

        before = settings_repo.get_all(self._conn)
        settings_repo.set_value(self._conn, "cafe_name", self._cafe_name_input.text().strip())
        settings_repo.set_value(self._conn, "business_close_time", close_time_text)
        settings_repo.set_value(self._conn, "ps_min_minutes", str(self._ps_min_minutes_input.value()))
        settings_repo.set_value(self._conn, "rounding_step_egp", str(self._rounding_step_input.value()))
        settings_repo.set_value(self._conn, "auto_lock_minutes", str(self._auto_lock_input.value()))
        after = settings_repo.get_all(self._conn)

        changed = {key: {"before": before[key], "after": after[key]} for key, _label in _AUDITED_KEYS if before.get(key) != after.get(key)}
        if changed:
            audit_service.log(
                self._conn, "settings_changed", user=self._user, entity_type="settings",
                summary_ar="تغيير إعدادات عامة: {0}".format(", ".join(changed.keys())),
                details=changed,
            )

        self._error_label.setText("")
        self.saved.emit()
