"""The right-hand navigation list. Hides sections the current role can't use."""
from __future__ import annotations

from PySide2.QtCore import Signal
from PySide2.QtWidgets import QPushButton, QVBoxLayout, QWidget

from derby.core.i18n import ar
from derby.features.auth import permissions

# (key, label, phase-if-not-built-yet, permission check)
SECTIONS = [
    ("menu", ar.SIDEBAR_MENU, None, permissions.can_manage_menu),
    ("pos", ar.SIDEBAR_CASHIER, None, permissions.use_pos),
    ("tables", ar.SIDEBAR_TABLES, None, permissions.view_tables),
    ("sales_log", ar.SIDEBAR_SALES_LOG, None, permissions.view_sales_today),
    ("playstation", ar.SIDEBAR_PLAYSTATION, None, permissions.use_ps),
    ("expenses", ar.SIDEBAR_EXPENSES, None, permissions.can_access_expenses),
    ("reports", ar.SIDEBAR_REPORTS, None, permissions.can_access_reports),
    ("settings", ar.SIDEBAR_SETTINGS, None, permissions.can_access_settings),
]


class Sidebar(QWidget):
    navigate = Signal(str)

    def __init__(self, role: str, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self._buttons = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 16, 8, 16)
        layout.setSpacing(4)

        for key, label, _phase, allowed in SECTIONS:
            if not allowed(role):
                continue
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, k=key: self.navigate.emit(k))
            layout.addWidget(button)
            self._buttons[key] = button

        layout.addStretch(1)

    def set_active(self, key: str) -> None:
        for button_key, button in self._buttons.items():
            button.setProperty("active", "true" if button_key == key else "false")
            button.style().unpolish(button)
            button.style().polish(button)
