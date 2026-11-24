"""سجل العمليات (owner only): a filtered, paged view over audit_log.
Pagination (not "load everything") is deliberate -- a mature cafe's
audit_log can reach six figures of rows (every sale, discount, drawer
move, stock change...), and loading all of them into one QTableWidget
would freeze a weak Windows 7 PC. Export uses the SAME filters but
fetches every matching row (via a worker thread), not just the current
page -- a backup/review export must be complete.
"""
from __future__ import annotations

import sqlite3
from datetime import timedelta

from PySide2.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from derby.core.db import audit_repo, users_repo
from derby.core.i18n import ar
from derby.core.theme.table_style import centered_item, configure_table, mark_as_danger, right_item
from derby.core.utils.screen_refresh import RefreshOnChangeMixin
from derby.core.utils.time_utils import parse_utc_iso, to_cairo, utc_now
from derby.features.audit.action_labels import label_for_action
from derby.features.audit.audit_detail_dialog import AuditDetailDialog
from derby.features.reports import export_service
from derby.features.reports.export_panel import ExportPanel

PAGE_SIZE = 50
_SEVERITY_LABELS = {
    "info": ar.AUDIT_LOG_SEVERITY_INFO,
    "warning": ar.AUDIT_LOG_SEVERITY_WARNING,
    "critical": ar.AUDIT_LOG_SEVERITY_CRITICAL,
}


class AuditLogScreen(RefreshOnChangeMixin, QWidget):
    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._page = 0
        self._entries_by_row = []
        self._build_ui()
        self.reload()
        self._init_refresh_on_change()

    # --- UI ---------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel(ar.AUDIT_LOG_TITLE)
        title.setProperty("role", "title")
        layout.addWidget(title)

        filters_row = QHBoxLayout()
        today = to_cairo(utc_now()).date()
        filters_row.addWidget(QLabel(ar.AUDIT_LOG_FROM_DATE_LABEL))
        self._from_date_input = QLineEdit((today - timedelta(days=30)).isoformat())
        self._from_date_input.editingFinished.connect(self._on_filters_changed)
        filters_row.addWidget(self._from_date_input)

        filters_row.addWidget(QLabel(ar.AUDIT_LOG_TO_DATE_LABEL))
        self._to_date_input = QLineEdit(today.isoformat())
        self._to_date_input.editingFinished.connect(self._on_filters_changed)
        filters_row.addWidget(self._to_date_input)

        filters_row.addWidget(QLabel(ar.AUDIT_LOG_USER_LABEL))
        self._user_filter = QComboBox()
        self._user_filter.addItem(ar.AUDIT_LOG_FILTER_ALL, None)
        for row in users_repo.list_users(self._conn):
            self._user_filter.addItem(row["name"], row["id"])
        self._user_filter.currentIndexChanged.connect(self._on_filters_changed)
        filters_row.addWidget(self._user_filter)

        filters_row.addWidget(QLabel(ar.AUDIT_LOG_ACTION_LABEL))
        self._action_filter = QComboBox()
        self._action_filter.addItem(ar.AUDIT_LOG_FILTER_ALL, None)
        for action in audit_repo.distinct_actions(self._conn):
            self._action_filter.addItem(label_for_action(action), action)
        self._action_filter.currentIndexChanged.connect(self._on_filters_changed)
        filters_row.addWidget(self._action_filter)

        filters_row.addWidget(QLabel(ar.AUDIT_LOG_SEVERITY_LABEL))
        self._severity_filter = QComboBox()
        self._severity_filter.addItem(ar.AUDIT_LOG_FILTER_ALL, None)
        self._severity_filter.addItem(ar.AUDIT_LOG_SEVERITY_INFO, "info")
        self._severity_filter.addItem(ar.AUDIT_LOG_SEVERITY_WARNING, "warning")
        self._severity_filter.addItem(ar.AUDIT_LOG_SEVERITY_CRITICAL, "critical")
        self._severity_filter.currentIndexChanged.connect(self._on_filters_changed)
        filters_row.addWidget(self._severity_filter)
        layout.addLayout(filters_row)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel(ar.AUDIT_LOG_SEARCH_LABEL))
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(ar.AUDIT_LOG_SEARCH_PLACEHOLDER)
        self._search_input.editingFinished.connect(self._on_filters_changed)
        search_row.addWidget(self._search_input)
        layout.addLayout(search_row)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            [
                ar.AUDIT_LOG_COLUMN_TIME, ar.AUDIT_LOG_COLUMN_USER, ar.AUDIT_LOG_COLUMN_ACTION,
                ar.AUDIT_LOG_COLUMN_ENTITY, ar.AUDIT_LOG_COLUMN_SUMMARY, ar.AUDIT_LOG_COLUMN_SEVERITY,
            ]
        )
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.cellDoubleClicked.connect(self._on_row_double_clicked)
        configure_table(self._table, stretch_columns=(4,), fixed_widths={0: 130, 1: 110, 2: 160, 3: 110, 5: 70})
        layout.addWidget(self._table)

        pager_row = QHBoxLayout()
        self._result_count_label = QLabel("")
        pager_row.addWidget(self._result_count_label)
        pager_row.addStretch(1)
        self._prev_button = QPushButton(ar.AUDIT_LOG_PREV_PAGE)
        self._prev_button.clicked.connect(self._on_prev_page)
        pager_row.addWidget(self._prev_button)
        self._page_label = QLabel("")
        pager_row.addWidget(self._page_label)
        self._next_button = QPushButton(ar.AUDIT_LOG_NEXT_PAGE)
        self._next_button.clicked.connect(self._on_next_page)
        pager_row.addWidget(self._next_button)
        layout.addLayout(pager_row)

        self._export_entries = []
        self._export_panel = ExportPanel(lambda: "سجل-العمليات-{0}".format(to_cairo(utc_now()).strftime("%Y%m%d-%H%M")))
        self._export_panel.set_exporters(
            csv_fn=self._export_csv, xlsx_fn=self._export_xlsx, before_export_fn=self._prepare_export_entries
        )
        layout.addWidget(self._export_panel)

    # --- filters / query ----------------------------------------------------

    def _current_filters(self) -> dict:
        return {
            "start_date": self._from_date_input.text().strip() or None,
            "end_date": self._to_date_input.text().strip() or None,
            "user_id": self._user_filter.currentData(),
            "action": self._action_filter.currentData(),
            "severity": self._severity_filter.currentData(),
            "search_text": self._search_input.text().strip() or None,
        }

    def _on_filters_changed(self) -> None:
        self._page = 0
        self.reload()

    def reload(self) -> None:
        filters = self._current_filters()
        total = audit_repo.count_entries(self._conn, **filters)
        total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        self._page = min(self._page, total_pages - 1)
        entries = audit_repo.list_entries(self._conn, page=self._page, page_size=PAGE_SIZE, **filters)

        self._entries_by_row = entries
        self._table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            self._populate_row(row, entry)

        self._result_count_label.setText(ar.AUDIT_LOG_RESULT_COUNT.format(count=total))
        self._page_label.setText(ar.AUDIT_LOG_PAGE_LABEL.format(page=self._page + 1, total=total_pages))
        self._prev_button.setEnabled(self._page > 0)
        self._next_button.setEnabled(self._page + 1 < total_pages)

    def _populate_row(self, row: int, entry: sqlite3.Row) -> None:
        cairo_time = to_cairo(parse_utc_iso(entry["at_utc"])).strftime("%Y-%m-%d %H:%M")
        entity_text = "{0} #{1}".format(entry["entity_type"], entry["entity_id"]) if entry["entity_type"] else ""
        severity_text = _SEVERITY_LABELS.get(entry["severity"], entry["severity"])
        makers = [centered_item, right_item, right_item, centered_item, right_item, centered_item]
        values = [
            cairo_time,
            entry["user_name"] or "",
            label_for_action(entry["action"]),
            entity_text,
            entry["summary_ar"] or entry["details"] or "",
            severity_text,
        ]
        for column, (value, make_item) in enumerate(zip(values, makers)):
            item = make_item(value)
            if entry["severity"] == "critical":
                item = mark_as_danger(item)
            self._table.setItem(row, column, item)

    def _on_prev_page(self) -> None:
        if self._page > 0:
            self._page -= 1
            self.reload()

    def _on_next_page(self) -> None:
        self._page += 1
        self.reload()

    def _on_row_double_clicked(self, row: int, _column: int) -> None:
        if 0 <= row < len(self._entries_by_row):
            AuditDetailDialog(self._entries_by_row[row], parent=self).exec_()

    # --- export (every matching row, not just the current page) -----------
    #
    # _prepare_export_entries runs synchronously on the MAIN thread (see
    # export_panel.ExportPanel.set_exporters' before_export_fn) and is the
    # only place here that reads self._conn for export purposes; _export_csv/
    # _export_xlsx then run on the background worker thread against the
    # already-fetched, plain-Python self._export_entries list only.

    def _prepare_export_entries(self) -> None:
        filters = self._current_filters()
        total = audit_repo.count_entries(self._conn, **filters)
        self._export_entries = audit_repo.list_entries(self._conn, page=0, page_size=max(total, 1), **filters)

    def _export_csv(self, path) -> None:
        export_service.write_csv_sections(export_service.audit_log_sections(self._export_entries), path)

    def _export_xlsx(self, path) -> None:
        export_service.write_xlsx_sections(export_service.audit_log_sections(self._export_entries), path)
