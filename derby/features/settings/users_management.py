"""Owner-only user list: add, rename, change PIN, deactivate/reactivate.

Deliberately dialog-free (everything inline) to keep the widget simple and
avoid extra modal-dialog edge cases on older Windows.
"""
from __future__ import annotations

import sqlite3

from PySide2.QtCore import QRegExp
from PySide2.QtGui import QRegExpValidator
from PySide2.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from derby.core import audit_service
from derby.core.db import users_repo
from derby.core.i18n import ar
from derby.core.utils.pin_hash import is_valid_pin_format


def _pin_input() -> QLineEdit:
    field = QLineEdit()
    field.setEchoMode(QLineEdit.Password)
    field.setValidator(QRegExpValidator(QRegExp(r"\d{0,6}")))
    return field


class UsersManagementWidget(QWidget):
    def __init__(self, conn: sqlite3.Connection, current_user_id: int, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._current_user_id = current_user_id
        self._selected_user_id = None
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        title = QLabel(ar.USERS_TITLE)
        title.setProperty("role", "title")
        layout.addWidget(title)

        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_selection_changed)
        layout.addWidget(self._list)

        self._message_label = QLabel("")
        self._message_label.setProperty("role", "error")
        self._message_label.setWordWrap(True)
        layout.addWidget(self._message_label)

        layout.addWidget(self._build_add_section())
        layout.addWidget(self._build_actions_section())

    def _build_add_section(self) -> QWidget:
        section = QWidget()
        row = QHBoxLayout(section)
        row.setContentsMargins(0, 0, 0, 0)

        self._add_name_input = QLineEdit()
        self._add_name_input.setPlaceholderText(ar.USERS_NAME_LABEL)
        row.addWidget(self._add_name_input)

        self._add_role_input = QComboBox()
        self._add_role_input.addItem(ar.USERS_ROLE_CASHIER, users_repo.ROLE_CASHIER)
        self._add_role_input.addItem(ar.USERS_ROLE_OWNER, users_repo.ROLE_OWNER)
        row.addWidget(self._add_role_input)

        self._add_pin_input = _pin_input()
        self._add_pin_input.setPlaceholderText(ar.USERS_PIN_LABEL)
        row.addWidget(self._add_pin_input)

        self._add_pin_confirm_input = _pin_input()
        self._add_pin_confirm_input.setPlaceholderText(ar.USERS_PIN_CONFIRM_LABEL)
        row.addWidget(self._add_pin_confirm_input)

        add_button = QPushButton(ar.USERS_ADD_BUTTON)
        add_button.clicked.connect(self._on_add_user)
        row.addWidget(add_button)

        return section

    def _build_actions_section(self) -> QWidget:
        section = QWidget()
        row = QHBoxLayout(section)
        row.setContentsMargins(0, 0, 0, 0)

        self._rename_input = QLineEdit()
        self._rename_input.setPlaceholderText(ar.USERS_NAME_LABEL)
        row.addWidget(self._rename_input)
        rename_button = QPushButton(ar.USERS_RENAME_BUTTON)
        rename_button.clicked.connect(self._on_rename)
        row.addWidget(rename_button)

        self._new_pin_input = _pin_input()
        self._new_pin_input.setPlaceholderText(ar.USERS_PIN_LABEL)
        row.addWidget(self._new_pin_input)

        self._new_pin_confirm_input = _pin_input()
        self._new_pin_confirm_input.setPlaceholderText(ar.USERS_PIN_CONFIRM_LABEL)
        row.addWidget(self._new_pin_confirm_input)
        change_pin_button = QPushButton(ar.USERS_CHANGE_PIN_BUTTON)
        change_pin_button.clicked.connect(self._on_change_pin)
        row.addWidget(change_pin_button)

        self._toggle_active_button = QPushButton(ar.USERS_DEACTIVATE_BUTTON)
        self._toggle_active_button.clicked.connect(self._on_toggle_active)
        row.addWidget(self._toggle_active_button)

        self._actions_section = section
        self._actions_section.setEnabled(False)
        return section

    def reload(self) -> None:
        self._list.clear()
        for user in users_repo.list_users(self._conn):
            status = ar.USERS_ACTIVE_LABEL if user["is_active"] else ar.USERS_INACTIVE_LABEL
            role_label = ar.USERS_ROLE_OWNER if user["role"] == users_repo.ROLE_OWNER else ar.USERS_ROLE_CASHIER
            item = QListWidgetItem("{0} — {1} — {2}".format(user["name"], role_label, status))
            item.setData(1000, user["id"])
            self._list.addItem(item)
        self._message_label.setText("")

    def _on_selection_changed(self, current: QListWidgetItem, _previous: QListWidgetItem) -> None:
        if current is None:
            self._selected_user_id = None
            self._actions_section.setEnabled(False)
            return
        self._selected_user_id = current.data(1000)
        self._actions_section.setEnabled(True)
        user = users_repo.get_user(self._conn, self._selected_user_id)
        self._rename_input.setText(user["name"])
        self._toggle_active_button.setText(
            ar.USERS_REACTIVATE_BUTTON if not user["is_active"] else ar.USERS_DEACTIVATE_BUTTON
        )

    def _on_add_user(self) -> None:
        name = self._add_name_input.text().strip()
        role = self._add_role_input.currentData()
        pin = self._add_pin_input.text()
        pin_confirm = self._add_pin_confirm_input.text()

        if not name:
            self._message_label.setText(ar.USERS_ERROR_NAME_REQUIRED)
            return
        if not is_valid_pin_format(pin):
            self._message_label.setText(ar.USERS_ERROR_PIN_FORMAT)
            return
        if pin != pin_confirm:
            self._message_label.setText(ar.USERS_ERROR_PIN_MISMATCH)
            return
        if users_repo.is_pin_in_use(self._conn, pin):
            self._message_label.setText(ar.USERS_ERROR_PIN_TAKEN)
            return

        new_user_id = users_repo.create_user(self._conn, name, role, pin)
        audit_service.log(
            self._conn, "user_created", user_id=self._current_user_id,
            entity_type="user", entity_id=new_user_id,
            summary_ar="إضافة مستخدم: {0} ({1})".format(name, role),
            details={"name": name, "role": role},
        )
        self._add_name_input.clear()
        self._add_pin_input.clear()
        self._add_pin_confirm_input.clear()
        self._message_label.setText(ar.USERS_SAVED_MESSAGE)
        self.reload()

    def _on_rename(self) -> None:
        if self._selected_user_id is None:
            return
        new_name = self._rename_input.text().strip()
        if not new_name:
            self._message_label.setText(ar.USERS_ERROR_NAME_REQUIRED)
            return
        old_user = users_repo.get_user(self._conn, self._selected_user_id)
        old_name = old_user["name"] if old_user is not None else ""
        users_repo.rename_user(self._conn, self._selected_user_id, new_name)
        audit_service.log(
            self._conn, "user_renamed", user_id=self._current_user_id,
            entity_type="user", entity_id=self._selected_user_id,
            summary_ar="تعديل اسم مستخدم: {0} -> {1}".format(old_name, new_name),
            details={"before": old_name, "after": new_name},
        )
        self._message_label.setText(ar.USERS_SAVED_MESSAGE)
        self.reload()

    def _on_change_pin(self) -> None:
        if self._selected_user_id is None:
            return
        new_pin = self._new_pin_input.text()
        new_pin_confirm = self._new_pin_confirm_input.text()
        if not is_valid_pin_format(new_pin):
            self._message_label.setText(ar.USERS_ERROR_PIN_FORMAT)
            return
        if new_pin != new_pin_confirm:
            self._message_label.setText(ar.USERS_ERROR_PIN_MISMATCH)
            return
        if users_repo.is_pin_in_use(self._conn, new_pin, exclude_user_id=self._selected_user_id):
            self._message_label.setText(ar.USERS_ERROR_PIN_TAKEN)
            return
        users_repo.change_pin(self._conn, self._selected_user_id, new_pin)
        audit_service.log(
            self._conn, "user_pin_changed", user_id=self._current_user_id,
            entity_type="user", entity_id=self._selected_user_id,
            summary_ar="تغيير الرقم السري لمستخدم", severity=audit_service.SEVERITY_WARNING,
        )
        self._new_pin_input.clear()
        self._new_pin_confirm_input.clear()
        self._message_label.setText(ar.USERS_SAVED_MESSAGE)
        self.reload()

    def _on_toggle_active(self) -> None:
        if self._selected_user_id is None:
            return
        user = users_repo.get_user(self._conn, self._selected_user_id)
        if user["is_active"]:
            if self._selected_user_id == self._current_user_id:
                self._message_label.setText(ar.USERS_ERROR_CANNOT_DEACTIVATE_SELF)
                return
            if user["role"] == users_repo.ROLE_OWNER and users_repo.count_active_owners(self._conn) <= 1:
                self._message_label.setText(ar.USERS_ERROR_CANNOT_DEACTIVATE_LAST_OWNER)
                return
            users_repo.set_active(self._conn, self._selected_user_id, False)
            audit_service.log(
                self._conn, "user_deactivated", user_id=self._current_user_id,
                entity_type="user", entity_id=self._selected_user_id,
                summary_ar="تعطيل مستخدم: {0}".format(user["name"]), severity=audit_service.SEVERITY_WARNING,
            )
        else:
            users_repo.set_active(self._conn, self._selected_user_id, True)
            audit_service.log(
                self._conn, "user_reactivated", user_id=self._current_user_id,
                entity_type="user", entity_id=self._selected_user_id,
                summary_ar="تفعيل مستخدم: {0}".format(user["name"]),
            )
        self._message_label.setText(ar.USERS_SAVED_MESSAGE)
        self.reload()
