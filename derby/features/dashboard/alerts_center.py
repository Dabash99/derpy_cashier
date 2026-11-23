"""Compact tappable alerts list on الرئيسية (owner only)."""
from __future__ import annotations

import sqlite3

from PySide2.QtCore import Signal
from PySide2.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from derby.core.i18n import ar
from derby.core.theme.styled import enable_styled_background
from derby.features.dashboard import alerts_service


class AlertsCenter(QWidget):
    navigate_requested = Signal(str)

    def __init__(self, conn: sqlite3.Connection, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setObjectName("AlertsCenter")
        self.setProperty("variant", "banner")
        enable_styled_background(self)
        self._conn = conn
        self._rows_layout = QVBoxLayout(self)
        self._rows_layout.setContentsMargins(12, 8, 12, 8)
        self._rows_layout.setSpacing(4)
        self.reload()

    def reload(self) -> None:
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

        alerts = alerts_service.compute_alerts(self._conn)
        if not alerts:
            self.setVisible(False)
            return
        self.setVisible(True)

        title = QLabel(ar.ALERTS_CENTER_TITLE)
        title.setProperty("role", "subtitle")
        self._rows_layout.addWidget(title)
        for alert in alerts:
            self._rows_layout.addWidget(self._build_row(alert))

    def _build_row(self, alert) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(alert.text)
        label.setProperty("role", "error" if alert.severity == alerts_service.SEVERITY_ERROR else "warning")
        label.setWordWrap(True)
        layout.addWidget(label, 1)
        if alert.navigate_key:
            button = QPushButton(ar.ALERTS_CENTER_VIEW_BUTTON)
            button.clicked.connect(lambda _c=False, key=alert.navigate_key: self.navigate_requested.emit(key))
            layout.addWidget(button)
        return row
