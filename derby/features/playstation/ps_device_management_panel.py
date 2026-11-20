"""Owner-only: add/rename/reorder/disable PlayStation devices and set
their Single/Multi hourly rates. Disabling a busy device (open order or
running session) is rejected -- the one business rule beyond plain CRUD.
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

from derby.core.db import ps_devices_repo
from derby.core.i18n import ar
from derby.core.utils.money import piasters_to_plain_text
from derby.features.menu.price_parsing import parse_product_price
from derby.features.playstation import ps_service
from derby.features.pos.exceptions import SessionRunningError

_DEVICE_ID_ROLE = 1000


class PsDeviceManagementPanel(QWidget):
    devices_changed = Signal()

    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel(ar.PS_TITLE)
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
        self._new_name_input.setPlaceholderText(ar.PS_DEVICE_NAME_PLACEHOLDER)
        add_row.addWidget(self._new_name_input)
        add_button = QPushButton(ar.PS_DEVICE_ADD_BUTTON)
        add_button.clicked.connect(self._on_add)
        add_row.addWidget(add_button)
        layout.addLayout(add_row)

        rename_row = QHBoxLayout()
        self._rename_input = QLineEdit()
        rename_row.addWidget(self._rename_input)
        rename_button = QPushButton(ar.PS_DEVICE_RENAME_BUTTON)
        rename_button.clicked.connect(self._on_rename)
        rename_row.addWidget(rename_button)
        layout.addLayout(rename_row)

        rates_row = QHBoxLayout()
        rates_row.addWidget(QLabel(ar.PS_DEVICE_SINGLE_RATE_LABEL))
        self._single_rate_input = QLineEdit()
        rates_row.addWidget(self._single_rate_input)
        rates_row.addWidget(QLabel(ar.PS_DEVICE_MULTI_RATE_LABEL))
        self._multi_rate_input = QLineEdit()
        rates_row.addWidget(self._multi_rate_input)
        save_rates_button = QPushButton(ar.PS_DEVICE_SAVE_RATES_BUTTON)
        save_rates_button.clicked.connect(self._on_save_rates)
        rates_row.addWidget(save_rates_button)
        layout.addLayout(rates_row)

        actions_row = QHBoxLayout()
        up_button = QPushButton(ar.MENU_CATEGORY_MOVE_UP_BUTTON)
        up_button.clicked.connect(lambda: self._on_move(-1))
        actions_row.addWidget(up_button)
        down_button = QPushButton(ar.MENU_CATEGORY_MOVE_DOWN_BUTTON)
        down_button.clicked.connect(lambda: self._on_move(1))
        actions_row.addWidget(down_button)

        self._toggle_active_button = QPushButton(ar.PS_DEVICE_DEACTIVATE_BUTTON)
        self._toggle_active_button.clicked.connect(self._on_toggle_active)
        actions_row.addWidget(self._toggle_active_button)
        layout.addLayout(actions_row)

        self._actions = [
            rename_button, save_rates_button, up_button, down_button, self._toggle_active_button,
        ]
        self._set_actions_enabled(False)

    def _set_actions_enabled(self, enabled: bool) -> None:
        for widget in self._actions:
            widget.setEnabled(enabled)

    def _selected_device_id(self):
        item = self._list.currentItem()
        return item.data(_DEVICE_ID_ROLE) if item is not None else None

    def reload(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for device in ps_devices_repo.list_devices(self._conn):
            status = "" if device["is_active"] else " ({0})".format(ar.USERS_INACTIVE_LABEL)
            item = QListWidgetItem(device["name"] + status)
            item.setData(_DEVICE_ID_ROLE, device["id"])
            self._list.addItem(item)
        self._list.blockSignals(False)
        self._message_label.setText("")
        self._refresh_actions_state()

    def _refresh_actions_state(self) -> None:
        device_id = self._selected_device_id()
        self._set_actions_enabled(device_id is not None)
        if device_id is not None:
            device = ps_devices_repo.get_device(self._conn, device_id)
            self._rename_input.setText(device["name"])
            self._single_rate_input.setText(piasters_to_plain_text(device["single_rate_piasters_per_hour"]))
            self._multi_rate_input.setText(piasters_to_plain_text(device["multi_rate_piasters_per_hour"]))
            self._toggle_active_button.setText(
                ar.PS_DEVICE_REACTIVATE_BUTTON if not device["is_active"] else ar.PS_DEVICE_DEACTIVATE_BUTTON
            )

    def _on_add(self) -> None:
        name = self._new_name_input.text().strip()
        if not name:
            self._message_label.setText(ar.PS_DEVICE_ERROR_NAME_REQUIRED)
            return
        ps_service.add_device(self._conn, name, self._user["id"])
        self._new_name_input.clear()
        self.reload()
        self.devices_changed.emit()

    def _on_rename(self) -> None:
        device_id = self._selected_device_id()
        if device_id is None:
            return
        new_name = self._rename_input.text().strip()
        if not new_name:
            self._message_label.setText(ar.PS_DEVICE_ERROR_NAME_REQUIRED)
            return
        ps_service.rename_device(self._conn, device_id, new_name, self._user["id"])
        self.reload()
        self.devices_changed.emit()

    def _on_save_rates(self) -> None:
        device_id = self._selected_device_id()
        if device_id is None:
            return
        try:
            single_rate = parse_product_price(self._single_rate_input.text())
            multi_rate = parse_product_price(self._multi_rate_input.text())
        except ValueError:
            self._message_label.setText(ar.PS_DEVICE_ERROR_RATE_INVALID)
            return
        ps_service.set_rates(self._conn, device_id, single_rate, multi_rate, self._user["id"])
        self.reload()
        self.devices_changed.emit()

    def _on_move(self, direction: int) -> None:
        device_id = self._selected_device_id()
        if device_id is None:
            return
        ps_service.move_device(self._conn, device_id, direction, self._user["id"])
        self.reload()
        self.devices_changed.emit()

    def _on_toggle_active(self) -> None:
        device_id = self._selected_device_id()
        if device_id is None:
            return
        device = ps_devices_repo.get_device(self._conn, device_id)
        try:
            ps_service.set_device_active(self._conn, device_id, not device["is_active"], self._user["id"])
        except SessionRunningError:
            self._message_label.setText(ar.PS_DEVICE_ERROR_CANNOT_DISABLE_BUSY)
            return
        self.reload()
        self.devices_changed.emit()
