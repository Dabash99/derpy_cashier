"""The confirmation dialog for "تصفية بيانات التجربة" (Settings -> أدوات
متقدمة): a clear warning, the owner's PIN, and a typed confirmation
word -- all three are checked before go_live_cleanup_service.run_cleanup
even attempts the safety backup.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide2.QtWidgets import QDialog, QLabel, QLineEdit, QPushButton, QVBoxLayout

from derby.core.db import settings_repo
from derby.core.i18n import ar
from derby.core.utils.paths import default_backup_dir
from derby.core.utils.time_utils import utc_now
from derby.features.closing.backup_service import BackupError
from derby.features.pos.exceptions import ApprovalLockedOutError, WrongApprovalPinError
from derby.features.settings import go_live_cleanup_service
from derby.features.settings.exceptions import ConfirmationWordMismatchError


class GoLiveCleanupDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, db_path: Path, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._db_path = db_path
        self.result_message = ""
        self.setWindowTitle(ar.ADVANCED_CLEANUP_BUTTON)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        warning_label = QLabel(ar.ADVANCED_CLEANUP_WARNING)
        warning_label.setProperty("role", "error")
        warning_label.setWordWrap(True)
        layout.addWidget(warning_label)

        layout.addWidget(QLabel(ar.ADVANCED_CLEANUP_PIN_LABEL))
        self._pin_input = QLineEdit()
        self._pin_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self._pin_input)

        layout.addWidget(QLabel(ar.ADVANCED_CLEANUP_CONFIRM_WORD_LABEL))
        self._word_input = QLineEdit()
        layout.addWidget(self._word_input)

        self._error_label = QLabel("")
        self._error_label.setProperty("role", "error")
        self._error_label.setWordWrap(True)
        layout.addWidget(self._error_label)

        confirm_button = QPushButton(ar.ADVANCED_CLEANUP_CONFIRM_BUTTON)
        confirm_button.setProperty("danger", "true")
        confirm_button.clicked.connect(self._on_confirm)
        layout.addWidget(confirm_button)

    def _backup_dir(self) -> Path:
        return Path(settings_repo.get(self._conn, "backup_folder_primary") or default_backup_dir())

    def _on_confirm(self) -> None:
        try:
            result = go_live_cleanup_service.run_cleanup(
                self._conn, self._db_path, self._backup_dir(), utc_now(), self._user,
                self._pin_input.text(), self._word_input.text(),
            )
        except WrongApprovalPinError:
            self._error_label.setText(ar.DISCOUNT_ERROR_WRONG_PIN)
            return
        except ApprovalLockedOutError:
            self._error_label.setText(ar.LOGIN_ERROR_LOCKED.format(minutes=0, seconds=0))
            return
        except ConfirmationWordMismatchError:
            self._error_label.setText(ar.ADVANCED_CLEANUP_ERROR_WORD)
            return
        except BackupError as error:
            self._error_label.setText(ar.ADVANCED_CLEANUP_ERROR_BACKUP_FAILED.format(error=str(error)))
            return
        self.result_message = ar.ADVANCED_CLEANUP_SUCCESS_MESSAGE.format(path=result["backup_path"])
        self.accept()
