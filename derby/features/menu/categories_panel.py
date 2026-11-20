"""The categories list (right side of the menu screen, per RTL layout):
add, rename, reorder, activate/deactivate.
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

from derby.core.db import categories_repo
from derby.core.i18n import ar

_CATEGORY_ID_ROLE = 1000


class CategoriesPanel(QWidget):
    selection_changed = Signal(object)  # category_id or None
    categories_changed = Signal()

    def __init__(self, conn: sqlite3.Connection, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        title = QLabel(ar.MENU_CATEGORIES_TITLE)
        title.setProperty("role", "title")
        layout.addWidget(title)

        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_selection_changed)
        layout.addWidget(self._list)

        self._message_label = QLabel("")
        self._message_label.setProperty("role", "error")
        self._message_label.setWordWrap(True)
        layout.addWidget(self._message_label)

        add_row = QHBoxLayout()
        self._new_name_input = QLineEdit()
        self._new_name_input.setPlaceholderText(ar.MENU_CATEGORY_NAME_PLACEHOLDER)
        add_row.addWidget(self._new_name_input)
        add_button = QPushButton(ar.MENU_CATEGORY_ADD_BUTTON)
        add_button.clicked.connect(self._on_add)
        add_row.addWidget(add_button)
        layout.addLayout(add_row)

        actions_row = QHBoxLayout()
        self._rename_input = QLineEdit()
        actions_row.addWidget(self._rename_input)
        rename_button = QPushButton(ar.MENU_CATEGORY_RENAME_BUTTON)
        rename_button.clicked.connect(self._on_rename)
        actions_row.addWidget(rename_button)
        layout.addLayout(actions_row)

        move_row = QHBoxLayout()
        up_button = QPushButton(ar.MENU_CATEGORY_MOVE_UP_BUTTON)
        up_button.clicked.connect(lambda: self._on_move(-1))
        move_row.addWidget(up_button)
        down_button = QPushButton(ar.MENU_CATEGORY_MOVE_DOWN_BUTTON)
        down_button.clicked.connect(lambda: self._on_move(1))
        move_row.addWidget(down_button)
        self._toggle_active_button = QPushButton(ar.MENU_CATEGORY_DEACTIVATE_BUTTON)
        self._toggle_active_button.clicked.connect(self._on_toggle_active)
        move_row.addWidget(self._toggle_active_button)
        layout.addLayout(move_row)

        self._actions_widgets = [rename_button, up_button, down_button, self._toggle_active_button]
        self._set_actions_enabled(False)

    def _set_actions_enabled(self, enabled: bool) -> None:
        for widget in self._actions_widgets:
            widget.setEnabled(enabled)

    def selected_category_id(self):
        item = self._list.currentItem()
        return item.data(_CATEGORY_ID_ROLE) if item is not None else None

    def reload(self) -> None:
        previously_selected = self.selected_category_id()
        self._list.blockSignals(True)
        self._list.clear()

        all_item = QListWidgetItem(ar.MENU_ALL_CATEGORIES)
        all_item.setData(_CATEGORY_ID_ROLE, None)
        self._list.addItem(all_item)
        if previously_selected is None:
            self._list.setCurrentItem(all_item)

        for category in categories_repo.list_categories(self._conn):
            status = "" if category["is_active"] else " ({0})".format(ar.USERS_INACTIVE_LABEL)
            item = QListWidgetItem(category["name"] + status)
            item.setData(_CATEGORY_ID_ROLE, category["id"])
            self._list.addItem(item)
            if category["id"] == previously_selected:
                self._list.setCurrentItem(item)
        self._list.blockSignals(False)
        self._message_label.setText("")
        self._refresh_actions_state()

    def _refresh_actions_state(self) -> None:
        category_id = self.selected_category_id()
        self._set_actions_enabled(category_id is not None)
        if category_id is not None:
            category = categories_repo.get_category(self._conn, category_id)
            self._rename_input.setText(category["name"])
            self._toggle_active_button.setText(
                ar.MENU_CATEGORY_REACTIVATE_BUTTON if not category["is_active"] else ar.MENU_CATEGORY_DEACTIVATE_BUTTON
            )

    def _on_selection_changed(self, _current, _previous) -> None:
        self._refresh_actions_state()
        self.selection_changed.emit(self.selected_category_id())

    def _on_add(self) -> None:
        name = self._new_name_input.text().strip()
        if not name:
            self._message_label.setText(ar.MENU_CATEGORY_ERROR_NAME_REQUIRED)
            return
        if categories_repo.is_name_duplicate(self._conn, name):
            self._message_label.setText(ar.MENU_CATEGORY_ERROR_NAME_TAKEN)
            return
        categories_repo.create_category(self._conn, name)
        self._new_name_input.clear()
        self.reload()
        self.categories_changed.emit()

    def _on_rename(self) -> None:
        category_id = self.selected_category_id()
        if category_id is None:
            return
        new_name = self._rename_input.text().strip()
        if not new_name:
            self._message_label.setText(ar.MENU_CATEGORY_ERROR_NAME_REQUIRED)
            return
        if categories_repo.is_name_duplicate(self._conn, new_name, exclude_id=category_id):
            self._message_label.setText(ar.MENU_CATEGORY_ERROR_NAME_TAKEN)
            return
        categories_repo.rename_category(self._conn, category_id, new_name)
        self.reload()
        self.categories_changed.emit()

    def _on_move(self, direction: int) -> None:
        category_id = self.selected_category_id()
        if category_id is None:
            return
        categories_repo.move_category(self._conn, category_id, direction)
        self.reload()
        self.categories_changed.emit()

    def _on_toggle_active(self) -> None:
        category_id = self.selected_category_id()
        if category_id is None:
            return
        category = categories_repo.get_category(self._conn, category_id)
        categories_repo.set_active(self._conn, category_id, not category["is_active"])
        self.reload()
        self.categories_changed.emit()
