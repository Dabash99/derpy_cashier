"""The Tables screen: a "طلب جديد" section for starting a new takeaway
order plus cards for every currently open one, a grid of table cards
(free/busy, total, elapsed time, "من يوم سابق" badge). Clicking a card
hands off to the Cashier screen via the order_opened/table_selected
signals. Table management (add/rename/reorder/disable) is a separate
owner-only tab.
"""
from __future__ import annotations

import sqlite3

from PySide2.QtCore import Signal
from PySide2.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from derby.core.db import orders_repo, tables_repo
from derby.core.i18n import ar
from derby.core.theme.styled import enable_styled_background
from derby.core.theme.tab_bar import configure_tab_widget
from derby.core.utils.money import format_egp
from derby.core.utils.screen_refresh import RefreshOnChangeMixin
from derby.core.utils.time_utils import parse_utc_iso, to_cairo
from derby.features.auth import permissions
from derby.features.pos import orders_service
from derby.features.pos.cancel_order_ui import confirm_and_cancel_order
from derby.features.pos.invoice_dialog import print_invoice
from derby.features.pos.payment_dialog import PaymentDialog
from derby.features.tables.move_order_dialog import MoveOrderDialog
from derby.features.tables.tables_management_panel import TablesManagementPanel

_GRID_COLUMNS = 4


class TablesScreen(RefreshOnChangeMixin, QWidget):
    order_opened = Signal(int)
    # A free table card was clicked -- unlike order_opened, no order row
    # exists yet (lazy creation: see PosScreen.open_table).
    table_selected = Signal(int)
    # "+ طلب تيك أواي" was pressed -- payload is the optional label text
    # (may be ""). Like table_selected, no order row exists yet.
    takeaway_requested = Signal(str)

    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._build_ui()
        self.reload()
        self._init_refresh_on_change()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel(ar.TABLES_TITLE)
        title.setProperty("role", "title")
        layout.addWidget(title)

        tabs = QTabWidget()
        configure_tab_widget(tabs)
        tabs.addTab(self._build_grid_tab(), ar.TABLES_GRID_TAB)
        if permissions.manage_tables(self._user["role"]):
            self._management_panel = TablesManagementPanel(self._conn)
            self._management_panel.tables_changed.connect(self.reload)
            tabs.addTab(self._management_panel, ar.TABLES_MANAGE_TAB)
        layout.addWidget(tabs)

    def _build_grid_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        new_order_title = QLabel(ar.TABLES_NEW_ORDER_SECTION_TITLE)
        new_order_title.setProperty("role", "subtitle")
        layout.addWidget(new_order_title)

        new_order_row = QHBoxLayout()
        new_takeaway_button = QPushButton(ar.TABLES_NEW_TAKEAWAY_BUTTON)
        new_takeaway_button.setProperty("variant", "primary")
        new_takeaway_button.setMinimumHeight(56)
        new_takeaway_button.clicked.connect(self._on_new_takeaway)
        new_order_row.addWidget(new_takeaway_button, 1)
        self._takeaway_label_input = QLineEdit()
        self._takeaway_label_input.setPlaceholderText(ar.TABLES_TAKEAWAY_LABEL_PLACEHOLDER)
        self._takeaway_label_input.returnPressed.connect(self._on_new_takeaway)
        new_order_row.addWidget(self._takeaway_label_input, 1)
        layout.addLayout(new_order_row)

        self._takeaway_layout = QVBoxLayout()
        layout.addLayout(self._takeaway_layout)

        self._tables_grid = QGridLayout()
        layout.addLayout(self._tables_grid)

        layout.addStretch(1)
        return tab

    def _on_new_takeaway(self) -> None:
        label = self._takeaway_label_input.text().strip()
        self._takeaway_label_input.clear()
        self.takeaway_requested.emit(label)

    def reload(self) -> None:
        self._clear_layout(self._tables_grid)
        for index, table in enumerate(tables_repo.list_tables(self._conn, active_only=True)):
            row, col = divmod(index, _GRID_COLUMNS)
            self._tables_grid.addWidget(self._build_table_card(table), row, col)

        self._clear_layout(self._takeaway_layout)
        takeaway_orders = orders_repo.list_open_takeaway_orders(self._conn)
        if not takeaway_orders:
            empty_label = QLabel(ar.TABLES_NO_TAKEAWAY_ORDERS)
            empty_label.setProperty("role", "subtitle")
            self._takeaway_layout.addWidget(empty_label)
        for order in takeaway_orders:
            self._takeaway_layout.addWidget(self._build_takeaway_card(order))

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
            elif item.layout():
                TablesScreen._clear_layout(item.layout())

    def _build_table_card(self, table: sqlite3.Row) -> QWidget:
        card = QWidget()
        card_layout = QVBoxLayout(card)

        order = orders_repo.get_open_order_for_table(self._conn, table["id"])
        has_items = order is not None and len(orders_repo.list_order_items(self._conn, order["id"])) > 0

        if order is None:
            lines = [table["name"], ar.TABLES_FREE_LABEL]
            open_button = QPushButton("\n".join(lines))
            open_button.setMinimumSize(150, 110)
            open_button.clicked.connect(lambda: self.table_selected.emit(table["id"]))
            card_layout.addWidget(open_button)
            return card

        if not has_items:
            # Lazily-created order that never got an item (normally swept
            # by auto_cancel_empty_open_orders, but shown here too in case
            # that hasn't run yet) -- a plain one-click close, no approval
            # needed since there is nothing to lose.
            lines = [table["name"], ar.TABLES_EMPTY_ORDER_LABEL]
            info_label = QLabel("\n".join(lines))
            card_layout.addWidget(info_label)
            close_button = QPushButton(ar.TABLES_CLOSE_EMPTY_BUTTON)
            close_button.setMinimumSize(150, 48)
            close_button.clicked.connect(lambda: self._on_close_empty_order(order["id"]))
            card_layout.addWidget(close_button)
            return card

        lines = [table["name"], ar.TABLES_BUSY_LABEL]
        lines.append("{0}: {1}".format(ar.TABLES_TOTAL_LABEL, format_egp(order["total_piasters"])))
        opened_cairo = to_cairo(parse_utc_iso(order["opened_at_utc"]))
        lines.append(ar.TABLES_OPENED_AT_LABEL.format(time=opened_cairo.strftime("%H:%M")))
        if orders_service.is_from_previous_business_day(self._conn, order):
            lines.append(ar.POS_PREVIOUS_DAY_BADGE)

        open_button = QPushButton("\n".join(lines))
        open_button.setMinimumSize(150, 110)
        open_button.clicked.connect(lambda: self.order_opened.emit(order["id"]))
        card_layout.addWidget(open_button)

        move_button = QPushButton(ar.TABLES_MOVE_ORDER_BUTTON)
        move_button.clicked.connect(lambda: self._on_move_order(order["id"]))
        card_layout.addWidget(move_button)

        return card

    def _on_close_empty_order(self, order_id: int) -> None:
        orders_service.cancel(self._conn, order_id, self._user)
        self.reload()

    def _build_takeaway_card(self, order: sqlite3.Row) -> QWidget:
        card = QWidget()
        card.setProperty("variant", "card")
        enable_styled_background(card)
        outer = QVBoxLayout(card)

        items = orders_repo.list_order_items(self._conn, order["id"])
        opened_cairo = to_cairo(parse_utc_iso(order["opened_at_utc"]))

        header_row = QHBoxLayout()
        title_text = order["label"] or ar.TABLES_TAKEAWAY_ORDER_NUMBER.format(id=order["id"])
        name_label = QLabel(title_text)
        name_label.setProperty("role", "title")
        header_row.addWidget(name_label)
        header_row.addStretch(1)
        time_label = QLabel(ar.TABLES_OPENED_AT_LABEL.format(time=opened_cairo.strftime("%H:%M")))
        time_label.setProperty("role", "subtitle")
        header_row.addWidget(time_label)
        outer.addLayout(header_row)

        if not items:
            # Same leftover-empty-order case as a table card: one-click
            # close, no approval needed.
            outer.addWidget(QLabel(ar.TABLES_EMPTY_ORDER_LABEL))
            close_button = QPushButton(ar.TABLES_CLOSE_EMPTY_BUTTON)
            close_button.clicked.connect(lambda: self._on_close_empty_order(order["id"]))
            outer.addWidget(close_button)
            return card

        info_row = QHBoxLayout()
        info_row.addWidget(QLabel(ar.TABLES_ITEM_COUNT_LABEL.format(count=len(items))))
        info_row.addWidget(QLabel("{0}: {1}".format(ar.TABLES_TOTAL_LABEL, format_egp(order["total_piasters"]))))
        if orders_service.is_from_previous_business_day(self._conn, order):
            info_row.addWidget(QLabel(ar.POS_PREVIOUS_DAY_BADGE))
        info_row.addStretch(1)
        outer.addLayout(info_row)

        buttons_row = QHBoxLayout()
        open_button = QPushButton(ar.TABLES_OPEN_ORDER_BUTTON)
        open_button.clicked.connect(lambda: self.order_opened.emit(order["id"]))
        buttons_row.addWidget(open_button)
        pay_button = QPushButton(ar.POS_PAY_BUTTON)
        pay_button.setProperty("variant", "primary")
        pay_button.clicked.connect(lambda: self._on_quick_pay(order["id"]))
        buttons_row.addWidget(pay_button)
        move_button = QPushButton(ar.TABLES_MOVE_TO_TABLE_BUTTON)
        move_button.clicked.connect(lambda: self._on_move_to_table(order["id"]))
        buttons_row.addWidget(move_button)
        cancel_button = QPushButton(ar.POS_CANCEL_ORDER_BUTTON)
        cancel_button.setProperty("danger", "true")
        cancel_button.clicked.connect(lambda: self._on_cancel_takeaway(order["id"]))
        buttons_row.addWidget(cancel_button)
        outer.addLayout(buttons_row)

        return card

    def _on_quick_pay(self, order_id: int) -> None:
        order = orders_repo.get_order(self._conn, order_id)
        dialog = PaymentDialog(self._conn, order, self._user, parent=self)
        if dialog.exec_() == QDialog.Accepted and dialog.paid_order is not None:
            print_invoice(self._conn, dialog.paid_order["id"], is_copy=False, parent=self)
            self.reload()

    def _on_move_to_table(self, order_id: int) -> None:
        dialog = MoveOrderDialog(self._conn, order_id, self._user, parent=self, allowed_kinds=("table",))
        if dialog.exec_() == QDialog.Accepted:
            self.reload()

    def _on_cancel_takeaway(self, order_id: int) -> None:
        if confirm_and_cancel_order(self, self._conn, order_id, self._user):
            self.reload()

    def _on_move_order(self, order_id: int) -> None:
        dialog = MoveOrderDialog(self._conn, order_id, self._user, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self.reload()
