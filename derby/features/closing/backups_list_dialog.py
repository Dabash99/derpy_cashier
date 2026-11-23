"""Part B: "عرض النسخ الاحتياطية" -- lists every backup_log row (primary
and secondary, daily/manual/monthly-tagged-as-daily/exit) with its
date, target, size, app/schema version, and verified flag, plus two
actions: open the folder a selected row's file lives in, and manually
re-apply the current retention policy to both configured folders.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional

from PySide2.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
)

from derby.core import audit_service
from derby.core.db import backup_log_repo, settings_repo
from derby.core.i18n import ar
from derby.core.theme.table_style import centered_item, configure_table, right_item
from derby.core.utils.time_utils import parse_utc_iso, to_cairo
from derby.features.closing import backup_service

_TARGET_LABELS = {"primary": ar.BACKUPS_LIST_TARGET_PRIMARY, "secondary": ar.BACKUPS_LIST_TARGET_SECONDARY}


def _format_size(size_bytes: Optional[int]) -> str:
    if not size_bytes:
        return ""
    kb = size_bytes / 1024
    if kb < 1024:
        return "{0:.0f} ك.ب".format(kb)
    return "{0:.1f} م.ب".format(kb / 1024)


class BackupsListDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._rows_by_index = []
        self.setWindowTitle(ar.BACKUPS_LIST_TITLE)
        self.resize(760, 480)
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(
            [
                ar.BACKUPS_LIST_COLUMN_TIME, ar.BACKUPS_LIST_COLUMN_TARGET, ar.BACKUPS_LIST_COLUMN_KIND,
                ar.BACKUPS_LIST_COLUMN_SIZE, ar.BACKUPS_LIST_COLUMN_APP_VERSION,
                ar.BACKUPS_LIST_COLUMN_SCHEMA_VERSION, ar.BACKUPS_LIST_COLUMN_VERIFIED,
            ]
        )
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        configure_table(self._table, stretch_columns=(0,), fixed_widths={1: 80, 2: 80, 3: 90, 4: 100, 5: 100, 6: 80})
        layout.addWidget(self._table)

        actions_row = QHBoxLayout()
        open_folder_button = QPushButton(ar.BACKUPS_LIST_OPEN_FOLDER_BUTTON)
        open_folder_button.clicked.connect(self._on_open_folder)
        actions_row.addWidget(open_folder_button)
        cleanup_button = QPushButton(ar.BACKUPS_LIST_CLEANUP_BUTTON)
        cleanup_button.clicked.connect(self._on_cleanup)
        actions_row.addWidget(cleanup_button)
        layout.addLayout(actions_row)

        self._message_label = QLabel("")
        self._message_label.setWordWrap(True)
        layout.addWidget(self._message_label)

    def reload(self) -> None:
        rows = backup_log_repo.list_backups(self._conn, limit=500)
        self._rows_by_index = rows
        self._table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            cairo_time = to_cairo(parse_utc_iso(row["at_utc"])).strftime("%Y-%m-%d %H:%M")
            makers = [right_item, centered_item, centered_item, centered_item, centered_item, centered_item, centered_item]
            values = [
                cairo_time,
                _TARGET_LABELS.get(row["target"], row["target"]),
                row["kind"],
                _format_size(row["size_bytes"]),
                row["app_version"] or "",
                str(row["schema_version"]) if row["schema_version"] is not None else "",
                ar.BACKUPS_LIST_VERIFIED_YES if row["verified"] else ar.BACKUPS_LIST_VERIFIED_NO,
            ]
            for column, (value, make_item) in enumerate(zip(values, makers)):
                self._table.setItem(row_index, column, make_item(value))
        if not rows:
            self._message_label.setText(ar.BACKUPS_LIST_EMPTY)

    def _selected_row(self) -> Optional[sqlite3.Row]:
        row_index = self._table.currentRow()
        if 0 <= row_index < len(self._rows_by_index):
            return self._rows_by_index[row_index]
        return None

    def _on_open_folder(self) -> None:
        row = self._selected_row()
        if row is None or not row["path"]:
            return
        folder = Path(row["path"]).parent
        if hasattr(os, "startfile") and folder.exists():
            os.startfile(str(folder))  # noqa: S606 -- opens Explorer on a local folder, Windows-only

    def _on_cleanup(self) -> None:
        values = settings_repo.get_all(self._conn)
        keep_daily = int(values.get("backup_keep_count") or "30")
        keep_monthly = int(values.get("backup_monthly_keep_count") or "12")
        primary_dir = Path(values["backup_folder_primary"]) if values.get("backup_folder_primary") else None
        secondary_dir = Path(values["backup_folder_secondary"]) if values.get("backup_folder_secondary") else None

        deleted = backup_service.apply_retention_policy(primary_dir, keep_daily, keep_monthly)
        deleted += backup_service.apply_retention_policy(secondary_dir, keep_daily, keep_monthly)

        self._message_label.setText(ar.BACKUPS_LIST_CLEANUP_RESULT.format(count=deleted))
        audit_service.log(
            self._conn, "backup_retention_cleanup", user=self._user, entity_type="backup",
            summary_ar=ar.BACKUPS_LIST_CLEANUP_RESULT.format(count=deleted),
            details={"deleted": deleted, "keep_daily": keep_daily, "keep_monthly": keep_monthly},
        )
        QMessageBox.information(self, ar.BACKUPS_LIST_CLEANUP_BUTTON, self._message_label.text())
