"""QApplication setup and top-level window routing.

Flow: apply any staged restore (before the database is even opened) ->
set HiDPI + RTL + bundled font -> single-instance check -> open DB and
run migrations -> show setup screen (first run) or login screen -> after
login, show the main window; locking/logout returns to login. A 30s
scheduler and an exit-time backup safety net run independently of login.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide2.QtCore import QEventLoop, Qt, QTimer
from PySide2.QtGui import QFont, QIcon
from PySide2.QtWidgets import QApplication, QDialog, QLabel, QMessageBox, QStackedWidget, QVBoxLayout

from derby.core.db import audit_repo, settings_repo, users_repo
from derby.core.db.connection import connect
from derby.core.db.migrations import run_pending_migrations
from derby.core.i18n import ar
from derby.core.theme import icons
from derby.core.theme.fonts import CAIRO_FAMILY, load_bundled_fonts
from derby.core.theme.stylesheet import build_stylesheet
from derby.core.utils.paths import app_data_dir, database_path
from derby.core.utils.single_instance import SingleInstanceGuard
from derby.core.utils.time_utils import utc_now
from derby.features.auth.login_screen import LoginScreen
from derby.features.auth.setup_screen import SetupScreen
from derby.features.closing import closing_service, restore_service
from derby.features.closing.closing_worker import ClosingWorker
from derby.features.closing.restore_service import MARKER_FILE_NAME
from derby.features.expenses import expenses_service
from derby.features.expenses.recurring_due_dialog import RecurringDueDialog
from derby.features.playstation.ps_service import run_startup_consistency_check
from derby.features.shell.idle_filter import IdleTimer
from derby.features.shell.main_window import MainWindow

SCHEDULER_INTERVAL_MS = 30_000
EXIT_BACKUP_TIMEOUT_MS = 15_000


class AppController:
    """Owns the long-lived windows and switches between them."""

    def __init__(self, app: QApplication, conn, db_path: Path) -> None:
        self._app = app
        self._conn = conn
        self._db_path = db_path
        self._main_window = None
        self._closing_worker = None

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

        self._scheduler_timer = QTimer(app)
        self._scheduler_timer.timeout.connect(self._on_scheduler_tick)
        self._scheduler_timer.start(SCHEDULER_INTERVAL_MS)
        app.aboutToQuit.connect(self._on_about_to_quit)

        self._run_closing(trigger="catchup")

    def _on_setup_completed(self) -> None:
        self._auth_stack.setCurrentWidget(self._login_screen)

    def _on_login_succeeded(self, user) -> None:
        self._main_window = MainWindow(self._conn, user, self._idle_timer, self._db_path)
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

    # --- closing scheduler ---------------------------------------------

    def _closing_settings(self):
        values = settings_repo.get_all(self._conn)
        enabled = values["closing_enabled"] == "1"
        primary_text = values["backup_folder_primary"].strip()
        secondary_text = values["backup_folder_secondary"].strip()
        primary_dir = Path(primary_text) if primary_text else None
        secondary_dir = Path(secondary_text) if secondary_text else None
        keep_count = int(values["backup_keep_count"] or "30")
        cafe_name = values["cafe_name"] or "ديربي"
        return enabled, primary_dir, secondary_dir, keep_count, cafe_name

    def _on_scheduler_tick(self) -> None:
        self._run_closing(trigger="auto")

    def _run_closing(self, trigger: str) -> None:
        if self._closing_worker is not None and self._closing_worker.isRunning():
            return  # a previous run is still in flight -- skip this tick
        enabled, primary_dir, secondary_dir, keep_count, cafe_name = self._closing_settings()
        if not enabled:
            return

        def work(worker_conn):
            return closing_service.run_due_closures(
                worker_conn, self._db_path, utc_now(), trigger, cafe_name, primary_dir, secondary_dir, keep_count
            )

        self._closing_worker = ClosingWorker(self._db_path, work)
        self._closing_worker.finished_ok.connect(self._on_closing_done)
        self._closing_worker.start()

    def _on_closing_done(self, _closures) -> None:
        if self._main_window is not None:
            main_window = self._main_window
            if getattr(main_window, "_closing_banner", None) is not None:
                main_window._closing_banner.reload()

    # --- exit-time backup safety net ------------------------------------

    def _on_about_to_quit(self) -> None:
        if (app_data_dir() / MARKER_FILE_NAME).exists():
            return  # a restore is staged -- the current database is about to be replaced anyway
        if not closing_service.exit_backup_is_due(self._conn, utc_now()):
            return
        enabled, primary_dir, secondary_dir, keep_count, _cafe_name = self._closing_settings()
        if not enabled or primary_dir is None:
            return

        progress_dialog = QDialog()
        progress_dialog.setWindowTitle(ar.APP_TITLE)
        layout = QVBoxLayout(progress_dialog)
        layout.addWidget(QLabel(ar.CLOSING_EXIT_BACKUP_IN_PROGRESS))
        progress_dialog.show()

        def work(worker_conn):
            return closing_service.run_exit_backup(worker_conn, self._db_path, utc_now(), primary_dir, secondary_dir, keep_count)

        worker = ClosingWorker(self._db_path, work)
        loop = QEventLoop()
        worker.finished_ok.connect(lambda _r: loop.quit())
        worker.finished_error.connect(lambda _e: loop.quit())
        timeout_timer = QTimer()
        timeout_timer.setSingleShot(True)
        timeout_timer.timeout.connect(loop.quit)
        worker.start()
        timeout_timer.start(EXIT_BACKUP_TIMEOUT_MS)
        loop.exec_()
        progress_dialog.close()


def main() -> int:
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.RightToLeft)

    load_bundled_fonts()
    app.setFont(QFont(CAIRO_FAMILY, 10))
    app.setStyleSheet(build_stylesheet())
    icon_pixmap = icons.icon_mark_pixmap("mono-black", 256)
    if not icon_pixmap.isNull():
        app.setWindowIcon(QIcon(icon_pixmap))

    guard = SingleInstanceGuard()
    if not guard.try_acquire():
        QMessageBox.warning(None, ar.ALREADY_RUNNING_TITLE, ar.ALREADY_RUNNING_MESSAGE)
        return 1

    restore_result = restore_service.apply_pending_restore(app_data_dir())

    db_path = database_path()
    conn = connect(db_path)
    run_pending_migrations(conn)
    settings_repo.ensure_defaults(conn)
    run_startup_consistency_check(conn)  # repairs any PlayStation session stopped mid-crash; logs each repair
    closing_service.ensure_first_run_date(conn, utc_now())

    if restore_result is not None:
        action = "db_restored" if restore_result["status"] == "ok" else "db_restore_failed"
        audit_repo.log(conn, action, details="backup_path={0}".format(restore_result["backup_path"]))

    controller = AppController(app, conn, db_path)
    app.derby_controller = controller  # keep a strong reference alive for the app's lifetime

    return app.exec_()
