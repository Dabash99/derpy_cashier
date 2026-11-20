"""The right-hand navigation list. Hides sections the current role can't use."""
from __future__ import annotations

from PySide2.QtCore import QSize, Qt, Signal
from PySide2.QtWidgets import QFrame, QPushButton, QScrollArea, QVBoxLayout, QWidget

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
    # No dedicated "chart bars" icon asset exists yet -- reusing "reports"
    # (closest existing shape), same stand-in approach as supplies' icon.
    ("daily_stats", ar.SIDEBAR_DAILY_STATS, "reports", None, permissions.view_daily_stats),
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

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # A plain QVBoxLayout here has no way to shrink once its buttons'
        # combined natural height no longer fits the window -- Qt's
        # layout engine responds to that deficit by overlapping items
        # rather than scrolling (confirmed: at 1024x680 with every
        # section enabled, button N+1 starts before button N ends). A
        # scroll area, same pattern as the PlayStation cards and Reports
        # sections, scrolls instead.
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setObjectName("SidebarScrollArea")

        host = QWidget()
        host.setObjectName("SidebarScrollHost")
        layout = QVBoxLayout(host)
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
        scroll_area.setWidget(host)
        outer.addWidget(scroll_area)

    def set_active(self, key: str) -> None:
        for button_key, button in self._buttons.items():
            button.setProperty("active", "true" if button_key == key else "false")
            button.style().unpolish(button)
            button.style().polish(button)
