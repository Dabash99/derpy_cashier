"""A read-only detail view for one سجل العمليات row: every column plus
the structured details_json (before/after), pretty-printed. No editing
anywhere here -- the audit log is append-only, there is nothing to save.
"""
from __future__ import annotations

import json
import sqlite3

from PySide2.QtWidgets import QDialog, QFormLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout

from derby.core.i18n import ar
from derby.core.utils.time_utils import parse_utc_iso, to_cairo
from derby.features.audit.action_labels import label_for_action

_SEVERITY_LABELS = {
    "info": ar.AUDIT_LOG_SEVERITY_INFO,
    "warning": ar.AUDIT_LOG_SEVERITY_WARNING,
    "critical": ar.AUDIT_LOG_SEVERITY_CRITICAL,
}


class AuditDetailDialog(QDialog):
    def __init__(self, entry: sqlite3.Row, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(ar.AUDIT_LOG_DETAIL_TITLE)
        self.resize(480, 420)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        cairo_time = to_cairo(parse_utc_iso(entry["at_utc"])).strftime("%Y-%m-%d %H:%M:%S")
        form.addRow(ar.AUDIT_LOG_COLUMN_TIME, QLabel(cairo_time))
        form.addRow(ar.AUDIT_LOG_COLUMN_DATE, QLabel(entry["business_date"] or ""))
        form.addRow(ar.AUDIT_LOG_COLUMN_USER, QLabel(entry["user_name"] or ""))
        form.addRow(ar.AUDIT_LOG_COLUMN_ACTION, QLabel(label_for_action(entry["action"])))
        entity_text = ""
        if entry["entity_type"]:
            entity_text = "{0} #{1}".format(entry["entity_type"], entry["entity_id"] or "")
        form.addRow(ar.AUDIT_LOG_COLUMN_ENTITY, QLabel(entity_text))
        form.addRow(ar.AUDIT_LOG_COLUMN_SEVERITY, QLabel(_SEVERITY_LABELS.get(entry["severity"], entry["severity"])))

        summary_label = QLabel(entry["summary_ar"] or entry["details"] or "")
        summary_label.setWordWrap(True)
        form.addRow(ar.AUDIT_LOG_COLUMN_SUMMARY, summary_label)

        layout.addWidget(QLabel(ar.AUDIT_LOG_DETAIL_BEFORE_AFTER))
        details_view = QPlainTextEdit()
        details_view.setReadOnly(True)
        details_view.setPlainText(self._pretty_details(entry["details_json"]))
        layout.addWidget(details_view)

        close_button = QPushButton(ar.GENERIC_OK)
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)

    @staticmethod
    def _pretty_details(details_json) -> str:
        if not details_json:
            return ar.AUDIT_LOG_DETAIL_NO_DETAILS
        try:
            parsed = json.loads(details_json)
        except (TypeError, ValueError):
            return str(details_json)
        return json.dumps(parsed, ensure_ascii=False, indent=2, sort_keys=True)
