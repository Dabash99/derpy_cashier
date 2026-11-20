"""Owner-only banner at the top of the main window: one row per pending
(unsent) closure, plus a warning line if the primary backup looks too
old. Stays until "تم الإرسال" is pressed -- the app has no way to know
whether a message was actually sent.
"""
from __future__ import annotations

import sqlite3

from PySide2.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from derby.core.db import day_closures_repo, settings_repo
from derby.core.i18n import ar
from derby.core.integrations import whatsapp
from derby.core.theme.styled import enable_styled_background
from derby.core.utils.time_utils import utc_now
from derby.features.closing import closing_service
from derby.features.closing.closing_report_viewer_dialog import ClosingReportViewerDialog


class ClosingBannerWidget(QWidget):
    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setObjectName("ClosingBanner")
        self.setProperty("variant", "banner")
        enable_styled_background(self)
        self._conn = conn
        self._user = user
        self._status_label_by_closure_id = {}
        self._rows_layout = QVBoxLayout(self)
        self._rows_layout.setContentsMargins(12, 8, 12, 8)
        self._rows_layout.setSpacing(4)
        self.reload()
        self.setVisible(self._rows_layout.count() > 0)

    def reload(self) -> None:
        self._reload_rows()
        self.setVisible(self._rows_layout.count() > 0)

    def _reload_rows(self) -> None:
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            if item.widget():
                # Hide immediately -- deleteLater() alone leaves the old
                # widget visible (and still positioned where it was)
                # until Qt actually processes the deferred deletion,
                # which can be one or more event-loop turns away.
                item.widget().hide()
                item.widget().deleteLater()
        self._status_label_by_closure_id = {}

        if closing_service.is_backup_stale_for_banner(self._conn, utc_now()):
            old_backup_label = QLabel(ar.CLOSING_OLD_BACKUP_WARNING)
            old_backup_label.setProperty("role", "error")
            self._rows_layout.addWidget(old_backup_label)

        for closure in day_closures_repo.list_unsent_closures(self._conn):
            self._rows_layout.addWidget(self._build_closure_row(closure))

    def _build_closure_row(self, closure: sqlite3.Row) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.addWidget(QLabel(ar.CLOSING_BANNER_TEXT.format(date=closure["business_date"])))

        whatsapp_button = QPushButton(ar.CLOSING_BANNER_WHATSAPP_BUTTON)
        whatsapp_button.clicked.connect(lambda _checked=False, c=closure: self._on_send(c, self._configured_method()))
        layout.addWidget(whatsapp_button)

        browser_button = QPushButton(ar.CLOSING_BANNER_BROWSER_BUTTON)
        browser_button.clicked.connect(lambda _checked=False, c=closure: self._on_send(c, whatsapp.METHOD_BROWSER))
        layout.addWidget(browser_button)

        copy_button = QPushButton(ar.CLOSING_BANNER_COPY_BUTTON)
        copy_button.clicked.connect(lambda _checked=False, c=closure: self._on_send(c, whatsapp.METHOD_COPY))
        layout.addWidget(copy_button)

        view_button = QPushButton(ar.CLOSING_BANNER_VIEW_BUTTON)
        view_button.clicked.connect(lambda _checked=False, c=closure: self._on_view(c))
        layout.addWidget(view_button)

        sent_button = QPushButton(ar.CLOSING_BANNER_SENT_BUTTON)
        sent_button.clicked.connect(lambda _checked=False, c=closure: self._on_mark_sent(c))
        layout.addWidget(sent_button)

        status_label = QLabel("")
        layout.addWidget(status_label)
        self._status_label_by_closure_id[closure["id"]] = status_label

        return row

    def _configured_method(self) -> str:
        return settings_repo.get(self._conn, "whatsapp_method", whatsapp.METHOD_DESKTOP) or whatsapp.METHOD_DESKTOP

    def _on_send(self, closure: sqlite3.Row, method: str) -> None:
        number = settings_repo.get(self._conn, "whatsapp_number", "") or ""
        result = whatsapp.open_report(method, number, closure["report_text"])
        status_label = self._status_label_by_closure_id.get(closure["id"])
        if status_label is not None:
            status_label.setText(result.message)

    def _on_view(self, closure: sqlite3.Row) -> None:
        ClosingReportViewerDialog(closure["report_text"], parent=self).exec_()

    def _on_mark_sent(self, closure: sqlite3.Row) -> None:
        day_closures_repo.mark_sent(self._conn, closure["id"], self._user["id"])
        self.reload()
