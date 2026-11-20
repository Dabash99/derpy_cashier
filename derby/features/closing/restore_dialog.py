"""Owner-only restore flow: pick a backup file, confirm with the owner's
PIN (reusing the same lockout as every other owner-approval action),
see a clear warning, then stage the swap for the next startup. The
caller (BackupClosingPanel) quits the app once this dialog accepts.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from PySide2.QtWidgets import QCheckBox, QDialog, QFileDialog, QLabel, QLineEdit, QPushButton, QVBoxLayout

from derby.core.i18n import ar
from derby.core.utils.paths import app_data_dir, default_backup_dir
from derby.core.utils.time_utils import utc_now
from derby.features.closing import restore_service
from derby.features.expenses import receipts
from derby.features.menu import images
from derby.features.pos import owner_approval
from derby.features.pos.exceptions import ApprovalLockedOutError, WrongApprovalPinError


class RestoreDialog(QDialog):
    def __init__(
        self,
        conn: sqlite3.Connection,
        user: sqlite3.Row,
        primary_dir: Optional[Path],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._primary_dir = primary_dir
        self._chosen_path: Optional[Path] = None
        self.setWindowTitle(ar.RESTORE_TITLE)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        warning_label = QLabel(ar.RESTORE_WARNING)
        warning_label.setProperty("role", "error")
        warning_label.setWordWrap(True)
        layout.addWidget(warning_label)

        pick_button = QPushButton(ar.RESTORE_PICK_FILE_BUTTON)
        pick_button.clicked.connect(self._on_pick_file)
        layout.addWidget(pick_button)
        self._chosen_label = QLabel("")
        layout.addWidget(self._chosen_label)

        self._copy_images_checkbox = QCheckBox(ar.RESTORE_COPY_IMAGES_LABEL)
        self._copy_images_checkbox.setChecked(True)
        layout.addWidget(self._copy_images_checkbox)

        layout.addWidget(QLabel(ar.RESTORE_PIN_LABEL))
        self._pin_input = QLineEdit()
        self._pin_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self._pin_input)

        self._error_label = QLabel("")
        self._error_label.setProperty("role", "error")
        self._error_label.setWordWrap(True)
        layout.addWidget(self._error_label)

        confirm_button = QPushButton(ar.RESTORE_CONFIRM_BUTTON)
        confirm_button.setProperty("danger", "true")
        confirm_button.clicked.connect(self._on_confirm)
        layout.addWidget(confirm_button)

    def _on_pick_file(self) -> None:
        start_dir = str(self._primary_dir) if self._primary_dir else str(default_backup_dir())
        file_path, _filter = QFileDialog.getOpenFileName(self, ar.RESTORE_PICK_FILE_BUTTON, start_dir, "SQLite DB (*.db)")
        if not file_path:
            return
        self._chosen_path = Path(file_path)
        self._chosen_label.setText(self._chosen_path.name)
        self._error_label.setText("")

    def _on_confirm(self) -> None:
        if self._chosen_path is None:
            return

        try:
            restore_service.validate_backup_file(self._chosen_path)
        except restore_service.RestoreValidationError as error:
            self._error_label.setText(str(error))
            return

        try:
            owner_approval.verify_owner_pin(self._conn, self._pin_input.text())
        except WrongApprovalPinError:
            self._error_label.setText(ar.RESTORE_ERROR_WRONG_PIN)
            return
        except ApprovalLockedOutError:
            self._error_label.setText(ar.LOGIN_ERROR_LOCKED.format(minutes=0, seconds=0))
            return

        if self._copy_images_checkbox.isChecked():
            restore_service.offer_mirror_restore(self._chosen_path, images.images_dir(), receipts.receipts_dir())

        primary_backup_dir = self._primary_dir or default_backup_dir()
        restore_service.stage_restore(self._chosen_path, app_data_dir(), primary_backup_dir, utc_now())
        self.accept()
