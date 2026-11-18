"""The Tables screen: a grid of table cards (free/busy, total, elapsed
time, "من يوم سابق" badge) plus an open-takeaway list. Clicking a card
hands off to the Cashier screen via the order_opened signal. Table
management (add/rename/reorder/disable) is a separate owner-only tab.
"""
from __future__ import annotations

import sqlite3

from PySide2.QtCore import Signal
from PySide2.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from derby.core.db import orders_repo, tables_repo
from derby.core.i18n import ar
from derby.core.utils.money import format_egp
from derby.core.utils.time_utils import parse_utc_iso, to_cairo
from derby.features.auth import permissions
from derby.features.pos import orders_service
from derby.features.tables.move_order_dialog import MoveOrderDialog
from derby.features.tables.tables_management_panel import TablesManagementPanel

_GRID_COLUMNS = 4


class TablesScreen(QWidget):
    order_opened = Signal(int)

    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel(ar.TABLES_TITLE)
        title.setProperty("role", "title")
        layout.addWidget(title)

        tabs = QTabWidget()
        tabs.addTab(self._build_grid_tab(), ar.TABLES_GRID_TAB)
        if permissions.manage_tables(self._user["role"]):
            self._management_panel = TablesManagementPanel(self._conn)
            self._management_panel.tables_changed.connect(self.reload)
            tabs.addTab(self._management_panel, ar.TABLES_MANAGE_TAB)
        layout.addWidget(tabs)

    def _build_grid_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self._tables_grid = QGridLayout()
        layout.addLayout(self._tables_grid)

        layout.addWidget(QLabel(ar.TABLES_TAKEAWAY_SECTION))
        self._takeaway_layout = QVBoxLayout()
        layout.addLayout(self._takeaway_layout)

        layout.addStretch(1)
        return tab

    def reload(self) -> None:
        self._clear_layout(self._tables_grid)
        for index, table in enumerate(tables_repo.list_tables(self._conn, active_only=True)):
            row, col = divmod(index, _GRID_COLUMNS)
            self._tables_grid.addWidget(self._build_table_card(table), row, col)

        self._clear_layout(self._takeaway_layout)
        for order in orders_repo.list_open_takeaway_orders(self._conn):
            self._takeaway_layout.addWidget(self._build_takeaway_row(order))

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                TablesScreen._clear_layout(item.layout())

    def _build_table_card(self, table: sqlite3.Row) -> QWidget:
        card = QWidget()
        card_layout = QVBoxLayout(card)

        order = orders_repo.get_open_order_for_table(self._conn, table["id"])
        lines = [table["name"]]
        if order is None:
            lines.append(ar.TABLES_FREE_LABEL)
        else:
            lines.append(ar.TABLES_BUSY_LABEL)
            lines.append("{0}: {1}".format(ar.TABLES_TOTAL_LABEL, format_egp(order["total_piasters"])))
            opened_cairo = to_cairo(parse_utc_iso(order["opened_at_utc"]))
            lines.append(ar.TABLES_OPENED_AT_LABEL.format(time=opened_cairo.strftime("%H:%M")))
            if orders_service.is_from_previous_business_day(self._conn, order):
                lines.append(ar.POS_PREVIOUS_DAY_BADGE)

        open_button = QPushButton("\n".join(lines))
        open_button.setMinimumSize(150, 110)
        open_button.clicked.connect(lambda: self._on_table_clicked(table["id"]))
        card_layout.addWidget(open_button)

        if order is not None:
            move_button = QPushButton(ar.TABLES_MOVE_ORDER_BUTTON)
            move_button.clicked.connect(lambda: self._on_move_order(order["id"]))
            card_layout.addWidget(move_button)

        return card

    def _build_takeaway_row(self, order: sqlite3.Row) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        opened_cairo = to_cairo(parse_utc_iso(order["opened_at_utc"]))
        label = "{0} — {1} — {2}".format(
            ar.TABLES_TAKEAWAY_SECTION, format_egp(order["total_piasters"]), opened_cairo.strftime("%H:%M")
        )
        open_button = QPushButton(label)
        open_button.clicked.connect(lambda: self.order_opened.emit(order["id"]))
        row_layout.addWidget(open_button)

        move_button = QPushButton(ar.TABLES_MOVE_ORDER_BUTTON)
        move_button.clicked.connect(lambda: self._on_move_order(order["id"]))
        row_layout.addWidget(move_button)
        return row

    def _on_table_clicked(self, table_id: int) -> None:
        order = orders_service.get_or_create_table_order(self._conn, table_id, self._user["id"])
        self.order_opened.emit(order["id"])

    def _on_move_order(self, order_id: int) -> None:
        dialog = MoveOrderDialog(self._conn, order_id, self._user, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self.reload()
