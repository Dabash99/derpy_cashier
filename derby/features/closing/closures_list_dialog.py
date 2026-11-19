"""Lists every day_closures row: business date, revision, net sales,
backup status, sent/pending, and a stale flag. A selected row can be
rebuilt, viewed, or marked as sent.
"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from PySide2.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from derby.core.db import day_closures_repo, settings_repo
from derby.core.i18n import ar
from derby.core.utils.money import format_egp
from derby.core.utils.paths import default_backup_dir
from derby.features.closing import closing_service
from derby.features.closing.closing_report_viewer_dialog import ClosingReportViewerDialog
from derby.features.reports.report_service import today_business_date


class ClosuresListDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, db_path: Path, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._db_path = db_path
        self._closures_by_row = []
        self.setWindowTitle(ar.CLOSURES_LIST_TITLE)
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            [
                ar.CLOSURES_COLUMN_DATE, ar.CLOSURES_COLUMN_REVISION, ar.CLOSURES_COLUMN_NET_SALES,
                ar.CLOSURES_COLUMN_BACKUP, ar.CLOSURES_COLUMN_SENT,
            ]
        )
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self._table)

        actions_row = QHBoxLayout()
        rebuild_button = QPushButton(ar.CLOSURES_REBUILD_BUTTON)
        rebuild_button.clicked.connect(self._on_rebuild)
        actions_row.addWidget(rebuild_button)
        view_button = QPushButton(ar.CLOSURES_VIEW_TEXT_BUTTON)
        view_button.clicked.connect(self._on_view)
        actions_row.addWidget(view_button)
        mark_sent_button = QPushButton(ar.CLOSURES_MARK_SENT_BUTTON)
        mark_sent_button.clicked.connect(self._on_mark_sent)
        actions_row.addWidget(mark_sent_button)
        layout.addLayout(actions_row)

        close_button = QPushButton(ar.GENERIC_OK)
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)

    def reload(self) -> None:
        closures = day_closures_repo.list_closures(self._conn)
        self._closures_by_row = closures
        self._table.setRowCount(len(closures))
        for row_index, closure in enumerate(closures):
            self._populate_row(row_index, closure)

    def _populate_row(self, row_index: int, closure: sqlite3.Row) -> None:
        backup_text = "{0} / {1}".format(
            closure["backup_primary_status"] or "-", closure["backup_secondary_status"] or "-"
        )
        sent_text = ar.CLOSURES_SENT_LABEL if closure["sent_at_utc"] else ar.CLOSURES_PENDING_LABEL
        if closure["stale"]:
            sent_text = "{0} — {1}".format(sent_text, ar.CLOSURES_STALE_BADGE)
        values = [
            closure["business_date"],
            str(closure["revision"]),
            format_egp(closure["net_sales_piasters"]),
            backup_text,
            sent_text,
        ]
        for column, value in enumerate(values):
            self._table.setItem(row_index, column, QTableWidgetItem(value))

    def _selected_closure(self):
        row = self._table.currentRow()
        if row < 0 or row >= len(self._closures_by_row):
            return None
        return self._closures_by_row[row]

    def _on_rebuild(self) -> None:
        closure = self._selected_closure()
        if closure is None:
            return
        business_date_value = date.fromisoformat(closure["business_date"])
        cafe_name = settings_repo.get(self._conn, "cafe_name", "") or "ديربي"
        primary_text = settings_repo.get(self._conn, "backup_folder_primary", "") or str(default_backup_dir())
        secondary_text = settings_repo.get(self._conn, "backup_folder_secondary", "") or ""
        keep_count = int(settings_repo.get(self._conn, "backup_keep_count", "30") or "30")

        closing_service.close_or_rebuild_day(
            self._conn, self._db_path, business_date_value, "manual", cafe_name, Path(primary_text),
            Path(secondary_text) if secondary_text else None, keep_count, today_business_date(self._conn),
        )
        self.reload()

    def _on_view(self) -> None:
        closure = self._selected_closure()
        if closure is None:
            return
        ClosingReportViewerDialog(closure["report_text"], parent=self).exec_()

    def _on_mark_sent(self) -> None:
        closure = self._selected_closure()
        if closure is None:
            return
        day_closures_repo.mark_sent(self._conn, closure["id"], self._user["id"])
        self.reload()
