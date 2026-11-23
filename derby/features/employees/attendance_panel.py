"""الحضور والانصراف: a cashier clocks themself in/out (PIN already
verified at login -- no extra prompt, matching how low-friction the
rest of the POS flow is); an owner can also pick ANY employee to view
hours and correct a row (reason required, audited).
"""
from __future__ import annotations

import sqlite3

from PySide2.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from derby.core.db import employees_repo
from derby.core.i18n import ar
from derby.core.theme.table_style import centered_item, configure_table
from derby.core.utils.time_utils import parse_utc_iso, to_cairo, utc_now
from derby.features.auth import permissions
from derby.features.employees import attendance_service
from derby.features.employees.exceptions import EmployeeError


class AttendancePanel(QWidget):
    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._can_pick_any = permissions.manage_attendance_corrections(user["role"])
        self._build_ui()
        self.reload()

    def _linked_employee(self) -> "sqlite3.Row | None":
        for employee in employees_repo.list_employees(self._conn, active_only=True):
            if employee["linked_user_id"] == self._user["id"]:
                return employee
        return None

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        picker_row = QHBoxLayout()
        picker_row.addWidget(QLabel(ar.ATTENDANCE_SELECT_EMPLOYEE_LABEL))
        self._employee_input = QComboBox()
        self._employee_input.currentIndexChanged.connect(self.reload)
        self._employee_input.setEnabled(self._can_pick_any)
        picker_row.addWidget(self._employee_input)
        layout.addLayout(picker_row)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

        actions_row = QHBoxLayout()
        self._clock_in_button = QPushButton(ar.ATTENDANCE_CLOCK_IN_BUTTON)
        self._clock_in_button.setProperty("variant", "primary")
        self._clock_in_button.clicked.connect(self._on_clock_in)
        actions_row.addWidget(self._clock_in_button)
        self._clock_out_button = QPushButton(ar.ATTENDANCE_CLOCK_OUT_BUTTON)
        self._clock_out_button.clicked.connect(self._on_clock_out)
        actions_row.addWidget(self._clock_out_button)
        layout.addLayout(actions_row)

        self._hours_label = QLabel("")
        layout.addWidget(self._hours_label)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(
            [ar.ATTENDANCE_COLUMN_DATE, ar.ATTENDANCE_COLUMN_IN, ar.ATTENDANCE_COLUMN_OUT, ar.ATTENDANCE_COLUMN_CORRECTED]
        )
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.cellDoubleClicked.connect(self._on_row_double_clicked)
        configure_table(self._table, stretch_columns=(0,), fixed_widths={1: 100, 2: 100, 3: 80})
        layout.addWidget(self._table)
        if self._can_pick_any:
            layout.addWidget(QLabel(ar.ATTENDANCE_CORRECTION_BUTTON))

        self._message_label = QLabel("")
        self._message_label.setProperty("role", "error")
        layout.addWidget(self._message_label)

    def _current_employee(self):
        if self._can_pick_any:
            employee_id = self._employee_input.currentData()
            return employees_repo.get_employee(self._conn, employee_id) if employee_id else None
        return self._linked_employee()

    def reload(self) -> None:
        if self._can_pick_any and self._employee_input.count() == 0:
            for employee in employees_repo.list_employees(self._conn, active_only=True):
                self._employee_input.addItem(employee["name"], employee["id"])

        employee = self._current_employee()
        self._rows_by_index = []
        if employee is None:
            self._status_label.setText("")
            self._clock_in_button.setEnabled(False)
            self._clock_out_button.setEnabled(False)
            self._table.setRowCount(0)
            self._hours_label.setText("")
            return

        from derby.core.db import attendance_repo

        open_row = attendance_repo.get_open_attendance(self._conn, employee["id"])
        if open_row is not None:
            clocked_in_cairo = to_cairo(parse_utc_iso(open_row["clock_in_utc"])).strftime("%H:%M")
            self._status_label.setText(ar.ATTENDANCE_STATUS_CLOCKED_IN.format(time=clocked_in_cairo))
        else:
            self._status_label.setText(ar.ATTENDANCE_STATUS_NOT_CLOCKED_IN)
        self._clock_in_button.setEnabled(open_row is None)
        self._clock_out_button.setEnabled(open_row is not None)

        today = utc_now().date()
        month_start = today.replace(day=1).isoformat()
        rows = attendance_service.list_for_employee(self._conn, employee["id"], month_start, today.isoformat())
        self._rows_by_index = rows
        self._table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            clock_in_text = to_cairo(parse_utc_iso(row["clock_in_utc"])).strftime("%m-%d %H:%M") if row["clock_in_utc"] else ""
            clock_out_text = to_cairo(parse_utc_iso(row["clock_out_utc"])).strftime("%m-%d %H:%M") if row["clock_out_utc"] else ""
            corrected_text = "✓" if row["corrected_by"] else ""
            for column, value in enumerate([row["business_date"], clock_in_text, clock_out_text, corrected_text]):
                self._table.setItem(row_index, column, centered_item(value))

        hours = attendance_service.hours_for_period(self._conn, employee["id"], month_start, today.isoformat())
        self._hours_label.setText(ar.ATTENDANCE_TOTAL_HOURS_LABEL.format(hours=hours))

    def _on_clock_in(self) -> None:
        employee = self._current_employee()
        if employee is None:
            return
        try:
            attendance_service.clock_in(self._conn, employee["id"], self._user)
        except EmployeeError as error:
            self._message_label.setText(str(error))
            return
        self.reload()

    def _on_clock_out(self) -> None:
        employee = self._current_employee()
        if employee is None:
            return
        try:
            attendance_service.clock_out(self._conn, employee["id"], self._user)
        except EmployeeError as error:
            self._message_label.setText(str(error))
            return
        self.reload()

    def _on_row_double_clicked(self, row: int, _column: int) -> None:
        if not self._can_pick_any or not (0 <= row < len(self._rows_by_index)):
            return
        attendance_row = self._rows_by_index[row]
        reason, confirmed = QInputDialog.getText(self, ar.ATTENDANCE_CORRECTION_BUTTON, ar.ATTENDANCE_CORRECTION_REASON_LABEL)
        if not confirmed or not reason.strip():
            return
        try:
            attendance_service.correct(
                self._conn, attendance_row["id"], attendance_row["clock_in_utc"], attendance_row["clock_out_utc"],
                reason, self._user,
            )
        except EmployeeError as error:
            QMessageBox.warning(self, ar.GENERIC_ERROR_TITLE, str(error))
            return
        self.reload()
