"""Settings -> أدوات متقدمة: today, just the go-live cleanup button."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide2.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QWidget

from derby.core.i18n import ar
from derby.features.settings.go_live_cleanup_dialog import GoLiveCleanupDialog


class AdvancedToolsPanel(QWidget):
    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, db_path: Path, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._db_path = db_path
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel(ar.ADVANCED_TOOLS_TITLE)
        title.setProperty("role", "title")
        layout.addWidget(title)

        cleanup_button = QPushButton(ar.ADVANCED_CLEANUP_BUTTON)
        cleanup_button.setProperty("danger", "true")
        cleanup_button.clicked.connect(self._on_cleanup)
        layout.addWidget(cleanup_button)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        layout.addStretch(1)

    def _on_cleanup(self) -> None:
        dialog = GoLiveCleanupDialog(self._conn, self._user, self._db_path, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self._status_label.setText(dialog.result_message)
