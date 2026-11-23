"""الموظفون (owner only): add/edit/deactivate, same inline-list pattern
as users_management.py.
"""
from __future__ import annotations

import sqlite3

from PySide2.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from derby.core.db import employees_repo, users_repo
from derby.core.i18n import ar
from derby.core.utils.money import egp_to_piasters, piasters_to_egp_float
from derby.features.employees import employee_service
from derby.features.employees.exceptions import EmployeeError


class EmployeesPanel(QWidget):
    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._selected_employee_id = None
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_selection_changed)
        layout.addWidget(self._list)

        form_row = QHBoxLayout()
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText(ar.EMPLOYEES_NAME_LABEL)
        form_row.addWidget(self._name_input)
        self._phone_input = QLineEdit()
        self._phone_input.setPlaceholderText(ar.EMPLOYEES_PHONE_LABEL)
        form_row.addWidget(self._phone_input)
        self._job_title_input = QLineEdit()
        self._job_title_input.setPlaceholderText(ar.EMPLOYEES_JOB_TITLE_LABEL)
        form_row.addWidget(self._job_title_input)
        layout.addLayout(form_row)

        form_row2 = QHBoxLayout()
        self._pay_type_input = QComboBox()
        self._pay_type_input.addItem(ar.EMPLOYEES_PAY_TYPE_MONTHLY, employees_repo.PAY_TYPE_MONTHLY)
        self._pay_type_input.addItem(ar.EMPLOYEES_PAY_TYPE_DAILY, employees_repo.PAY_TYPE_DAILY)
        form_row2.addWidget(self._pay_type_input)
        self._base_amount_input = QSpinBox()
        self._base_amount_input.setRange(0, 1_000_000)
        self._base_amount_input.setSuffix(" ج.م")
        form_row2.addWidget(self._base_amount_input)
        self._linked_user_input = QComboBox()
        self._linked_user_input.addItem(ar.EMPLOYEES_NONE_LABEL, None)
        for row in users_repo.list_users(self._conn, active_only=True):
            self._linked_user_input.addItem(row["name"], row["id"])
        form_row2.addWidget(self._linked_user_input)
        layout.addLayout(form_row2)

        actions_row = QHBoxLayout()
        add_button = QPushButton(ar.EMPLOYEES_ADD_BUTTON)
        add_button.clicked.connect(self._on_add)
        actions_row.addWidget(add_button)
        self._save_button = QPushButton(ar.EMPLOYEES_SAVE_BUTTON)
        self._save_button.clicked.connect(self._on_save)
        actions_row.addWidget(self._save_button)
        self._toggle_active_button = QPushButton(ar.EMPLOYEES_DEACTIVATE_BUTTON)
        self._toggle_active_button.clicked.connect(self._on_toggle_active)
        actions_row.addWidget(self._toggle_active_button)
        layout.addLayout(actions_row)

        self._message_label = QLabel("")
        self._message_label.setProperty("role", "error")
        layout.addWidget(self._message_label)

        self._set_form_enabled(False)

    def _set_form_enabled(self, enabled: bool) -> None:
        self._save_button.setEnabled(enabled)
        self._toggle_active_button.setEnabled(enabled)

    def reload(self) -> None:
        self._list.clear()
        for employee in employees_repo.list_employees(self._conn):
            status = ar.EMPLOYEES_ACTIVE_LABEL if employee["is_active"] else ar.EMPLOYEES_INACTIVE_LABEL
            item = QListWidgetItem("{0} — {1} — {2}".format(employee["name"], employee["job_title"] or "", status))
            item.setData(1000, employee["id"])
            self._list.addItem(item)

    def _on_selection_changed(self, current: QListWidgetItem, _previous) -> None:
        if current is None:
            self._selected_employee_id = None
            self._set_form_enabled(False)
            return
        self._selected_employee_id = current.data(1000)
        employee = employees_repo.get_employee(self._conn, self._selected_employee_id)
        self._name_input.setText(employee["name"])
        self._phone_input.setText(employee["phone"] or "")
        self._job_title_input.setText(employee["job_title"] or "")
        index = self._pay_type_input.findData(employee["pay_type"])
        if index >= 0:
            self._pay_type_input.setCurrentIndex(index)
        self._base_amount_input.setValue(int(piasters_to_egp_float(employee["base_amount_piasters"])))
        linked_index = self._linked_user_input.findData(employee["linked_user_id"])
        self._linked_user_input.setCurrentIndex(linked_index if linked_index >= 0 else 0)
        self._toggle_active_button.setText(
            ar.EMPLOYEES_REACTIVATE_BUTTON if not employee["is_active"] else ar.EMPLOYEES_DEACTIVATE_BUTTON
        )
        self._set_form_enabled(True)

    def _on_add(self) -> None:
        try:
            employee_service.create_employee(
                self._conn, self._name_input.text(), self._phone_input.text().strip() or None,
                self._job_title_input.text().strip() or None, self._pay_type_input.currentData(),
                egp_to_piasters(self._base_amount_input.value()), self._user, self._linked_user_input.currentData(),
            )
        except EmployeeError as error:
            self._message_label.setText(str(error))
            return
        self._name_input.clear()
        self._phone_input.clear()
        self._job_title_input.clear()
        self._message_label.setText(ar.EMPLOYEES_SAVED_MESSAGE)
        self.reload()

    def _on_save(self) -> None:
        if self._selected_employee_id is None:
            return
        try:
            employee_service.update_employee(
                self._conn, self._selected_employee_id, self._name_input.text(), self._phone_input.text().strip() or None,
                self._job_title_input.text().strip() or None, self._pay_type_input.currentData(),
                egp_to_piasters(self._base_amount_input.value()), self._user, self._linked_user_input.currentData(),
            )
        except EmployeeError as error:
            self._message_label.setText(str(error))
            return
        self._message_label.setText(ar.EMPLOYEES_SAVED_MESSAGE)
        self.reload()

    def _on_toggle_active(self) -> None:
        if self._selected_employee_id is None:
            return
        employee = employees_repo.get_employee(self._conn, self._selected_employee_id)
        employee_service.set_active(self._conn, self._selected_employee_id, not employee["is_active"], self._user)
        self._message_label.setText(ar.EMPLOYEES_SAVED_MESSAGE)
        self.reload()
