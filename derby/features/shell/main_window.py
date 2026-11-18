"""The logged-in main window: header + sidebar + a content area that
swaps between the feature screens the current role is allowed to see.
"""
from __future__ import annotations

import sqlite3

from PySide2.QtCore import Signal
from PySide2.QtWidgets import QHBoxLayout, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from derby.core.db import settings_repo
from derby.features.menu.menu_screen import MenuScreen
from derby.features.settings.settings_screen import SettingsScreen
from derby.features.shell.header import Header
from derby.features.shell.idle_filter import IdleTimer
from derby.features.shell.placeholder_screen import PlaceholderScreen
from derby.features.shell.sidebar import SECTIONS, Sidebar


class MainWindow(QMainWindow):
    lock_requested = Signal()

    def __init__(
        self,
        conn: sqlite3.Connection,
        user: sqlite3.Row,
        idle_timer: IdleTimer,
        parent: QWidget = None,
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._idle_timer = idle_timer
        self._screens = {}

        cafe_name = settings_repo.get(conn, "cafe_name", "") or ""
        self._header = Header(cafe_name, user["name"], user["role"])
        self._header.lock_requested.connect(self._on_lock_requested)

        self._sidebar = Sidebar(user["role"])
        self._sidebar.navigate.connect(self._on_navigate)

        self._content_stack = QStackedWidget()
        self._build_screens()

        central = QWidget()
        outer_layout = QVBoxLayout(central)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        outer_layout.addWidget(self._header)

        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(self._content_stack, 1)
        body_layout.addWidget(self._sidebar)
        outer_layout.addLayout(body_layout)

        self.setCentralWidget(central)
        self._navigate_to_default()

        self._idle_timer.idle_timeout.connect(self._on_lock_requested)
        self._idle_timer.set_timeout_minutes(int(settings_repo.get(conn, "auto_lock_minutes", "10")))
        self._idle_timer.start()

    def _build_screens(self) -> None:
        for key, _label, phase, allowed in SECTIONS:
            if not allowed(self._user["role"]):
                continue
            if key == "settings":
                widget = SettingsScreen(self._conn, self._user["id"])
            elif key == "menu":
                widget = MenuScreen(self._conn, self._user["id"])
            else:
                widget = PlaceholderScreen(phase)
            self._content_stack.addWidget(widget)
            self._screens[key] = widget

    def _on_navigate(self, key: str) -> None:
        widget = self._screens.get(key)
        if widget is not None:
            self._content_stack.setCurrentWidget(widget)
            self._sidebar.set_active(key)

    def _navigate_to_default(self) -> None:
        for key, _label, _phase, _allowed in SECTIONS:
            if key in self._screens:
                self._on_navigate(key)
                return

    def _on_lock_requested(self) -> None:
        self._idle_timer.stop()
        self.lock_requested.emit()
