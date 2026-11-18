"""QApplication setup and top-level window routing.

Flow: set HiDPI + RTL + bundled font -> single-instance check -> open DB
and run migrations -> show setup screen (first run) or login screen ->
after login, show the main window; locking/logout returns to login.
"""
from __future__ import annotations

import sys

from PySide2.QtCore import Qt
from PySide2.QtGui import QFont
from PySide2.QtWidgets import QApplication, QMessageBox, QStackedWidget

from derby.core.db import settings_repo, users_repo
from derby.core.db.connection import connect
from derby.core.db.migrations import run_pending_migrations
from derby.core.i18n import ar
from derby.core.theme.fonts import FONT_FAMILY, load_bundled_fonts
from derby.core.theme.stylesheet import build_stylesheet
from derby.core.utils.single_instance import SingleInstanceGuard
from derby.features.auth.login_screen import LoginScreen
from derby.features.auth.setup_screen import SetupScreen
from derby.features.expenses import expenses_service
from derby.features.expenses.recurring_due_dialog import RecurringDueDialog
from derby.features.playstation.ps_service import run_startup_consistency_check
from derby.features.shell.idle_filter import IdleTimer
from derby.features.shell.main_window import MainWindow


class AppController:
    """Owns the long-lived windows and switches between them."""

    def __init__(self, app: QApplication, conn) -> None:
        self._app = app
        self._conn = conn
        self._main_window = None

        self._idle_timer = IdleTimer()
        app.installEventFilter(self._idle_timer)

        self._auth_stack = QStackedWidget()
        self._auth_stack.setWindowTitle(ar.APP_TITLE)
        self._auth_stack.resize(420, 640)

        self._login_screen = LoginScreen(conn)
        self._login_screen.login_succeeded.connect(self._on_login_succeeded)

        if users_repo.has_any_users(conn):
            self._auth_stack.addWidget(self._login_screen)
        else:
            setup_screen = SetupScreen(conn)
            setup_screen.setup_completed.connect(self._on_setup_completed)
            self._auth_stack.addWidget(setup_screen)
            self._auth_stack.addWidget(self._login_screen)
            self._auth_stack.setCurrentWidget(setup_screen)

        self._auth_stack.show()

    def _on_setup_completed(self) -> None:
        self._auth_stack.setCurrentWidget(self._login_screen)

    def _on_login_succeeded(self, user) -> None:
        self._main_window = MainWindow(self._conn, user, self._idle_timer)
        self._main_window.lock_requested.connect(self._on_lock_requested)
        self._main_window.resize(1100, 700)
        self._auth_stack.hide()
        self._main_window.show()

        if user["role"] == users_repo.ROLE_OWNER:
            today = expenses_service.today_business_date(self._conn)
            if expenses_service.due_templates_for_month(self._conn, today):
                RecurringDueDialog(self._conn, user, today, parent=self._main_window).exec_()

    def _on_lock_requested(self) -> None:
        if self._main_window is not None:
            self._main_window.hide()
            self._main_window.deleteLater()
            self._main_window = None
        self._auth_stack.show()


def main() -> int:
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.RightToLeft)

    load_bundled_fonts()
    app.setFont(QFont(FONT_FAMILY, 10))
    app.setStyleSheet(build_stylesheet())

    guard = SingleInstanceGuard()
    if not guard.try_acquire():
        QMessageBox.warning(None, ar.ALREADY_RUNNING_TITLE, ar.ALREADY_RUNNING_MESSAGE)
        return 1

    conn = connect()
    run_pending_migrations(conn)
    settings_repo.ensure_defaults(conn)
    run_startup_consistency_check(conn)  # repairs any PlayStation session stopped mid-crash; logs each repair

    controller = AppController(app, conn)
    app.derby_controller = controller  # keep a strong reference alive for the app's lifetime

    return app.exec_()
