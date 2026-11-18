"""Owner-only: add/rename/reorder/disable tables. Disabling a table with
an open order is rejected -- that's the one business rule beyond plain
CRUD here.
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

from derby.core.db import orders_repo, tables_repo
from derby.core.i18n import ar

_TABLE_ID_ROLE = 1000


class TablesManagementPanel(QWidget):
    tables_changed = Signal()

    def __init__(self, conn: sqlite3.Connection, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel(ar.TABLES_TITLE)
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
        self._new_name_input.setPlaceholderText(ar.TABLES_NAME_PLACEHOLDER)
        add_row.addWidget(self._new_name_input)
        add_button = QPushButton(ar.TABLES_ADD_BUTTON)
        add_button.clicked.connect(self._on_add)
        add_row.addWidget(add_button)
        layout.addLayout(add_row)

        actions_row = QHBoxLayout()
        self._rename_input = QLineEdit()
        actions_row.addWidget(self._rename_input)
        rename_button = QPushButton(ar.TABLES_RENAME_BUTTON)
        rename_button.clicked.connect(self._on_rename)
        actions_row.addWidget(rename_button)

        up_button = QPushButton(ar.MENU_CATEGORY_MOVE_UP_BUTTON)
        up_button.clicked.connect(lambda: self._on_move(-1))
        actions_row.addWidget(up_button)
        down_button = QPushButton(ar.MENU_CATEGORY_MOVE_DOWN_BUTTON)
        down_button.clicked.connect(lambda: self._on_move(1))
        actions_row.addWidget(down_button)

        self._toggle_active_button = QPushButton(ar.TABLES_DEACTIVATE_BUTTON)
        self._toggle_active_button.clicked.connect(self._on_toggle_active)
        actions_row.addWidget(self._toggle_active_button)
        layout.addLayout(actions_row)

        self._actions = [rename_button, up_button, down_button, self._toggle_active_button]
        self._set_actions_enabled(False)

    def _set_actions_enabled(self, enabled: bool) -> None:
        for widget in self._actions:
            widget.setEnabled(enabled)

    def _selected_table_id(self):
        item = self._list.currentItem()
        return item.data(_TABLE_ID_ROLE) if item is not None else None

    def reload(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for table in tables_repo.list_tables(self._conn):
            status = "" if table["is_active"] else " ({0})".format(ar.USERS_INACTIVE_LABEL)
            item = QListWidgetItem(table["name"] + status)
            item.setData(_TABLE_ID_ROLE, table["id"])
            self._list.addItem(item)
        self._list.blockSignals(False)
        self._message_label.setText("")
        self._refresh_actions_state()

    def _refresh_actions_state(self) -> None:
        table_id = self._selected_table_id()
        self._set_actions_enabled(table_id is not None)
        if table_id is not None:
            table = tables_repo.get_table(self._conn, table_id)
            self._rename_input.setText(table["name"])
            self._toggle_active_button.setText(
                ar.TABLES_REACTIVATE_BUTTON if not table["is_active"] else ar.TABLES_DEACTIVATE_BUTTON
            )

    def _on_add(self) -> None:
        name = self._new_name_input.text().strip()
        if not name:
            self._message_label.setText(ar.TABLES_ERROR_NAME_REQUIRED)
            return
        tables_repo.create_table(self._conn, name)
        self._new_name_input.clear()
        self.reload()
        self.tables_changed.emit()

    def _on_rename(self) -> None:
        table_id = self._selected_table_id()
        if table_id is None:
            return
        new_name = self._rename_input.text().strip()
        if not new_name:
            self._message_label.setText(ar.TABLES_ERROR_NAME_REQUIRED)
            return
        tables_repo.rename_table(self._conn, table_id, new_name)
        self.reload()
        self.tables_changed.emit()

    def _on_move(self, direction: int) -> None:
        table_id = self._selected_table_id()
        if table_id is None:
            return
        tables_repo.move_table(self._conn, table_id, direction)
        self.reload()
        self.tables_changed.emit()

    def _on_toggle_active(self) -> None:
        table_id = self._selected_table_id()
        if table_id is None:
            return
        table = tables_repo.get_table(self._conn, table_id)
        if table["is_active"]:
            if orders_repo.get_open_order_for_table(self._conn, table_id) is not None:
                self._message_label.setText(ar.TABLES_ERROR_CANNOT_DISABLE_BUSY)
                return
            tables_repo.set_active(self._conn, table_id, False)
        else:
            tables_repo.set_active(self._conn, table_id, True)
        self.reload()
        self.tables_changed.emit()
