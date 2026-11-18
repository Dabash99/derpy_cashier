"""Owner-only Settings screen: general settings, users, update check."""
from __future__ import annotations

import sqlite3

from PySide2.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

from derby.core.i18n import ar
from derby.features.settings.general_settings_form import GeneralSettingsForm
from derby.features.settings.update_check_panel import UpdateCheckPanel
from derby.features.settings.users_management import UsersManagementWidget


class SettingsScreen(QWidget):
    def __init__(self, conn: sqlite3.Connection, current_user_id: int, parent: QWidget = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        title = QLabel(ar.SETTINGS_TITLE)
        title.setProperty("role", "title")
        layout.addWidget(title)

        tabs = QTabWidget()
        self._general_form = GeneralSettingsForm(conn)
        self._users_widget = UsersManagementWidget(conn, current_user_id)
        self._update_panel = UpdateCheckPanel(conn)
        self._general_form.saved.connect(self._update_panel.reload)

        tabs.addTab(self._general_form, ar.SETTINGS_TAB_GENERAL)
        tabs.addTab(self._users_widget, ar.SETTINGS_TAB_USERS)
        tabs.addTab(self._update_panel, ar.SETTINGS_TAB_UPDATES)
        layout.addWidget(tabs)
