"""Settings tab "النسخ الاحتياطي والإقفال" (owner only): the closing/
backup/WhatsApp settings, a status block, and the action buttons (backup
now, close today, retry secondary, restore, closures list). Every
backup/closing action runs on a ClosingWorker so the UI never freezes.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from PySide2.QtCore import Signal
from PySide2.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from derby.core.db import backup_log_repo, day_closures_repo, settings_repo
from derby.core.i18n import ar
from derby.core.integrations import whatsapp
from derby.core.utils.time_utils import parse_utc_iso, to_cairo, utc_now
from derby.features.closing import backup_service, closing_service
from derby.features.closing.closing_worker import ClosingWorker
from derby.features.closing.closures_list_dialog import ClosuresListDialog
from derby.features.closing.restore_dialog import RestoreDialog


class BackupClosingPanel(QWidget):
    closed_today = Signal()  # tells the main window to refresh its banner

    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, db_path: Path, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._db_path = db_path
        self._worker: Optional[ClosingWorker] = None
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        form = QFormLayout()
        outer.addLayout(form)

        self._enable_checkbox = QCheckBox(ar.CLOSING_ENABLE_LABEL)
        form.addRow(self._enable_checkbox)

        self._keep_count_input = QSpinBox()
        self._keep_count_input.setRange(1, 365)
        form.addRow(ar.CLOSING_KEEP_COUNT_LABEL, self._keep_count_input)

        self._whatsapp_number_input = QLineEdit()
        self._whatsapp_number_input.textChanged.connect(self._update_whatsapp_hint)
        form.addRow(ar.CLOSING_WHATSAPP_NUMBER_LABEL, self._whatsapp_number_input)
        self._whatsapp_hint_label = QLabel("")
        form.addRow("", self._whatsapp_hint_label)

        self._whatsapp_method_input = QComboBox()
        self._whatsapp_method_input.addItem(ar.CLOSING_WHATSAPP_METHOD_DESKTOP, whatsapp.METHOD_DESKTOP)
        self._whatsapp_method_input.addItem(ar.CLOSING_WHATSAPP_METHOD_BROWSER, whatsapp.METHOD_BROWSER)
        self._whatsapp_method_input.addItem(ar.CLOSING_WHATSAPP_METHOD_COPY, whatsapp.METHOD_COPY)
        form.addRow(ar.CLOSING_WHATSAPP_METHOD_LABEL, self._whatsapp_method_input)

        self._primary_input, primary_row = self._build_folder_row()
        form.addRow(ar.CLOSING_BACKUP_PRIMARY_LABEL, primary_row)
        self._secondary_input, secondary_row = self._build_folder_row()
        form.addRow(ar.CLOSING_BACKUP_SECONDARY_LABEL, secondary_row)

        self._same_drive_label = QLabel("")
        self._same_drive_label.setProperty("role", "error")
        outer.addWidget(self._same_drive_label)

        self._error_label = QLabel("")
        self._error_label.setProperty("role", "error")
        self._error_label.setWordWrap(True)
        outer.addWidget(self._error_label)

        save_button = QPushButton(ar.GENERIC_SAVE)
        save_button.clicked.connect(self._on_save)
        outer.addWidget(save_button)

        outer.addWidget(QLabel(ar.CLOSING_STATUS_TITLE))
        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        outer.addWidget(self._status_label)

        actions_row = QHBoxLayout()
        self._backup_now_button = QPushButton(ar.CLOSING_BACKUP_NOW_BUTTON)
        self._backup_now_button.clicked.connect(self._on_backup_now)
        actions_row.addWidget(self._backup_now_button)
        self._close_today_button = QPushButton(ar.CLOSING_CLOSE_TODAY_BUTTON)
        self._close_today_button.setProperty("variant", "primary")
        self._close_today_button.clicked.connect(self._on_close_today)
        actions_row.addWidget(self._close_today_button)
        self._retry_secondary_button = QPushButton(ar.CLOSING_RETRY_SECONDARY_BUTTON)
        self._retry_secondary_button.clicked.connect(self._on_retry_secondary)
        actions_row.addWidget(self._retry_secondary_button)
        restore_button = QPushButton(ar.CLOSING_RESTORE_BUTTON)
        restore_button.clicked.connect(self._on_restore)
        actions_row.addWidget(restore_button)
        list_button = QPushButton(ar.CLOSING_LIST_BUTTON)
        list_button.clicked.connect(self._on_open_list)
        actions_row.addWidget(list_button)
        outer.addLayout(actions_row)

    def _build_folder_row(self):
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        folder_input = QLineEdit()
        folder_input.textChanged.connect(self._update_same_drive_warning)
        browse_button = QPushButton("...")
        browse_button.setFixedWidth(40)
        browse_button.clicked.connect(lambda: self._browse_folder(folder_input))
        test_button = QPushButton(ar.CLOSING_TEST_FOLDER_BUTTON)
        test_button.clicked.connect(lambda: self._on_test_folder(folder_input))
        row_layout.addWidget(folder_input)
        row_layout.addWidget(browse_button)
        row_layout.addWidget(test_button)
        return folder_input, row_widget

    def _browse_folder(self, target_input: QLineEdit) -> None:
        chosen = QFileDialog.getExistingDirectory(self, ar.CLOSING_BACKUP_PRIMARY_LABEL, target_input.text())
        if chosen:
            target_input.setText(chosen)

    def _on_test_folder(self, target_input: QLineEdit) -> None:
        text = target_input.text().strip()
        if not text:
            return
        ok = backup_service.test_folder_writable(Path(text))
        QMessageBox.information(
            self, ar.CLOSING_TEST_FOLDER_BUTTON, ar.CLOSING_TEST_FOLDER_SUCCESS if ok else ar.CLOSING_TEST_FOLDER_FAILED
        )

    def _update_whatsapp_hint(self) -> None:
        hint = whatsapp.egypt_local_hint(self._whatsapp_number_input.text())
        self._whatsapp_hint_label.setText(hint or "")

    def _update_same_drive_warning(self) -> None:
        primary = self._primary_input.text().strip()
        secondary = self._secondary_input.text().strip()
        if primary and secondary and backup_service.same_drive(Path(primary), Path(secondary)):
            self._same_drive_label.setText(ar.CLOSING_SAME_DRIVE_WARNING)
        else:
            self._same_drive_label.setText("")

    # --- load / save settings -----------------------------------------

    def reload(self) -> None:
        values = settings_repo.get_all(self._conn)
        self._enable_checkbox.setChecked(values["closing_enabled"] == "1")
        self._keep_count_input.setValue(int(values["backup_keep_count"]))
        self._whatsapp_number_input.setText(values["whatsapp_number"])
        index = self._whatsapp_method_input.findData(values["whatsapp_method"])
        if index >= 0:
            self._whatsapp_method_input.setCurrentIndex(index)
        self._primary_input.setText(values["backup_folder_primary"])
        self._secondary_input.setText(values["backup_folder_secondary"])
        self._error_label.setText("")
        self._refresh_status()

    def _refresh_status(self, leading_message: Optional[str] = None) -> None:
        last_primary = backup_log_repo.last_verified_backup(self._conn, "primary")
        last_secondary = backup_log_repo.last_verified_backup(self._conn, "secondary")
        last_closure = day_closures_repo.get_last_closure(self._conn)
        lines = [
            ar.CLOSING_LAST_BACKUP_PRIMARY.format(text=self._format_backup_row(last_primary)),
            ar.CLOSING_LAST_BACKUP_SECONDARY.format(text=self._format_backup_row(last_secondary)),
            ar.CLOSING_LAST_CLOSURE.format(text=last_closure["business_date"] if last_closure is not None else ar.CLOSING_NO_BACKUP_YET),
        ]
        if leading_message:
            lines.insert(0, leading_message)
        self._status_label.setText("\n".join(lines))

    @staticmethod
    def _format_backup_row(row: Optional[sqlite3.Row]) -> str:
        if row is None:
            return ar.CLOSING_NO_BACKUP_YET
        cairo_time = to_cairo(parse_utc_iso(row["at_utc"])).strftime("%Y-%m-%d %H:%M")
        size_kb = (row["size_bytes"] or 0) // 1024
        return "{0} ({1} ك.ب)".format(cairo_time, size_kb)

    def _on_save(self) -> None:
        number = self._whatsapp_number_input.text().strip()
        if number:
            is_valid, error = whatsapp.validate_number(number)
            if not is_valid:
                self._error_label.setText(error)
                return

        settings_repo.set_value(self._conn, "closing_enabled", "1" if self._enable_checkbox.isChecked() else "0")
        settings_repo.set_value(self._conn, "backup_keep_count", str(self._keep_count_input.value()))
        settings_repo.set_value(self._conn, "whatsapp_number", number)
        settings_repo.set_value(self._conn, "whatsapp_method", self._whatsapp_method_input.currentData())
        settings_repo.set_value(self._conn, "backup_folder_primary", self._primary_input.text().strip())
        settings_repo.set_value(self._conn, "backup_folder_secondary", self._secondary_input.text().strip())
        self._error_label.setText("")

    # --- actions (all via ClosingWorker) --------------------------------

    def _primary_dir(self) -> Optional[Path]:
        text = self._primary_input.text().strip()
        return Path(text) if text else None

    def _secondary_dir(self) -> Optional[Path]:
        text = self._secondary_input.text().strip()
        return Path(text) if text else None

    def _cafe_name(self) -> str:
        return settings_repo.get(self._conn, "cafe_name", "") or "ديربي"

    def _set_buttons_enabled(self, enabled: bool) -> None:
        self._backup_now_button.setEnabled(enabled)
        self._close_today_button.setEnabled(enabled)
        self._retry_secondary_button.setEnabled(enabled)

    def _run_worker(self, work_fn, on_done) -> None:
        self._set_buttons_enabled(False)
        self._error_label.setText("")
        self._status_label.setText(ar.CLOSING_WORKING)
        worker = ClosingWorker(self._db_path, work_fn)
        worker.finished_ok.connect(lambda result: self._on_worker_ok(result, on_done))
        worker.finished_error.connect(self._on_worker_error)
        self._worker = worker
        worker.start()

    def _on_worker_ok(self, result, on_done) -> None:
        self._set_buttons_enabled(True)
        on_done(result)

    def _on_worker_error(self, message: str) -> None:
        self._set_buttons_enabled(True)
        self._error_label.setText(message)
        self._refresh_status()

    def _on_backup_now(self) -> None:
        primary_dir, secondary_dir = self._primary_dir(), self._secondary_dir()

        def work(conn):
            return closing_service.run_manual_backup(conn, self._db_path, utc_now(), primary_dir, secondary_dir)

        self._run_worker(work, self._on_backup_done)

    def _on_backup_done(self, result) -> None:
        primary, _secondary = result
        message = ar.CLOSING_BACKUP_SUCCESS if primary.status == "ok" else ar.CLOSING_BACKUP_FAILED.format(error=primary.error or "")
        self._refresh_status(leading_message=message)

    def _on_close_today(self) -> None:
        primary_dir, secondary_dir = self._primary_dir(), self._secondary_dir()
        cafe_name = self._cafe_name()
        keep_count = self._keep_count_input.value()

        def work(conn):
            _closure, already_existed = closing_service.close_today_manually(
                conn, self._db_path, utc_now(), cafe_name, primary_dir, secondary_dir, keep_count
            )
            return already_existed

        self._run_worker(work, self._on_close_today_done)

    def _on_close_today_done(self, already_existed: bool) -> None:
        message = ar.CLOSING_MANUAL_CLOSURE_ALREADY_DONE if already_existed else ar.CLOSING_MANUAL_CLOSURE_SUCCESS
        self._refresh_status(leading_message=message)
        self.closed_today.emit()

    def _on_retry_secondary(self) -> None:
        secondary_dir = self._secondary_dir()
        if secondary_dir is None:
            return
        keep_count = self._keep_count_input.value()

        def work(conn):
            return closing_service.retry_secondary_backup(conn, self._db_path, secondary_dir, keep_count)

        self._run_worker(work, self._on_retry_secondary_done)

    def _on_retry_secondary_done(self, outcome) -> None:
        message = ar.CLOSING_BACKUP_SUCCESS if outcome.status == "ok" else ar.CLOSING_BACKUP_FAILED.format(error=outcome.error or "")
        self._refresh_status(leading_message=message)

    def _on_restore(self) -> None:
        dialog = RestoreDialog(self._conn, self._user, self._primary_dir(), parent=self)
        if dialog.exec_() == dialog.Accepted:
            QMessageBox.information(self, ar.RESTORE_TITLE, ar.RESTORE_SUCCESS_RESTART)
            app = QApplication.instance()
            if app is not None:
                app.quit()

    def _on_open_list(self) -> None:
        dialog = ClosuresListDialog(self._conn, self._user, self._db_path, parent=self)
        dialog.exec_()
        self._refresh_status()
