"""Owner-only: add/rename/reorder/disable expense categories. Disabling a
category that is still used by past expenses is allowed on purpose -- it
only hides the category from NEW entries; nothing else changes.
"""
from __future__ import annotations

import sqlite3

from PySide2.QtCore import Signal
from PySide2.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from derby.core.db import expense_categories_repo
from derby.core.i18n import ar
from derby.features.expenses import expenses_service

_CATEGORY_ID_ROLE = 1000


class ExpenseCategoriesPanel(QWidget):
    categories_changed = Signal()

    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel(ar.EXPENSE_CATEGORIES_TITLE)
        title.setProperty("role", "title")
        layout.addWidget(title)

        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._refresh_actions_state)
        layout.addWidget(self._list)

        self._message_label = QLabel("")
        self._message_label.setProperty("role", "error")
        self._message_label.setWordWrap(True)
        layout.addWidget(self._message_label)

        add_row = QHBoxLayout()
        self._new_name_input = QLineEdit()
        self._new_name_input.setPlaceholderText(ar.EXPENSE_CATEGORY_NAME_PLACEHOLDER)
        add_row.addWidget(self._new_name_input)
        add_button = QPushButton(ar.EXPENSE_CATEGORY_ADD_BUTTON)
        add_button.clicked.connect(self._on_add)
        add_row.addWidget(add_button)
        layout.addLayout(add_row)

        actions_row = QHBoxLayout()
        self._rename_input = QLineEdit()
        actions_row.addWidget(self._rename_input)
        rename_button = QPushButton(ar.EXPENSE_CATEGORY_RENAME_BUTTON)
        rename_button.clicked.connect(self._on_rename)
        actions_row.addWidget(rename_button)

        up_button = QPushButton(ar.MENU_CATEGORY_MOVE_UP_BUTTON)
        up_button.clicked.connect(lambda: self._on_move(-1))
        actions_row.addWidget(up_button)
        down_button = QPushButton(ar.MENU_CATEGORY_MOVE_DOWN_BUTTON)
        down_button.clicked.connect(lambda: self._on_move(1))
        actions_row.addWidget(down_button)

        self._toggle_active_button = QPushButton(ar.EXPENSE_CATEGORY_DEACTIVATE_BUTTON)
        self._toggle_active_button.clicked.connect(self._on_toggle_active)
        actions_row.addWidget(self._toggle_active_button)
        layout.addLayout(actions_row)

        self._actions = [rename_button, up_button, down_button, self._toggle_active_button]
        self._set_actions_enabled(False)

    def _set_actions_enabled(self, enabled: bool) -> None:
        for widget in self._actions:
            widget.setEnabled(enabled)

    def _selected_category_id(self):
        item = self._list.currentItem()
        return item.data(_CATEGORY_ID_ROLE) if item is not None else None

    def reload(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for category in expense_categories_repo.list_categories(self._conn):
            status = "" if category["is_active"] else " ({0})".format(ar.USERS_INACTIVE_LABEL)
            item = QListWidgetItem(category["name"] + status)
            item.setData(_CATEGORY_ID_ROLE, category["id"])
            self._list.addItem(item)
        self._list.blockSignals(False)
        self._message_label.setText("")
        self._refresh_actions_state()

    def _refresh_actions_state(self) -> None:
        category_id = self._selected_category_id()
        self._set_actions_enabled(category_id is not None)
        if category_id is not None:
            category = expense_categories_repo.get_category(self._conn, category_id)
            self._rename_input.setText(category["name"])
            self._toggle_active_button.setText(
                ar.EXPENSE_CATEGORY_REACTIVATE_BUTTON if not category["is_active"] else ar.EXPENSE_CATEGORY_DEACTIVATE_BUTTON
            )

    def _on_add(self) -> None:
        name = self._new_name_input.text().strip()
        if not name:
            self._message_label.setText(ar.EXPENSE_CATEGORY_ERROR_NAME_REQUIRED)
            return
        expenses_service.add_category(self._conn, name, self._user["id"])
        self._new_name_input.clear()
        self.reload()
        self.categories_changed.emit()

    def _on_rename(self) -> None:
        category_id = self._selected_category_id()
        if category_id is None:
            return
        new_name = self._rename_input.text().strip()
        if not new_name:
            self._message_label.setText(ar.EXPENSE_CATEGORY_ERROR_NAME_REQUIRED)
            return
        expenses_service.rename_category(self._conn, category_id, new_name, self._user["id"])
        self.reload()
        self.categories_changed.emit()

    def _on_move(self, direction: int) -> None:
        category_id = self._selected_category_id()
        if category_id is None:
            return
        expenses_service.move_category(self._conn, category_id, direction, self._user["id"])
        self.reload()
        self.categories_changed.emit()

    def _on_toggle_active(self) -> None:
        category_id = self._selected_category_id()
        if category_id is None:
            return
        category = expense_categories_repo.get_category(self._conn, category_id)
        expenses_service.set_category_active(self._conn, category_id, not category["is_active"], self._user["id"])
        self.reload()
        self.categories_changed.emit()
