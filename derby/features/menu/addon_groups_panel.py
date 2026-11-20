"""Manage addon groups (e.g. "الحجم") and their addons (e.g. "كبير +٥ جنيه").
Groups on the right (RTL), that group's addons on the left.
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from PySide2.QtWidgets import (
    QCheckBox,
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

from derby.core.db import addons_repo
from derby.core.i18n import ar
from derby.core.utils.money import format_egp
from derby.features.menu.price_parsing import parse_product_price

_ID_ROLE = 1000


class AddonGroupsPanel(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._selected_group_id: Optional[int] = None
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        outer = QHBoxLayout(self)

        addons_column = QVBoxLayout()
        addons_column.addWidget(QLabel(ar.MENU_ADDON_GROUP_NAME_LABEL))
        self._addons_list = QListWidget()
        addons_column.addWidget(self._addons_list)

        addon_add_row = QHBoxLayout()
        self._addon_name_input = QLineEdit()
        self._addon_name_input.setPlaceholderText(ar.MENU_ADDON_NAME_LABEL)
        addon_add_row.addWidget(self._addon_name_input)
        self._addon_price_input = QLineEdit()
        self._addon_price_input.setPlaceholderText(ar.MENU_ADDON_PRICE_LABEL)
        addon_add_row.addWidget(self._addon_price_input)
        add_addon_button = QPushButton(ar.MENU_ADDON_ADD_BUTTON)
        add_addon_button.clicked.connect(self._on_add_addon)
        addon_add_row.addWidget(add_addon_button)
        addons_column.addLayout(addon_add_row)

        self._toggle_addon_button = QPushButton(ar.MENU_ADDON_GROUP_DEACTIVATE_BUTTON)
        self._toggle_addon_button.clicked.connect(self._on_toggle_addon_active)
        addons_column.addWidget(self._toggle_addon_button)

        outer.addLayout(addons_column, 2)

        groups_column = QVBoxLayout()
        groups_title = QLabel(ar.MENU_ADDON_GROUPS_TITLE)
        groups_title.setProperty("role", "title")
        groups_column.addWidget(groups_title)

        self._groups_list = QListWidget()
        self._groups_list.currentItemChanged.connect(self._on_group_selected)
        groups_column.addWidget(self._groups_list)

        self._message_label = QLabel("")
        self._message_label.setProperty("role", "error")
        self._message_label.setWordWrap(True)
        groups_column.addWidget(self._message_label)

        self._group_name_input = QLineEdit()
        self._group_name_input.setPlaceholderText(ar.MENU_ADDON_GROUP_NAME_LABEL)
        groups_column.addWidget(self._group_name_input)

        min_max_row = QHBoxLayout()
        min_max_row.addWidget(QLabel(ar.MENU_ADDON_GROUP_MIN_SELECT_LABEL))
        self._min_select_input = QSpinBox()
        self._min_select_input.setRange(0, 20)
        min_max_row.addWidget(self._min_select_input)
        groups_column.addLayout(min_max_row)

        max_row = QHBoxLayout()
        self._max_unlimited_checkbox = QCheckBox(ar.MENU_ADDON_GROUP_MAX_SELECT_LABEL)
        self._max_unlimited_checkbox.toggled.connect(lambda checked: self._max_select_input.setDisabled(checked))
        max_row.addWidget(self._max_unlimited_checkbox)
        self._max_select_input = QSpinBox()
        self._max_select_input.setRange(1, 20)
        max_row.addWidget(self._max_select_input)
        groups_column.addLayout(max_row)

        group_buttons_row = QHBoxLayout()
        save_group_button = QPushButton(ar.MENU_ADDON_GROUP_SAVE_BUTTON)
        save_group_button.clicked.connect(self._on_save_group)
        group_buttons_row.addWidget(save_group_button)
        add_group_button = QPushButton(ar.MENU_ADDON_GROUP_ADD_BUTTON)
        add_group_button.clicked.connect(self._on_add_group)
        group_buttons_row.addWidget(add_group_button)
        self._toggle_group_button = QPushButton(ar.MENU_ADDON_GROUP_DEACTIVATE_BUTTON)
        self._toggle_group_button.clicked.connect(self._on_toggle_group_active)
        group_buttons_row.addWidget(self._toggle_group_button)
        groups_column.addLayout(group_buttons_row)

        outer.addLayout(groups_column, 1)

    # --- groups ------------------------------------------------------------

    def reload(self) -> None:
        self._groups_list.blockSignals(True)
        self._groups_list.clear()
        for group in addons_repo.list_groups(self._conn):
            status = "" if group["is_active"] else " ({0})".format(ar.USERS_INACTIVE_LABEL)
            item = QListWidgetItem(group["name"] + status)
            item.setData(_ID_ROLE, group["id"])
            self._groups_list.addItem(item)
            if group["id"] == self._selected_group_id:
                self._groups_list.setCurrentItem(item)
        self._groups_list.blockSignals(False)
        self._reload_addons()

    def _on_group_selected(self, current: Optional[QListWidgetItem], _previous) -> None:
        self._selected_group_id = current.data(_ID_ROLE) if current is not None else None
        if self._selected_group_id is not None:
            group = addons_repo.get_group(self._conn, self._selected_group_id)
            self._group_name_input.setText(group["name"])
            self._min_select_input.setValue(group["min_select"])
            if group["max_select"] is None:
                self._max_unlimited_checkbox.setChecked(True)
            else:
                self._max_unlimited_checkbox.setChecked(False)
                self._max_select_input.setValue(group["max_select"])
            self._toggle_group_button.setText(
                ar.MENU_ADDON_GROUP_REACTIVATE_BUTTON if not group["is_active"] else ar.MENU_ADDON_GROUP_DEACTIVATE_BUTTON
            )
        self._reload_addons()

    def _on_add_group(self) -> None:
        name = self._group_name_input.text().strip()
        if not name:
            self._message_label.setText(ar.MENU_ADDON_GROUP_ERROR_NAME_REQUIRED)
            return
        addons_repo.create_group(self._conn, name)
        self._group_name_input.clear()
        self.reload()

    def _on_save_group(self) -> None:
        if self._selected_group_id is None:
            return
        name = self._group_name_input.text().strip()
        if not name:
            self._message_label.setText(ar.MENU_ADDON_GROUP_ERROR_NAME_REQUIRED)
            return
        max_select = None if self._max_unlimited_checkbox.isChecked() else self._max_select_input.value()
        addons_repo.update_group(self._conn, self._selected_group_id, name, self._min_select_input.value(), max_select)
        self._message_label.setText("")
        self.reload()

    def _on_toggle_group_active(self) -> None:
        if self._selected_group_id is None:
            return
        group = addons_repo.get_group(self._conn, self._selected_group_id)
        addons_repo.set_group_active(self._conn, self._selected_group_id, not group["is_active"])
        self.reload()

    # --- addons --------------------------------------------------------------

    def _reload_addons(self) -> None:
        self._addons_list.clear()
        if self._selected_group_id is None:
            return
        for addon in addons_repo.list_addons(self._conn, self._selected_group_id):
            status = "" if addon["is_active"] else " ({0})".format(ar.USERS_INACTIVE_LABEL)
            label = "{0} (+{1}){2}".format(addon["name"], format_egp(addon["price_delta_piasters"]), status)
            item = QListWidgetItem(label)
            item.setData(_ID_ROLE, addon["id"])
            self._addons_list.addItem(item)

    def _selected_addon_id(self):
        item = self._addons_list.currentItem()
        return item.data(_ID_ROLE) if item is not None else None

    def _on_add_addon(self) -> None:
        if self._selected_group_id is None:
            return
        name = self._addon_name_input.text().strip()
        if not name:
            self._message_label.setText(ar.MENU_ADDON_ERROR_NAME_REQUIRED)
            return
        try:
            price_delta = parse_product_price(self._addon_price_input.text() or "0")
        except ValueError:
            self._message_label.setText(ar.MENU_ADDON_ERROR_PRICE_INVALID)
            return
        addons_repo.create_addon(self._conn, self._selected_group_id, name, price_delta)
        self._addon_name_input.clear()
        self._addon_price_input.clear()
        self._message_label.setText("")
        self._reload_addons()

    def _on_toggle_addon_active(self) -> None:
        addon_id = self._selected_addon_id()
        if addon_id is None:
            return
        addons = {row["id"]: row for row in addons_repo.list_addons(self._conn, self._selected_group_id)}
        current = addons.get(addon_id)
        if current is None:
            return
        addons_repo.set_addon_active(self._conn, addon_id, not current["is_active"])
        self._reload_addons()
