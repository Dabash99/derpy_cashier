"""Sales log: paid/void orders for one business date. A cashier is locked
to today's business date; the owner can pick any date. Cancelled orders
never appear here -- they have no business_date (nothing was ever
invoiced), which matches "cancelling consumes no invoice number".
"""
from __future__ import annotations

import sqlite3
from datetime import time as time_of_day

from PySide2.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from derby.core.db import orders_repo, ps_devices_repo, settings_repo, tables_repo, users_repo
from derby.core.i18n import ar
from derby.core.theme.table_style import centered_item, configure_table, right_item
from derby.core.utils.business_date import business_date as compute_business_date
from derby.core.utils.money import format_egp
from derby.core.utils.screen_refresh import RefreshOnChangeMixin
from derby.core.utils.time_utils import parse_utc_iso, to_cairo, utc_now
from derby.features.auth import permissions
from derby.features.pos import orders_service
from derby.features.pos.invoice_dialog import print_invoice

_STATUS_LABELS = {
    "paid": ar.SALES_LOG_STATUS_PAID,
    "cancelled": ar.SALES_LOG_STATUS_CANCELLED,
    "void": ar.SALES_LOG_STATUS_VOID,
}
_METHOD_LABELS = {"cash": ar.PAYMENT_METHOD_CASH, "instapay": ar.PAYMENT_METHOD_INSTAPAY, "credit": ar.PAYMENT_METHOD_CREDIT}


def _method_key(order: sqlite3.Row) -> str:
    """آجل sales leave payment_method NULL and set customer_id instead
    (see orders_repo.mark_order_paid_on_credit)."""
    if order["customer_id"]:
        return "credit"
    return order["payment_method"]


class SalesLogScreen(RefreshOnChangeMixin, QWidget):
    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._can_view_all_dates = permissions.view_sales_all_dates(user["role"])
        self._build_ui()
        self.reload()
        self._init_refresh_on_change()

    def _today_business_date(self) -> str:
        close_time_text = settings_repo.get(self._conn, "business_close_time", "23:59") or "23:59"
        hour_str, minute_str = close_time_text.split(":")
        close_time = time_of_day(int(hour_str), int(minute_str))
        return compute_business_date(utc_now(), close_time).isoformat()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel(ar.SALES_LOG_TITLE)
        title.setProperty("role", "title")
        layout.addWidget(title)

        filters_row = QHBoxLayout()
        filters_row.addWidget(QLabel(ar.SALES_LOG_DATE_LABEL))
        self._date_input = QLineEdit(self._today_business_date())
        self._date_input.setEnabled(self._can_view_all_dates)
        self._date_input.editingFinished.connect(self.reload)
        filters_row.addWidget(self._date_input)

        filters_row.addWidget(QLabel(ar.SALES_LOG_METHOD_FILTER_LABEL))
        self._method_filter = QComboBox()
        self._method_filter.addItem(ar.SALES_LOG_FILTER_ALL, None)
        self._method_filter.addItem(ar.PAYMENT_METHOD_CASH, "cash")
        self._method_filter.addItem(ar.PAYMENT_METHOD_INSTAPAY, "instapay")
        self._method_filter.addItem(ar.PAYMENT_METHOD_CREDIT, "credit")
        self._method_filter.currentIndexChanged.connect(self.reload)
        filters_row.addWidget(self._method_filter)

        filters_row.addWidget(QLabel(ar.SALES_LOG_STATUS_FILTER_LABEL))
        self._status_filter = QComboBox()
        self._status_filter.addItem(ar.SALES_LOG_FILTER_ALL, None)
        self._status_filter.addItem(ar.SALES_LOG_STATUS_PAID, "paid")
        self._status_filter.addItem(ar.SALES_LOG_STATUS_VOID, "void")
        self._status_filter.currentIndexChanged.connect(self.reload)
        filters_row.addWidget(self._status_filter)
        layout.addLayout(filters_row)

        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(
            [
                ar.SALES_LOG_COLUMN_INVOICE,
                ar.SALES_LOG_COLUMN_TIME,
                ar.SALES_LOG_COLUMN_TABLE,
                ar.SALES_LOG_COLUMN_TOTAL,
                ar.SALES_LOG_COLUMN_METHOD,
                ar.SALES_LOG_COLUMN_CASHIER,
                ar.SALES_LOG_COLUMN_STATUS,
            ]
        )
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.cellDoubleClicked.connect(self._on_row_double_clicked)
        configure_table(
            self._table,
            stretch_columns=(2, 5),  # table/device name, cashier name
            fixed_widths={0: 70, 1: 70, 3: 110, 4: 90, 6: 90},
        )
        layout.addWidget(self._table)

        actions_row = QHBoxLayout()
        self._void_button = QPushButton(ar.SALES_LOG_VOID_BUTTON)
        self._void_button.setProperty("danger", "true")
        self._void_button.setVisible(permissions.void_paid_order(self._user["role"]))
        self._void_button.clicked.connect(self._on_void_clicked)
        actions_row.addWidget(self._void_button)
        layout.addLayout(actions_row)

        self._totals_label = QLabel("")
        self._totals_label.setWordWrap(True)
        layout.addWidget(self._totals_label)

    def _selected_date(self) -> str:
        if self._can_view_all_dates:
            return self._date_input.text().strip()
        return self._today_business_date()

    def reload(self) -> None:
        if not self._can_view_all_dates:
            self._date_input.setText(self._today_business_date())
        selected_date = self._selected_date()

        status_filter = self._status_filter.currentData()
        method_filter = self._method_filter.currentData()
        orders = orders_repo.list_orders(self._conn, business_date=selected_date, status=status_filter)
        if method_filter is not None:
            orders = [order for order in orders if _method_key(order) == method_filter]

        self._orders_by_row = orders
        self._table.setRowCount(len(orders))
        for row, order in enumerate(orders):
            self._populate_row(row, order)

        self._update_totals(selected_date)

    def _populate_row(self, row: int, order: sqlite3.Row) -> None:
        cairo_time = to_cairo(parse_utc_iso(order["paid_at_utc"])).strftime("%H:%M") if order["paid_at_utc"] else ""
        table_text = order["label"] or ar.INVOICE_TAKEAWAY_LABEL
        if order["table_id"]:
            table = tables_repo.get_table(self._conn, order["table_id"])
            table_text = table["name"] if table is not None else ""
        elif order["device_id"]:
            device = ps_devices_repo.get_device(self._conn, order["device_id"])
            table_text = device["name"] if device is not None else ""
        cashier_name = ""
        if order["paid_by"]:
            cashier = users_repo.get_user(self._conn, order["paid_by"])
            cashier_name = cashier["name"] if cashier is not None else ""
        method_text = _METHOD_LABELS.get(_method_key(order), order["payment_method"] or "")
        status_text = _STATUS_LABELS.get(order["status"], order["status"])

        makers = [centered_item, centered_item, right_item, centered_item, centered_item, right_item, centered_item]
        values = [
            str(order["invoice_no"] or ""),
            cairo_time,
            table_text,
            format_egp(order["total_piasters"]),
            method_text,
            cashier_name,
            status_text,
        ]
        for column, (value, make_item) in enumerate(zip(values, makers)):
            self._table.setItem(row, column, make_item(value))

    def _update_totals(self, selected_date: str) -> None:
        all_paid = orders_repo.list_orders(self._conn, business_date=selected_date, status="paid")
        count = len(all_paid)
        total = sum(order["total_piasters"] for order in all_paid)
        cash_total = sum(order["total_piasters"] for order in all_paid if _method_key(order) == "cash")
        instapay_total = sum(order["total_piasters"] for order in all_paid if _method_key(order) == "instapay")
        credit_total = sum(order["total_piasters"] for order in all_paid if _method_key(order) == "credit")
        self._totals_label.setText(
            ar.SALES_LOG_TOTALS_SUMMARY.format(
                count=count, total=format_egp(total), cash=format_egp(cash_total), instapay=format_egp(instapay_total),
                credit=format_egp(credit_total),
            )
        )

    def _selected_order(self):
        row = self._table.currentRow()
        if row < 0 or row >= len(self._orders_by_row):
            return None
        return self._orders_by_row[row]

    def _on_row_double_clicked(self, row: int, _column: int) -> None:
        if 0 <= row < len(self._orders_by_row):
            order = self._orders_by_row[row]
            print_invoice(self._conn, order["id"], is_copy=True, parent=self)

    def _on_void_clicked(self) -> None:
        order = self._selected_order()
        if order is None or order["status"] != "paid":
            return
        reason, confirmed = QInputDialog.getText(self, ar.SALES_LOG_VOID_DIALOG_TITLE, ar.SALES_LOG_VOID_REASON_LABEL)
        if not confirmed or not reason.strip():
            return
        try:
            orders_service.void(self._conn, order["id"], reason, self._user)
        except Exception as error:  # noqa: BLE001 -- surfaced to the owner directly
            QMessageBox.warning(self, ar.GENERIC_ERROR_TITLE, str(error))
            return
        self.reload()
