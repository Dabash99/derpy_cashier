"""Move an order to a different free table OR a free PlayStation device.
No merging -- a busy target is simply rejected."""
from __future__ import annotations

import sqlite3

from PySide2.QtWidgets import QDialog, QDialogButtonBox, QLabel, QListWidget, QListWidgetItem, QVBoxLayout

from derby.core.db import orders_repo, ps_devices_repo, tables_repo
from derby.core.i18n import ar
from derby.features.pos import orders_service
from derby.features.pos.exceptions import DeviceBusyError, SessionRunningError, TableBusyError

_TARGET_ROLE = 1000


class MoveOrderDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, order_id: int, requesting_user: sqlite3.Row, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._order_id = order_id
        self._requesting_user = requesting_user
        self.setWindowTitle(ar.TABLES_MOVE_ORDER_TITLE)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(ar.TABLES_MOVE_ORDER_CHOOSE_TARGET))

        self._list = QListWidget()
        order = orders_repo.get_order(self._conn, self._order_id)
        for table in tables_repo.list_tables(self._conn, active_only=True):
            if table["id"] == order["table_id"]:
                continue
            if orders_repo.get_open_order_for_table(self._conn, table["id"]) is not None:
                continue
            item = QListWidgetItem(table["name"])
            item.setData(_TARGET_ROLE, ("table", table["id"]))
            self._list.addItem(item)
        for device in ps_devices_repo.list_devices(self._conn, active_only=True):
            if device["id"] == order["device_id"]:
                continue
            if orders_repo.get_open_order_for_device(self._conn, device["id"]) is not None:
                continue
            item = QListWidgetItem("{0} ({1})".format(device["name"], ar.SIDEBAR_PLAYSTATION))
            item.setData(_TARGET_ROLE, ("device", device["id"]))
            self._list.addItem(item)
        layout.addWidget(self._list)

        self._error_label = QLabel("")
        self._error_label.setProperty("role", "error")
        layout.addWidget(self._error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(ar.GENERIC_OK)
        buttons.button(QDialogButtonBox.Cancel).setText(ar.GENERIC_CANCEL)
        buttons.accepted.connect(self._on_confirm)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_confirm(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        kind, target_id = item.data(_TARGET_ROLE)
        try:
            if kind == "table":
                orders_service.move_order(self._conn, self._order_id, target_id, self._requesting_user)
            else:
                orders_service.move_order(self._conn, self._order_id, None, self._requesting_user, target_device_id=target_id)
        except (TableBusyError, DeviceBusyError):
            self._error_label.setText(ar.TABLES_MOVE_ERROR_BUSY)
            return
        except SessionRunningError:
            self._error_label.setText(ar.PS_ERROR_SESSION_RUNNING)
            return
        self.accept()
