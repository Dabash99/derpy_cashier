"""الرواتب (owner only): the monthly payroll sheet, advance/deduction/
bonus entry, "تسجيل الدفع" (files a normal "مرتبات" expense, see
payroll_service.record_payment), and an export of the month's sheet.
"""
from __future__ import annotations

import sqlite3

from PySide2.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from derby.core.db import employees_repo
from derby.core.i18n import ar
from derby.core.theme.table_style import centered_item, configure_table, right_item
from derby.core.utils.money import egp_to_piasters, format_egp
from derby.core.utils.time_utils import utc_now
from derby.features.employees import payroll_service
from derby.features.reports.export_panel import ExportPanel
from derby.features.reports.export_service import ExportSection, write_csv_sections, write_xlsx_sections


class PayrollPanel(QWidget):
    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._sheet = []
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        month_row = QHBoxLayout()
        month_row.addWidget(QLabel(ar.PAYROLL_MONTH_LABEL))
        today = utc_now().date()
        self._month_input = QLineEdit("{0:04d}-{1:02d}".format(today.year, today.month))
        self._month_input.editingFinished.connect(self.reload)
        month_row.addWidget(self._month_input)
        layout.addLayout(month_row)

        line_row = QHBoxLayout()
        self._employee_input = QComboBox()
        for employee in employees_repo.list_employees(self._conn, active_only=True):
            self._employee_input.addItem(employee["name"], employee["id"])
        line_row.addWidget(self._employee_input)
        self._amount_input = QSpinBox()
        self._amount_input.setRange(1, 1_000_000)
        self._amount_input.setSuffix(" ج.م")
        line_row.addWidget(self._amount_input)
        self._note_input = QLineEdit()
        self._note_input.setPlaceholderText(ar.PAYROLL_NOTE_LABEL)
        line_row.addWidget(self._note_input)
        layout.addLayout(line_row)

        buttons_row = QHBoxLayout()
        advance_button = QPushButton(ar.PAYROLL_ADD_ADVANCE_BUTTON)
        advance_button.clicked.connect(lambda: self._add_line(payroll_service.add_advance))
        buttons_row.addWidget(advance_button)
        deduction_button = QPushButton(ar.PAYROLL_ADD_DEDUCTION_BUTTON)
        deduction_button.clicked.connect(lambda: self._add_line(payroll_service.add_deduction))
        buttons_row.addWidget(deduction_button)
        bonus_button = QPushButton(ar.PAYROLL_ADD_BONUS_BUTTON)
        bonus_button.clicked.connect(lambda: self._add_line(payroll_service.add_bonus))
        buttons_row.addWidget(bonus_button)
        layout.addLayout(buttons_row)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            [
                ar.PAYROLL_COLUMN_EMPLOYEE, ar.PAYROLL_COLUMN_BASE, ar.PAYROLL_COLUMN_BONUSES,
                ar.PAYROLL_COLUMN_ADVANCES, ar.PAYROLL_COLUMN_DEDUCTIONS, ar.PAYROLL_COLUMN_NET,
            ]
        )
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        configure_table(self._table, stretch_columns=(0,), fixed_widths={1: 90, 2: 90, 3: 90, 4: 90, 5: 100})
        layout.addWidget(self._table)

        pay_row = QHBoxLayout()
        self._payment_method_input = QComboBox()
        self._payment_method_input.addItem(ar.PAYMENT_METHOD_CASH, "cash")
        self._payment_method_input.addItem(ar.PAYMENT_METHOD_INSTAPAY, "instapay")
        pay_row.addWidget(QLabel(ar.PAYROLL_PAYMENT_METHOD_LABEL))
        pay_row.addWidget(self._payment_method_input)
        pay_button = QPushButton(ar.PAYROLL_RECORD_PAYMENT_BUTTON)
        pay_button.setProperty("variant", "primary")
        pay_button.clicked.connect(self._on_record_payment)
        pay_row.addWidget(pay_button)
        layout.addLayout(pay_row)

        self._message_label = QLabel("")
        layout.addWidget(self._message_label)

        self._export_panel = ExportPanel(lambda: "رواتب-{0}".format(self._month_input.text()))
        self._export_panel.set_exporters(csv_fn=self._export_csv, xlsx_fn=self._export_xlsx)
        layout.addWidget(self._export_panel)

    def _year_month(self):
        try:
            year_str, month_str = self._month_input.text().split("-")
            return int(year_str), int(month_str)
        except ValueError:
            today = utc_now().date()
            return today.year, today.month

    def reload(self) -> None:
        year, month = self._year_month()
        self._sheet = payroll_service.build_month_sheet(self._conn, year, month)
        self._table.setRowCount(len(self._sheet))
        for row_index, line in enumerate(self._sheet):
            makers = [right_item, centered_item, centered_item, centered_item, centered_item, centered_item]
            values = [
                line.employee["name"], format_egp(line.base_piasters), format_egp(line.bonuses_piasters),
                format_egp(line.advances_piasters), format_egp(line.deductions_piasters), format_egp(line.net_piasters),
            ]
            for column, (value, make_item) in enumerate(zip(values, makers)):
                self._table.setItem(row_index, column, make_item(value))

    def _add_line(self, add_fn) -> None:
        employee_id = self._employee_input.currentData()
        if employee_id is None:
            return
        employee = employees_repo.get_employee(self._conn, employee_id)
        amount_piasters = egp_to_piasters(self._amount_input.value())
        add_fn(self._conn, employee["id"], amount_piasters, utc_now().date(), self._note_input.text().strip() or None, self._user)
        self._note_input.clear()
        self._message_label.setText(ar.EMPLOYEES_SAVED_MESSAGE)
        self.reload()

    def _on_record_payment(self) -> None:
        row = self._table.currentRow()
        if not (0 <= row < len(self._sheet)):
            return
        line = self._sheet[row]
        year, month = self._year_month()
        payroll_service.record_payment(self._conn, line, year, month, self._payment_method_input.currentData(), self._user)
        self._message_label.setText(ar.PAYROLL_PAYMENT_SUCCESS)
        self.reload()

    def _sections(self):
        rows = [
            [
                line.employee["name"], line.base_piasters, line.bonuses_piasters, line.advances_piasters,
                line.deductions_piasters, line.net_piasters,
            ]
            for line in self._sheet
        ]
        return [
            ExportSection(
                "كشف الرواتب", ["الموظف", "الأساسي", "الحوافز", "السلف", "الاستقطاعات", "الصافي"], rows,
                money_columns=(1, 2, 3, 4, 5),
            )
        ]

    def _export_csv(self, path) -> None:
        write_csv_sections(self._sections(), path)

    def _export_xlsx(self, path) -> None:
        write_xlsx_sections(self._sections(), path)
