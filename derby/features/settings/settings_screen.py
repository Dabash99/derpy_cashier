"""Owner-only Settings screen: general settings, users, update check,
and the closing/backup/WhatsApp tab.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide2.QtCore import Qt
from PySide2.QtWidgets import QLabel, QScrollArea, QTabWidget, QVBoxLayout, QWidget

from derby.core.i18n import ar
from derby.core.theme.tab_bar import configure_tab_widget
from derby.features.closing.backup_closing_panel import BackupClosingPanel
from derby.features.dashboard.alerts_settings_panel import AlertsSettingsPanel
from derby.features.pos.discount_presets_panel import DiscountPresetsPanel
from derby.features.settings.about_panel import AboutPanel
from derby.features.settings.advanced_tools_panel import AdvancedToolsPanel
from derby.features.settings.general_settings_form import GeneralSettingsForm
from derby.features.settings.update_check_panel import UpdateCheckPanel
from derby.features.settings.users_management import UsersManagementWidget


class _ExtrasPanel(QWidget):
    """One combined tab for the two Phase 11 Part E settings panels --
    kept as a single tab (not two) so the settings tab bar does not grow
    past what fits at the app's minimum window width (1024px); see
    tests/test_tab_bar_and_titles.py.
    """

    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, parent: QWidget = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        self.discount_presets_panel = DiscountPresetsPanel(conn, user)
        self.alerts_settings_panel = AlertsSettingsPanel(conn, user)
        layout.addWidget(self.discount_presets_panel)
        layout.addWidget(self.alerts_settings_panel)
        layout.addStretch(1)
        scroll_area.setWidget(content)
        outer.addWidget(scroll_area)


class SettingsScreen(QWidget):
    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, db_path: Path, parent: QWidget = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        title = QLabel(ar.SETTINGS_TITLE)
        title.setProperty("role", "title")
        layout.addWidget(title)

        tabs = QTabWidget()
        configure_tab_widget(tabs)
        self._general_form = GeneralSettingsForm(conn, user)
        self._users_widget = UsersManagementWidget(conn, user["id"])
        self._update_panel = UpdateCheckPanel(conn)
        self._backup_closing_panel = BackupClosingPanel(conn, user, db_path)
        self._advanced_tools_panel = AdvancedToolsPanel(conn, user, db_path)
        self._extras_panel = _ExtrasPanel(conn, user)
        self._general_form.saved.connect(self._update_panel.reload)

        tabs.addTab(self._general_form, ar.SETTINGS_TAB_GENERAL)
        tabs.addTab(self._users_widget, ar.SETTINGS_TAB_USERS)
        tabs.addTab(self._update_panel, ar.SETTINGS_TAB_UPDATES)
        tabs.addTab(self._backup_closing_panel, ar.CLOSING_SETTINGS_TAB)
        tabs.addTab(self._extras_panel, ar.SETTINGS_TAB_EXTRAS)
        tabs.addTab(AboutPanel(), ar.SETTINGS_TAB_ABOUT)
        tabs.addTab(self._advanced_tools_panel, ar.SETTINGS_TAB_ADVANCED)
        layout.addWidget(tabs)
