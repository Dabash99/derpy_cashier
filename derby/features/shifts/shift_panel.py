""""الوردية" tab: open/close/handover the one shared shift, and show its
live report once closed. Visible to both roles (permissions.
view_shift_report) -- a cashier closes their own shift the same way the
owner does; only the "سجل الورديات" (every shift, not just the current
one) tab is owner-only (see shifts_employees_screen.py).
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from derby.core.db import users_repo
from derby.core.i18n import ar
from derby.core.utils.money import parse_egp_input
from derby.core.utils.time_utils import parse_utc_iso, to_cairo
from derby.features.shifts import shift_service
from derby.features.shifts.exceptions import ShiftError


class ShiftPanel(QWidget):
    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._last_closed_report_text = ""
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # This tab's content (two forms + buttons + the report text) can
        # exceed the window's minimum height (1024x680, see
        # main_window.py) once it sits inside the tab bar/header chrome --
        # a plain QVBoxLayout has no way to shrink in that case and Qt
        # overlaps rows instead of scrolling (same bug class as the
        # sidebar's own scroll-host, see its comment), so this tab scrolls
        # like every other content-heavy screen in this app.
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        scroll_area.setWidget(content)
        outer.addWidget(scroll_area)

        self._status_label = QLabel("")
        self._status_label.setProperty("role", "subtitle")
        layout.addWidget(self._status_label)

        open_form_host = QWidget()
        form = QFormLayout(open_form_host)
        self._opening_cash_input = QLineEdit()
        form.addRow(ar.SHIFT_OPENING_CASH_LABEL, self._opening_cash_input)
        layout.addWidget(open_form_host)

        open_row = QHBoxLayout()
        self._open_button = QPushButton(ar.SHIFT_OPEN_BUTTON)
        self._open_button.setProperty("variant", "primary")
        self._open_button.clicked.connect(self._on_open)
        open_row.addWidget(self._open_button)
        layout.addLayout(open_row)

        close_form_host = QWidget()
        close_form = QFormLayout(close_form_host)
        self._counted_input = QLineEdit()
        close_form.addRow(ar.SHIFT_COUNTED_LABEL, self._counted_input)
        self._notes_input = QLineEdit()
        close_form.addRow(ar.SHIFT_NOTES_LABEL, self._notes_input)
        self._handover_to_input = QComboBox()
        close_form.addRow(ar.SHIFT_HANDOVER_TO_LABEL, self._handover_to_input)
        layout.addWidget(close_form_host)

        close_row = QHBoxLayout()
        self._close_button = QPushButton(ar.SHIFT_CLOSE_BUTTON)
        self._close_button.clicked.connect(self._on_close)
        close_row.addWidget(self._close_button)
        self._handover_button = QPushButton(ar.SHIFT_HANDOVER_BUTTON)
        self._handover_button.clicked.connect(self._on_handover)
        close_row.addWidget(self._handover_button)
        layout.addLayout(close_row)

        self._message_label = QLabel("")
        self._message_label.setWordWrap(True)
        self._message_label.setProperty("role", "error")
        layout.addWidget(self._message_label)

        report_title = QLabel(ar.SHIFT_REPORT_TITLE)
        report_title.setProperty("role", "subtitle")
        layout.addWidget(report_title)
        self._report_label = QLabel("")
        self._report_label.setWordWrap(True)
        layout.addWidget(self._report_label)
        layout.addStretch(1)

    def reload(self) -> None:
        shift = shift_service.get_open_shift(self._conn)
        has_shift = shift is not None
        self._open_button.setEnabled(not has_shift)
        self._opening_cash_input.setEnabled(not has_shift)
        self._close_button.setEnabled(has_shift)
        self._handover_button.setEnabled(has_shift)
        self._counted_input.setEnabled(has_shift)

        self._handover_to_input.clear()
        for other in users_repo.list_users(self._conn, active_only=True):
            if other["id"] != self._user["id"]:
                self._handover_to_input.addItem(other["name"], other["id"])

        if has_shift:
            opened_cairo = to_cairo(parse_utc_iso(shift["opened_at_utc"])).strftime("%Y-%m-%d %H:%M")
            opener = users_repo.get_user(self._conn, shift["user_id"])
            self._status_label.setText(
                ar.SHIFT_OPEN_SINCE.format(time=opened_cairo, user=opener["name"] if opener else "")
            )
            report = shift_service.build_shift_report(self._conn, shift)
            self._report_label.setText(shift_service.report_summary_text(report))
        else:
            self._status_label.setText(ar.SHIFT_NO_OPEN_SHIFT)
            self._report_label.setText(self._last_closed_report_text)

    def _parse_amount(self, text: str) -> Optional[int]:
        try:
            return parse_egp_input(text)
        except ValueError:
            return None

    def _on_open(self) -> None:
        amount = self._parse_amount(self._opening_cash_input.text() or "0")
        if amount is None:
            self._message_label.setText(ar.DRAWER_ERROR_AMOUNT_INVALID)
            return
        try:
            shift_service.open_shift(self._conn, self._user, amount)
        except ShiftError as error:
            self._message_label.setText(str(error))
            return
        self._opening_cash_input.clear()
        self.reload()

    def _on_close(self) -> None:
        shift = shift_service.get_open_shift(self._conn)
        if shift is None:
            return
        amount = self._parse_amount(self._counted_input.text())
        if amount is None:
            self._message_label.setText(ar.DRAWER_ERROR_AMOUNT_INVALID)
            return
        try:
            _closed, report = shift_service.close_shift(
                self._conn, shift, amount, self._notes_input.text().strip() or None, self._user
            )
        except ShiftError as error:
            self._message_label.setText(str(error))
            return
        self._counted_input.clear()
        self._notes_input.clear()
        self._message_label.setText(ar.SHIFT_CLOSE_SUCCESS)
        self._last_closed_report_text = shift_service.report_summary_text(report)
        self.reload()

    def _on_handover(self) -> None:
        shift = shift_service.get_open_shift(self._conn)
        if shift is None or self._handover_to_input.count() == 0:
            return
        amount = self._parse_amount(self._counted_input.text())
        if amount is None:
            self._message_label.setText(ar.DRAWER_ERROR_AMOUNT_INVALID)
            return
        next_user_id = self._handover_to_input.currentData()
        next_user = users_repo.get_user(self._conn, next_user_id)
        try:
            shift_service.handover_shift(
                self._conn, shift, amount, self._notes_input.text().strip() or None, self._user, next_user
            )
        except ShiftError as error:
            self._message_label.setText(str(error))
            return
        self._counted_input.clear()
        self._notes_input.clear()
        self._message_label.setText(ar.SHIFT_HANDOVER_SUCCESS)
        self.reload()
