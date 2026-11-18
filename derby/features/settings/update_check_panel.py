"""Owner-only "فحص التحديثات" button and its result display.

This is the single place in the UI that triggers Derby's one allowed
network call — see derby/core/updates/update_check.py for the request
itself, which this panel only drives and reports on.
"""
from __future__ import annotations

import sqlite3
import webbrowser

from PySide2.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from derby.core.db import audit_repo, settings_repo
from derby.core.i18n import ar
from derby.core.updates.update_check import (
    FAILURE_INVALID,
    FAILURE_OFFLINE,
    FAILURE_SSL,
    UpdateCheckWorker,
)
from derby.core.updates.version_logic import is_allowed_download_url


class UpdateCheckPanel(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._worker = None
        self._download_url = ""
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        button_row = QHBoxLayout()
        self._check_button = QPushButton(ar.UPDATE_CHECK_BUTTON)
        self._check_button.clicked.connect(self._on_check_clicked)
        button_row.addWidget(self._check_button)

        self._open_download_button = QPushButton(ar.UPDATE_CHECK_OPEN_DOWNLOAD_PAGE)
        self._open_download_button.clicked.connect(self._on_open_download_clicked)
        self._open_download_button.hide()
        button_row.addWidget(self._open_download_button)

        layout.addLayout(button_row)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

    def reload(self) -> None:
        manifest_url = settings_repo.get(self._conn, "update_manifest_url", "") or ""
        self._open_download_button.hide()
        if not manifest_url:
            self._check_button.setEnabled(False)
            self._status_label.setText(ar.UPDATE_CHECK_NO_URL_HINT)
        else:
            self._check_button.setEnabled(True)
            self._status_label.setText("")

    def _on_check_clicked(self) -> None:
        manifest_url = settings_repo.get(self._conn, "update_manifest_url", "") or ""
        if not manifest_url:
            return
        self._check_button.setEnabled(False)
        self._open_download_button.hide()
        self._status_label.setText(ar.UPDATE_CHECK_CHECKING)

        self._worker = UpdateCheckWorker(manifest_url, self)
        self._worker.succeeded.connect(self._on_succeeded)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_succeeded(self, result) -> None:
        self._check_button.setEnabled(True)
        if result.up_to_date:
            self._status_label.setText(ar.UPDATE_CHECK_UP_TO_DATE)
            audit_repo.log(self._conn, "update_check", details="up_to_date")
        else:
            self._status_label.setText(
                ar.UPDATE_CHECK_NEW_VERSION_AVAILABLE.format(version=result.version) + "\n" + result.notes
            )
            if is_allowed_download_url(result.download_url):
                self._download_url = result.download_url
                self._open_download_button.show()
            audit_repo.log(self._conn, "update_check", details="new_version:{0}".format(result.version))

    def _on_failed(self, category: str) -> None:
        self._check_button.setEnabled(True)
        messages = {
            FAILURE_OFFLINE: ar.UPDATE_CHECK_FAILED_OFFLINE,
            FAILURE_SSL: ar.UPDATE_CHECK_FAILED_SSL,
            FAILURE_INVALID: ar.UPDATE_CHECK_FAILED_INVALID_RESPONSE,
        }
        self._status_label.setText(messages.get(category, ar.UPDATE_CHECK_FAILED_OFFLINE))
        audit_repo.log(self._conn, "update_check", details="failed:{0}".format(category))

    def _on_open_download_clicked(self) -> None:
        if is_allowed_download_url(self._download_url):
            webbrowser.open(self._download_url)
        else:
            self._status_label.setText(ar.UPDATE_CHECK_REJECTED_DOWNLOAD_HOST)
