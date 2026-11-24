"""العملاء: search/balance/last-activity/overdue list, add/edit/
deactivate, كشف حساب, تسجيل دفعة, تذكير واتساب.
"""
from __future__ import annotations

import sqlite3

from PySide2.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from derby.core.db import customer_ledger_repo, customers_repo, settings_repo
from derby.core.i18n import ar
from derby.core.integrations import whatsapp
from derby.core.theme.table_style import centered_item, configure_table, mark_as_danger, right_item
from derby.core.utils.money import format_egp, parse_egp_input
from derby.core.utils.screen_refresh import RefreshOnChangeMixin
from derby.core.utils.time_utils import parse_utc_iso, to_cairo, utc_now
from derby.features.customers import customer_service
from derby.features.customers.customer_statement_dialog import CustomerStatementDialog
from derby.features.customers.exceptions import CustomerError


class CustomersScreen(RefreshOnChangeMixin, QWidget):
    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._rows_by_index = []
        self._selected_customer_id = None
        self._build_ui()
        self.reload()
        self._init_refresh_on_change()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel(ar.CUSTOMERS_TITLE)
        title.setProperty("role", "title")
        layout.addWidget(title)

        search_row = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(ar.CUSTOMERS_SEARCH_PLACEHOLDER)
        self._search_input.textChanged.connect(self.reload)
        search_row.addWidget(self._search_input)
        layout.addLayout(search_row)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            [
                ar.CUSTOMERS_COLUMN_NAME, ar.CUSTOMERS_COLUMN_PHONE, ar.CUSTOMERS_COLUMN_BALANCE,
                ar.CUSTOMERS_COLUMN_LAST_ACTIVITY, ar.CUSTOMERS_COLUMN_OVERDUE,
            ]
        )
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.currentCellChanged.connect(self._on_selection_changed)
        configure_table(self._table, stretch_columns=(0,), fixed_widths={1: 110, 2: 110, 3: 120, 4: 70})
        layout.addWidget(self._table)

        add_row = QHBoxLayout()
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText(ar.CUSTOMERS_NAME_LABEL)
        add_row.addWidget(self._name_input)
        self._phone_input = QLineEdit()
        self._phone_input.setPlaceholderText(ar.CUSTOMERS_PHONE_LABEL)
        add_row.addWidget(self._phone_input)
        self._limit_input = QSpinBox()
        self._limit_input.setRange(0, 1_000_000)
        self._limit_input.setSuffix(" ج.م")
        add_row.addWidget(self._limit_input)
        add_button = QPushButton(ar.CUSTOMERS_ADD_BUTTON)
        add_button.clicked.connect(self._on_add)
        add_row.addWidget(add_button)
        layout.addLayout(add_row)

        actions_row = QHBoxLayout()
        self._statement_button = QPushButton(ar.CUSTOMERS_STATEMENT_BUTTON)
        self._statement_button.clicked.connect(self._on_statement)
        actions_row.addWidget(self._statement_button)

        self._payment_amount_input = QLineEdit()
        self._payment_amount_input.setPlaceholderText(ar.CUSTOMERS_PAYMENT_AMOUNT_LABEL)
        actions_row.addWidget(self._payment_amount_input)
        self._record_cash_button = QPushButton(ar.CUSTOMERS_RECORD_PAYMENT_BUTTON + " (" + ar.PAYMENT_METHOD_CASH + ")")
        self._record_cash_button.clicked.connect(lambda: self._on_record_payment("cash"))
        actions_row.addWidget(self._record_cash_button)
        self._record_instapay_button = QPushButton(ar.CUSTOMERS_RECORD_PAYMENT_BUTTON + " (" + ar.PAYMENT_METHOD_INSTAPAY + ")")
        self._record_instapay_button.clicked.connect(lambda: self._on_record_payment("instapay"))
        actions_row.addWidget(self._record_instapay_button)

        self._reminder_button = QPushButton(ar.CUSTOMERS_WHATSAPP_REMINDER_BUTTON)
        self._reminder_button.clicked.connect(self._on_reminder)
        actions_row.addWidget(self._reminder_button)

        self._deactivate_button = QPushButton(ar.CUSTOMERS_DEACTIVATE_BUTTON)
        self._deactivate_button.clicked.connect(self._on_toggle_active)
        actions_row.addWidget(self._deactivate_button)
        layout.addLayout(actions_row)

        self._message_label = QLabel("")
        self._message_label.setWordWrap(True)
        layout.addWidget(self._message_label)

        self._set_selection_actions_enabled(False)

    def _set_selection_actions_enabled(self, enabled: bool) -> None:
        for button in (
            self._statement_button, self._record_cash_button, self._record_instapay_button,
            self._reminder_button, self._deactivate_button,
        ):
            button.setEnabled(enabled)

    def reload(self) -> None:
        overdue_days = int(settings_repo.get(self._conn, "customer_overdue_days", "14") or "14")
        today = to_cairo(utc_now()).date()
        search_text = self._search_input.text().strip() or None
        customers = customers_repo.list_customers(self._conn, active_only=False, search_text=search_text)
        self._rows_by_index = customers
        self._table.setRowCount(len(customers))
        for row_index, customer in enumerate(customers):
            balance = customer_service.balance_piasters(self._conn, customer["id"])
            last_activity = customer_ledger_repo.last_activity_at(self._conn, customer["id"])
            last_activity_text = to_cairo(parse_utc_iso(last_activity)).strftime("%Y-%m-%d") if last_activity else ""
            overdue = customer_service.is_overdue(self._conn, customer["id"], overdue_days, today)
            makers = [right_item, centered_item, centered_item, centered_item, centered_item]
            values = [
                customer["name"], customer["phone"] or "", format_egp(balance), last_activity_text,
                "!" if overdue else "",
            ]
            for column, (value, make_item) in enumerate(zip(values, makers)):
                item = make_item(value)
                if overdue:
                    item = mark_as_danger(item)
                self._table.setItem(row_index, column, item)

    def _on_selection_changed(self, row: int, *_args) -> None:
        if 0 <= row < len(self._rows_by_index):
            self._selected_customer_id = self._rows_by_index[row]["id"]
            self._set_selection_actions_enabled(True)
        else:
            self._selected_customer_id = None
            self._set_selection_actions_enabled(False)

    def _on_add(self) -> None:
        try:
            customer_service.create_customer(
                self._conn, self._name_input.text(), self._phone_input.text().strip() or None, None,
                self._limit_input.value() * 100 or None, self._user,
            )
        except CustomerError as error:
            self._message_label.setText(str(error))
            return
        self._name_input.clear()
        self._phone_input.clear()
        self._message_label.setText(ar.CUSTOMERS_SAVED_MESSAGE)
        self.reload()

    def _on_statement(self) -> None:
        if self._selected_customer_id is None:
            return
        dialog = CustomerStatementDialog(self._conn, self._selected_customer_id, parent=self)
        dialog.exec_()
        self.reload()

    def _on_record_payment(self, method: str) -> None:
        if self._selected_customer_id is None:
            return
        try:
            amount = parse_egp_input(self._payment_amount_input.text())
        except ValueError:
            self._message_label.setText(ar.DRAWER_ERROR_AMOUNT_INVALID)
            return
        try:
            customer_service.record_payment(self._conn, self._selected_customer_id, amount, method, self._user)
        except CustomerError as error:
            self._message_label.setText(str(error))
            return
        self._payment_amount_input.clear()
        self._message_label.setText(ar.CUSTOMERS_PAYMENT_SUCCESS)
        self.reload()

    def _on_reminder(self) -> None:
        if self._selected_customer_id is None:
            return
        customer = customers_repo.get_customer(self._conn, self._selected_customer_id)
        balance = customer_service.balance_piasters(self._conn, self._selected_customer_id)
        cafe_name = settings_repo.get(self._conn, "cafe_name", "") or "ديربي"
        text = ar.CUSTOMERS_REMINDER_TEXT.format(cafe=cafe_name, balance=format_egp(balance))
        method = settings_repo.get(self._conn, "whatsapp_method", whatsapp.METHOD_DESKTOP) or whatsapp.METHOD_DESKTOP
        result = whatsapp.open_report(method, customer["phone"] or "", text)
        self._message_label.setText(result.message)

    def _on_toggle_active(self) -> None:
        if self._selected_customer_id is None:
            return
        customer = customers_repo.get_customer(self._conn, self._selected_customer_id)
        customer_service.set_active(self._conn, self._selected_customer_id, not customer["is_active"], self._user)
        self._message_label.setText(ar.CUSTOMERS_SAVED_MESSAGE)
        self.reload()
