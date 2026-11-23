"""الورديات والموظفين: one screen, several tabs. Both roles get الوردية
(open/close their own) and الحضور والانصراف (clock themselves in/out);
سجل الورديات، الموظفون، and الرواتب are owner-only tabs.
"""
from __future__ import annotations

import sqlite3

from PySide2.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

from derby.core.i18n import ar
from derby.core.theme.tab_bar import configure_tab_widget
from derby.features.auth import permissions
from derby.features.employees.attendance_panel import AttendancePanel
from derby.features.employees.employees_panel import EmployeesPanel
from derby.features.employees.payroll_panel import PayrollPanel
from derby.features.shifts.shift_panel import ShiftPanel
from derby.features.shifts.shifts_history_panel import ShiftsHistoryPanel


class ShiftsEmployeesScreen(QWidget):
    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        layout = QVBoxLayout(self)
        title = QLabel(ar.SIDEBAR_SHIFTS_EMPLOYEES)
        title.setProperty("role", "title")
        layout.addWidget(title)

        tabs = QTabWidget()
        configure_tab_widget(tabs)
        self._shift_panel = ShiftPanel(conn, user)
        tabs.addTab(self._shift_panel, ar.SHIFTS_TAB_TITLE)

        if permissions.manage_shifts_all(user["role"]):
            self._history_panel = ShiftsHistoryPanel(conn)
            tabs.addTab(self._history_panel, ar.SHIFTS_HISTORY_TAB_TITLE)

        self._attendance_panel = AttendancePanel(conn, user)
        tabs.addTab(self._attendance_panel, ar.SHIFTS_ATTENDANCE_TAB_TITLE)

        if permissions.manage_employees(user["role"]):
            self._employees_panel = EmployeesPanel(conn, user)
            tabs.addTab(self._employees_panel, ar.SHIFTS_EMPLOYEES_TAB_TITLE)
            self._payroll_panel = PayrollPanel(conn, user)
            tabs.addTab(self._payroll_panel, ar.SHIFTS_PAYROLL_TAB_TITLE)

        tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(tabs)
        self._tabs = tabs

    def _on_tab_changed(self, _index: int) -> None:
        widget = self._tabs.currentWidget()
        if hasattr(widget, "reload"):
            widget.reload()

    def reload(self) -> None:
        self._shift_panel.reload()
