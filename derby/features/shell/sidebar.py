"""The right-hand navigation list. Hides sections the current role can't use."""
from __future__ import annotations

from PySide2.QtCore import QSize, Signal
from PySide2.QtWidgets import QPushButton, QVBoxLayout, QWidget

from derby.core.i18n import ar
from derby.core.theme import icons
from derby.core.theme.styled import enable_styled_background
from derby.features.auth import permissions

# (key, label, icon name in assets/brand/icons, phase-if-not-built-yet, permission check)
SECTIONS = [
    ("menu", ar.SIDEBAR_MENU, "menu", None, permissions.can_manage_menu),
    ("pos", ar.SIDEBAR_CASHIER, "cashier", None, permissions.use_pos),
    ("tables", ar.SIDEBAR_TABLES, "tables", None, permissions.view_tables),
    ("sales_log", ar.SIDEBAR_SALES_LOG, "sales_log", None, permissions.view_sales_today),
    ("playstation", ar.SIDEBAR_PLAYSTATION, "playstation", None, permissions.use_ps),
    ("expenses", ar.SIDEBAR_EXPENSES, "expenses", None, permissions.can_access_expenses),
    # No dedicated icon asset exists yet for supplies -- reusing "expenses"
    # (closest existing shape) rather than leaving the sidebar button
    # iconless; swap this for a real icon once one is rendered via
    # tools/render_assets.py.
    ("supplies", ar.SIDEBAR_SUPPLIES, "expenses", None, permissions.view_supplies),
    ("reports", ar.SIDEBAR_REPORTS, "reports", None, permissions.can_access_reports),
    ("settings", ar.SIDEBAR_SETTINGS, "settings", None, permissions.can_access_settings),
]


class Sidebar(QWidget):
    navigate = Signal(str)

    def __init__(self, role: str, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        enable_styled_background(self)
        self._buttons = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 16, 8, 16)
        layout.setSpacing(4)

        for key, label, icon_name, _phase, allowed in SECTIONS:
            if not allowed(role):
                continue
            button = QPushButton(label)
            # "light" (cream stroke) icon variant, to sit on the black
            # sidebar background -- see docs/BRAND.md.
            button.setIcon(icons.icon(icon_name, variant="light"))
            button.setIconSize(QSize(20, 20))
            button.clicked.connect(lambda _checked=False, k=key: self.navigate.emit(k))
            layout.addWidget(button)
            self._buttons[key] = button

        layout.addStretch(1)

    def set_active(self, key: str) -> None:
        for button_key, button in self._buttons.items():
            button.setProperty("active", "true" if button_key == key else "false")
            button.style().unpolish(button)
            button.style().polish(button)
