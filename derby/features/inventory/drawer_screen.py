"""الخزنة: the cash drawer ledger (opening/deposit/withdrawal/count) plus
an owner-only "مراجعة البضاعة" (goods review) section. A cashier sees
the ledger and can operate the drawer, but never the goods-review
figures (stock value, unpaid supplier balances) -- see
permissions.view_goods_review.
"""
from __future__ import annotations

import sqlite3

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from derby.core.db import drawer_repo, purchases_repo, stock_items_repo, users_repo
from derby.core.i18n import ar
from derby.core.theme.table_style import centered_item, configure_table, fit_table_height, right_item
from derby.core.utils.money import format_egp
from derby.core.utils.time_utils import parse_utc_iso, to_cairo, utc_now
from derby.features.auth import permissions
from derby.features.inventory import drawer_service, stock_service
from derby.features.inventory.drawer_dialogs import (
    DepositDialog,
    DrawerCountDialog,
    OpenDrawerDialog,
    WithdrawalDialog,
)
from derby.features.reports.export_panel import ExportPanel
from derby.features.reports.export_service import export_drawer_csv, export_drawer_xlsx

_ENTRY_TYPE_LABELS = {
    "opening": ar.DRAWER_ENTRY_TYPE_OPENING,
    "sale_cash": ar.DRAWER_ENTRY_TYPE_SALE_CASH,
    "expense": ar.DRAWER_ENTRY_TYPE_EXPENSE,
    "purchase": ar.DRAWER_ENTRY_TYPE_PURCHASE,
    "deposit": ar.DRAWER_ENTRY_TYPE_DEPOSIT,
    "withdrawal": ar.DRAWER_ENTRY_TYPE_WITHDRAWAL,
    "refund": ar.DRAWER_ENTRY_TYPE_REFUND,
    "count_adjustment": ar.DRAWER_ENTRY_TYPE_COUNT_ADJUSTMENT,
}


class DrawerScreen(QWidget):
    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._is_owner = permissions.view_goods_review(user["role"])
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        title = QLabel(ar.DRAWER_TITLE)
        title.setProperty("role", "title")
        outer.addWidget(title)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        scroll_area.setWidget(content)
        outer.addWidget(scroll_area, 1)

        self._no_opening_label = QLabel(ar.DRAWER_NO_OPENING_MESSAGE)
        content_layout.addWidget(self._no_opening_label)
        self._expected_cash_label = QLabel("")
        self._expected_cash_label.setProperty("role", "title")
        content_layout.addWidget(self._expected_cash_label)

        buttons_row = QHBoxLayout()
        self._open_button = QPushButton(ar.DRAWER_OPEN_BUTTON)
        self._open_button.clicked.connect(self._on_open_drawer)
        buttons_row.addWidget(self._open_button)
        self._deposit_button = QPushButton(ar.DRAWER_DEPOSIT_BUTTON)
        self._deposit_button.clicked.connect(self._on_deposit)
        buttons_row.addWidget(self._deposit_button)
        self._withdrawal_button = QPushButton(ar.DRAWER_WITHDRAWAL_BUTTON)
        self._withdrawal_button.clicked.connect(self._on_withdrawal)
        buttons_row.addWidget(self._withdrawal_button)
        self._count_button = QPushButton(ar.DRAWER_COUNT_BUTTON)
        self._count_button.clicked.connect(self._on_count)
        buttons_row.addWidget(self._count_button)
        buttons_row.addStretch(1)
        content_layout.addLayout(buttons_row)

        content_layout.addWidget(QLabel(ar.DRAWER_LEDGER_TITLE))
        self._ledger_table = QTableWidget(0, 5)
        self._ledger_table.setHorizontalHeaderLabels(
            [
                ar.DRAWER_LEDGER_COLUMN_TIME, ar.DRAWER_LEDGER_COLUMN_TYPE, ar.DRAWER_LEDGER_COLUMN_AMOUNT,
                ar.DRAWER_LEDGER_COLUMN_USER, ar.DRAWER_LEDGER_COLUMN_NOTE,
            ]
        )
        configure_table(self._ledger_table, stretch_columns=(4,))
        content_layout.addWidget(self._ledger_table)

        count_history_header = QHBoxLayout()
        count_history_header.addWidget(QLabel(ar.DRAWER_COUNT_HISTORY_TITLE))
        self._count_user_filter = QComboBox()
        self._count_user_filter.addItem(ar.DRAWER_COUNT_FILTER_ALL_USERS, None)
        for user_row in users_repo.list_users(self._conn):
            self._count_user_filter.addItem(user_row["name"], user_row["id"])
        self._count_user_filter.currentIndexChanged.connect(self._reload_count_history)
        count_history_header.addWidget(self._count_user_filter)
        count_history_header.addStretch(1)
        content_layout.addLayout(count_history_header)

        self._export_panel = ExportPanel(lambda: "الخزنة_{0}".format(utc_now().strftime("%Y%m%d")))
        self._export_panel.set_exporters(
            csv_fn=lambda path: export_drawer_csv(drawer_repo.list_entries(self._conn), drawer_service.count_history(self._conn), path),
            xlsx_fn=lambda path: export_drawer_xlsx(drawer_repo.list_entries(self._conn), drawer_service.count_history(self._conn), path),
        )
        content_layout.addWidget(self._export_panel)

        self._count_history_table = QTableWidget(0, 4)
        self._count_history_table.setHorizontalHeaderLabels(
            [
                ar.DRAWER_COUNT_HISTORY_COLUMN_TIME, ar.DRAWER_COUNT_HISTORY_COLUMN_USER,
                ar.DRAWER_COUNT_HISTORY_COLUMN_EXPECTED, ar.DRAWER_COUNT_HISTORY_COLUMN_COUNTED,
            ]
        )
        configure_table(self._count_history_table, stretch_columns=(1,))
        content_layout.addWidget(self._count_history_table)

        self._goods_review_title = QLabel(ar.GOODS_REVIEW_TITLE)
        self._goods_review_title.setProperty("role", "title")
        content_layout.addWidget(self._goods_review_title)
        self._stock_value_label = QLabel("")
        content_layout.addWidget(self._stock_value_label)
        self._low_stock_label = QLabel("")
        content_layout.addWidget(self._low_stock_label)
        self._negative_stock_label = QLabel("")
        content_layout.addWidget(self._negative_stock_label)
        self._unpaid_suppliers_label = QLabel("")
        content_layout.addWidget(self._unpaid_suppliers_label)
        self._goods_summary_label = QLabel("")
        self._goods_summary_label.setProperty("role", "subtitle")
        content_layout.addWidget(self._goods_summary_label)

        for widget in (
            self._goods_review_title, self._stock_value_label, self._low_stock_label,
            self._negative_stock_label, self._unpaid_suppliers_label, self._goods_summary_label,
        ):
            widget.setVisible(self._is_owner)

        content_layout.addStretch(1)

    # --- actions -----------------------------------------------------------

    def _on_open_drawer(self) -> None:
        dialog = OpenDrawerDialog(self._conn, self._user, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self.reload()

    def _on_deposit(self) -> None:
        dialog = DepositDialog(self._conn, self._user, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self.reload()

    def _on_withdrawal(self) -> None:
        dialog = WithdrawalDialog(self._conn, self._user, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self.reload()

    def _on_count(self) -> None:
        dialog = DrawerCountDialog(self._conn, self._user, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self.reload()

    # --- rendering -----------------------------------------------------

    def reload(self) -> None:
        expected = drawer_service.expected_cash_piasters(self._conn)
        has_opening = expected is not None
        self._no_opening_label.setVisible(not has_opening)
        self._expected_cash_label.setVisible(has_opening)
        self._deposit_button.setEnabled(has_opening)
        self._withdrawal_button.setEnabled(has_opening)
        self._count_button.setEnabled(has_opening)
        if has_opening:
            self._expected_cash_label.setText(ar.DRAWER_EXPECTED_CASH_LABEL + ": " + format_egp(expected))

        self._reload_ledger()
        self._reload_count_history()
        if self._is_owner:
            self._reload_goods_review()

    def _reload_ledger(self) -> None:
        entries = list(reversed(drawer_repo.list_entries(self._conn)))
        self._ledger_table.setRowCount(len(entries))
        for row_index, entry in enumerate(entries):
            user = users_repo.get_user(self._conn, entry["user_id"]) if entry["user_id"] else None
            local_time = to_cairo(parse_utc_iso(entry["created_at_utc"])).strftime("%Y-%m-%d %H:%M")
            self._ledger_table.setItem(row_index, 0, centered_item(local_time))
            self._ledger_table.setItem(row_index, 1, centered_item(_ENTRY_TYPE_LABELS.get(entry["entry_type"], entry["entry_type"])))
            self._ledger_table.setItem(row_index, 2, centered_item(format_egp(entry["amount_delta_piasters"])))
            self._ledger_table.setItem(row_index, 3, centered_item(user["name"] if user else "—"))
            self._ledger_table.setItem(row_index, 4, right_item(entry["note"] or ""))
        fit_table_height(self._ledger_table, max_rows=10)

    def _reload_count_history(self) -> None:
        user_id = self._count_user_filter.currentData()
        counts = drawer_service.count_history(self._conn, user_id=user_id)
        self._count_history_table.setRowCount(len(counts))
        for row_index, count in enumerate(counts):
            user = users_repo.get_user(self._conn, count["user_id"])
            local_time = to_cairo(parse_utc_iso(count["created_at_utc"])).strftime("%Y-%m-%d %H:%M")
            self._count_history_table.setItem(row_index, 0, centered_item(local_time))
            self._count_history_table.setItem(row_index, 1, centered_item(user["name"] if user else "—"))
            self._count_history_table.setItem(row_index, 2, centered_item(format_egp(count["expected_piasters"])))
            self._count_history_table.setItem(row_index, 3, centered_item(format_egp(count["counted_piasters"])))
        fit_table_height(self._count_history_table, max_rows=8)

    def _reload_goods_review(self) -> None:
        stock_value = stock_service.stock_value_piasters(self._conn)
        low_stock = stock_items_repo.list_low_stock(self._conn)
        negative_items = [item for item in stock_items_repo.list_stock_items(self._conn, active_only=True) if item["current_qty"] < 0]
        unpaid_total = sum(
            purchase["total_cost_piasters"] for purchase in purchases_repo.list_purchases(self._conn, is_paid=False)
        )

        self._stock_value_label.setText(ar.GOODS_REVIEW_STOCK_VALUE_LABEL + ": " + format_egp(stock_value))
        self._low_stock_label.setText(ar.GOODS_REVIEW_LOW_STOCK_LABEL + ": {0}".format(len(low_stock)))
        self._negative_stock_label.setText(ar.GOODS_REVIEW_NEGATIVE_STOCK_LABEL + ": {0}".format(len(negative_items)))
        self._unpaid_suppliers_label.setText(ar.GOODS_REVIEW_UNPAID_SUPPLIERS_LABEL + ": " + format_egp(unpaid_total))

        cash = drawer_service.expected_cash_piasters(self._conn) or 0
        total = cash + stock_value - unpaid_total
        self._goods_summary_label.setText(ar.GOODS_REVIEW_SUMMARY_LABEL.format(total=format_egp(total)))

    def low_stock_count(self) -> int:
        return len(stock_items_repo.list_low_stock(self._conn))
