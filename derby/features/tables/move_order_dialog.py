"""Move an order to a different (free) table. No merging -- a busy
target is simply rejected."""
from __future__ import annotations

import sqlite3

from PySide2.QtWidgets import QDialog, QDialogButtonBox, QLabel, QListWidget, QListWidgetItem, QVBoxLayout

from derby.core.db import orders_repo, tables_repo
from derby.core.i18n import ar
from derby.features.pos import orders_service
from derby.features.pos.exceptions import TableBusyError

_TABLE_ID_ROLE = 1000


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
            item.setData(_TABLE_ID_ROLE, table["id"])
            self._list.addItem(item)
        layout.addWidget(self._list)

        self._error_label = QLabel("")
        self._error_label.setProperty("role", "error")
        layout.addWidget(self._error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_confirm)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_confirm(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        target_table_id = item.data(_TABLE_ID_ROLE)
        try:
            orders_service.move_order(self._conn, self._order_id, target_table_id, self._requesting_user)
        except TableBusyError:
            self._error_label.setText(ar.TABLES_MOVE_ERROR_BUSY)
            return
        self.accept()
