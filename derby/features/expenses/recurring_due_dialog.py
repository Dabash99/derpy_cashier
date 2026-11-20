""""مصروفات ثابتة مستحقة هذا الشهر" -- shown when the owner opens the
Expenses screen (and the main window wires it in at login too) if any
active recurring template's day has arrived and it has no expense
generated for this month yet. Each row is confirmed (amount editable --
bills vary) or skipped independently; confirming/skipping never prompts
again for that template this month.
"""
from __future__ import annotations

import sqlite3
from datetime import date

from PySide2.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from derby.core.i18n import ar
from derby.core.utils.money import piasters_to_plain_text
from derby.features.expenses import expenses_service
from derby.features.expenses.exceptions import InvalidAmountError
from derby.features.menu.price_parsing import parse_product_price


class RecurringDueDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, today: date, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._today = today
        self.setWindowTitle(ar.RECURRING_DUE_DIALOG_TITLE)
        self._build_ui()

    def _build_ui(self) -> None:
        self._layout = QVBoxLayout(self)
        self._layout.addWidget(QLabel(ar.RECURRING_DUE_DIALOG_INTRO))
        self._rows_host = QVBoxLayout()
        self._layout.addLayout(self._rows_host)
        self._rebuild_rows()

    def _rebuild_rows(self) -> None:
        while self._rows_host.count():
            item = self._rows_host.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    inner = item.layout().takeAt(0)
                    if inner.widget():
                        inner.widget().hide()
                        inner.widget().deleteLater()

        due = expenses_service.due_templates_for_month(self._conn, self._today)
        if not due:
            self._rows_host.addWidget(QLabel(ar.RECURRING_DUE_NONE))
            return
        for template in due:
            self._rows_host.addLayout(self._build_row(template))

    def _build_row(self, template: sqlite3.Row) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel(template["name"]))

        amount_input = QLineEdit(piasters_to_plain_text(template["amount_piasters"]))
        row.addWidget(amount_input)

        error_label = QLabel("")
        error_label.setProperty("role", "error")

        confirm_button = QPushButton(ar.RECURRING_DUE_CONFIRM_BUTTON)
        confirm_button.clicked.connect(
            lambda _checked=False, t=template, inp=amount_input, err=error_label: self._on_confirm(t, inp, err)
        )
        row.addWidget(confirm_button)

        skip_button = QPushButton(ar.RECURRING_DUE_SKIP_BUTTON)
        skip_button.clicked.connect(lambda _checked=False, t=template: self._on_skip(t))
        row.addWidget(skip_button)

        row.addWidget(error_label)
        return row

    def _on_confirm(self, template: sqlite3.Row, amount_input: QLineEdit, error_label: QLabel) -> None:
        try:
            amount = parse_product_price(amount_input.text())
        except ValueError:
            error_label.setText(ar.RECURRING_ERROR_AMOUNT_INVALID)
            return
        try:
            expenses_service.confirm_recurring(self._conn, template["id"], amount, self._today, self._user["id"])
        except InvalidAmountError:
            error_label.setText(ar.RECURRING_ERROR_AMOUNT_INVALID)
            return
        self._rebuild_rows()
        if not expenses_service.due_templates_for_month(self._conn, self._today):
            self.accept()

    def _on_skip(self, template: sqlite3.Row) -> None:
        expenses_service.skip_recurring(self._conn, template["id"], self._today, self._user["id"])
        self._rebuild_rows()
        if not expenses_service.due_templates_for_month(self._conn, self._today):
            self.accept()
