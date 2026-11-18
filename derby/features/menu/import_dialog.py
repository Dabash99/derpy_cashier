"""CSV import UI: pick a file, preview NEW/EXISTS/INVALID rows, choose
what to do about existing products, then run the import on a background
thread (with its own DB connection -- SQLite connections aren't safe to
share across threads) so the UI stays responsive.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from PySide2.QtCore import QThread, Signal
from PySide2.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from derby.core.db import audit_repo
from derby.core.db.connection import connect
from derby.core.i18n import ar
from derby.core.utils.money import piasters_to_plain_text
from derby.features.menu.csv_importer import (
    EXISTS_ACTION_SKIP,
    EXISTS_ACTION_UPDATE,
    STATUS_EXISTS,
    STATUS_INVALID,
    STATUS_NEW,
    apply_import,
    classify_rows,
)
from derby.features.menu.csv_parser import CsvFormatError, parse_csv_text

_STATUS_LABELS = {
    STATUS_NEW: ar.MENU_CSV_STATUS_NEW,
    STATUS_EXISTS: ar.MENU_CSV_STATUS_EXISTS,
    STATUS_INVALID: ar.MENU_CSV_STATUS_INVALID,
}


def _connection_db_path(conn: sqlite3.Connection) -> Path:
    row = conn.execute("PRAGMA database_list").fetchone()
    return Path(row[2])


class ImportWorker(QThread):
    progress = Signal(int, int)
    succeeded = Signal(dict)
    failed = Signal(str)

    def __init__(self, db_path: Path, rows, images_folder: Path, exists_action: str, parent=None) -> None:
        super().__init__(parent)
        self._db_path = db_path
        self._rows = rows
        self._images_folder = images_folder
        self._exists_action = exists_action

    def run(self) -> None:
        try:
            worker_conn = connect(self._db_path)
            counts = apply_import(
                worker_conn,
                self._rows,
                self._images_folder,
                self._exists_action,
                progress_callback=lambda index, total: self.progress.emit(index, total),
            )
            worker_conn.close()
        except Exception as error:  # noqa: BLE001 -- reported to the UI, not swallowed
            self.failed.emit(str(error))
            return
        self.succeeded.emit(counts)


class ImportDialog(QDialog):
    import_completed = Signal()

    def __init__(self, conn: sqlite3.Connection, user_id: int, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user_id = user_id
        self._csv_path: Optional[Path] = None
        self._images_folder: Optional[Path] = None
        self._classified_rows = []
        self._worker: Optional[ImportWorker] = None

        self.setWindowTitle(ar.MENU_CSV_IMPORT_TITLE)
        self.resize(700, 500)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        pick_row = QHBoxLayout()
        pick_button = QPushButton(ar.MENU_CSV_PICK_FILE_BUTTON)
        pick_button.clicked.connect(self._on_pick_file)
        pick_row.addWidget(pick_button)
        self._file_label = QLabel("")
        pick_row.addWidget(self._file_label)
        layout.addLayout(pick_row)

        layout.addWidget(QLabel(ar.MENU_CSV_PREVIEW_TITLE))
        self._preview_table = QTableWidget(0, 7)
        self._preview_table.setHorizontalHeaderLabels(
            [
                ar.MENU_CSV_COLUMN_STATUS,
                ar.MENU_CSV_COLUMN_CATEGORY,
                ar.MENU_CSV_COLUMN_NAME_AR,
                ar.MENU_CSV_COLUMN_NAME_EN,
                ar.MENU_CSV_COLUMN_PRICE,
                ar.MENU_CSV_COLUMN_IMAGE,
                ar.MENU_CSV_COLUMN_NOTE,
            ]
        )
        self._preview_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self._preview_table)

        self._exists_action_input = QComboBox()
        self._exists_action_input.addItem(ar.MENU_CSV_EXISTS_OPTION_SKIP, EXISTS_ACTION_SKIP)
        self._exists_action_input.addItem(ar.MENU_CSV_EXISTS_OPTION_UPDATE, EXISTS_ACTION_UPDATE)
        layout.addWidget(self._exists_action_input)

        self._progress_bar = QProgressBar()
        self._progress_bar.hide()
        layout.addWidget(self._progress_bar)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        self._import_button = QPushButton(ar.MENU_CSV_IMPORT_CONFIRM_BUTTON)
        self._import_button.setEnabled(False)
        self._import_button.clicked.connect(self._on_start_import)
        layout.addWidget(self._import_button)

    def _on_pick_file(self) -> None:
        file_path, _filter = QFileDialog.getOpenFileName(self, ar.MENU_CSV_PICK_FILE_BUTTON, "", "CSV (*.csv)")
        if not file_path:
            return
        self._csv_path = Path(file_path)
        self._images_folder = self._csv_path.parent / "images"
        self._file_label.setText(str(self._csv_path))
        self._load_preview()

    def _load_preview(self) -> None:
        try:
            text = self._csv_path.read_text(encoding="utf-8-sig")
        except OSError:
            self._status_label.setText(ar.MENU_CSV_ERROR_CANNOT_READ)
            return
        try:
            raw_rows = parse_csv_text(text)
        except CsvFormatError as error:
            self._status_label.setText(str(error))
            return

        self._classified_rows = classify_rows(self._conn, raw_rows, self._images_folder)
        self._populate_preview_table()
        self._import_button.setEnabled(len(self._classified_rows) > 0)
        self._status_label.setText("")

    def _populate_preview_table(self) -> None:
        self._preview_table.setRowCount(len(self._classified_rows))
        for row_index, row in enumerate(self._classified_rows):
            price_text = piasters_to_plain_text(row.price_piasters) if row.price_piasters is not None else ""
            values = [
                _STATUS_LABELS[row.status],
                row.category_name,
                row.name_ar,
                row.name_en,
                price_text,
                row.image_file or "",
                row.note,
            ]
            for column, value in enumerate(values):
                self._preview_table.setItem(row_index, column, QTableWidgetItem(value))

    def _on_start_import(self) -> None:
        if not self._classified_rows:
            self._status_label.setText(ar.MENU_CSV_ERROR_NO_FILE)
            return

        self._import_button.setEnabled(False)
        self._progress_bar.setRange(0, len(self._classified_rows))
        self._progress_bar.setValue(0)
        self._progress_bar.show()
        self._status_label.setText(ar.MENU_CSV_IMPORTING_PROGRESS)

        db_path = _connection_db_path(self._conn)
        exists_action = self._exists_action_input.currentData()
        self._worker = ImportWorker(db_path, self._classified_rows, self._images_folder, exists_action, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.succeeded.connect(self._on_succeeded)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, index: int, _total: int) -> None:
        self._progress_bar.setValue(index)

    def _on_succeeded(self, counts: dict) -> None:
        self._progress_bar.hide()
        self._status_label.setText(
            ar.MENU_CSV_IMPORT_SUMMARY.format(
                new_count=counts["new"],
                updated_count=counts["updated"],
                skipped_count=counts["skipped"],
                invalid_count=counts["invalid"],
                missing_images_count=counts["missing_images"],
            )
        )
        audit_repo.log(self._conn, "menu_csv_import", user_id=self._user_id, details=str(counts))
        self._import_button.setEnabled(True)
        self.import_completed.emit()

    def _on_failed(self, message: str) -> None:
        self._progress_bar.hide()
        self._status_label.setText(message)
        self._import_button.setEnabled(True)
