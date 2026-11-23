"""The "بيع بالآجل" sub-dialog opened from the payment dialog: pick (or
quickly create) a customer, confirm -- if the sale would exceed their
credit limit, an owner PIN is requested automatically (same reusable
prompt the discount flow uses) before the sale is retried.
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from PySide2.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from derby.core.db import customers_repo
from derby.core.i18n import ar
from derby.core.utils.money import format_egp
from derby.features.customers import customer_service
from derby.features.customers.exceptions import CustomerError, NameRequiredError
from derby.features.pos.exceptions import ApprovalLockedOutError, CreditNotAllowedError, WrongApprovalPinError
from derby.features.pos.owner_pin_prompt import ask_for_owner_pin


class CreditSaleDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, order: sqlite3.Row, requesting_user: sqlite3.Row, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._order = order
        self._requesting_user = requesting_user
        self.paid_order: Optional[sqlite3.Row] = None

        self.setWindowTitle(ar.CUSTOMERS_CREDIT_SALE_DIALOG_TITLE)
        self._build_ui()
        self._reload_customers()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        total_label = QLabel("{0}: {1}".format(ar.PAYMENT_TOTAL_LABEL, format_egp(self._order["total_piasters"])))
        total_label.setProperty("role", "title")
        layout.addWidget(total_label)

        picker_row = QHBoxLayout()
        picker_row.addWidget(QLabel(ar.CUSTOMERS_SELECT_CUSTOMER_LABEL))
        self._customer_input = QComboBox()
        picker_row.addWidget(self._customer_input)
        layout.addLayout(picker_row)

        new_customer_row = QHBoxLayout()
        self._new_name_input = QLineEdit()
        self._new_name_input.setPlaceholderText(ar.CUSTOMERS_NAME_LABEL)
        new_customer_row.addWidget(self._new_name_input)
        self._new_phone_input = QLineEdit()
        self._new_phone_input.setPlaceholderText(ar.CUSTOMERS_PHONE_LABEL)
        new_customer_row.addWidget(self._new_phone_input)
        add_button = QPushButton(ar.CUSTOMERS_NEW_CUSTOMER_BUTTON)
        add_button.clicked.connect(self._on_add_customer)
        new_customer_row.addWidget(add_button)
        layout.addLayout(new_customer_row)

        confirm_button = QPushButton(ar.CUSTOMERS_CREDIT_SALE_DIALOG_TITLE)
        confirm_button.setProperty("variant", "primary")
        confirm_button.clicked.connect(self._on_confirm)
        layout.addWidget(confirm_button)

        self._error_label = QLabel("")
        self._error_label.setProperty("role", "error")
        self._error_label.setWordWrap(True)
        layout.addWidget(self._error_label)

    def _reload_customers(self) -> None:
        self._customer_input.clear()
        for customer in customers_repo.list_customers(self._conn, active_only=True):
            self._customer_input.addItem(customer["name"], customer["id"])

    def _on_add_customer(self) -> None:
        try:
            customer = customer_service.create_customer(
                self._conn, self._new_name_input.text(), self._new_phone_input.text().strip() or None, None, None,
                self._requesting_user,
            )
        except NameRequiredError:
            self._error_label.setText(ar.CUSTOMERS_ERROR_NAME_REQUIRED)
            return
        self._new_name_input.clear()
        self._new_phone_input.clear()
        self._reload_customers()
        index = self._customer_input.findData(customer["id"])
        if index >= 0:
            self._customer_input.setCurrentIndex(index)

    def _on_confirm(self) -> None:
        customer_id = self._customer_input.currentData()
        if customer_id is None:
            return
        self._attempt(approving_pin=None)

    def _attempt(self, approving_pin: Optional[str]) -> None:
        customer_id = self._customer_input.currentData()
        try:
            self.paid_order = customer_service.credit_sale(
                self._conn, self._order["id"], customer_id, self._requesting_user, approving_pin=approving_pin
            )
        except (WrongApprovalPinError, ApprovalLockedOutError) as error:
            if approving_pin is not None:
                self._error_label.setText(str(error))
                return
            pin = ask_for_owner_pin(self)
            if pin is None:
                return
            self._attempt(approving_pin=pin)
            return
        except CreditNotAllowedError:
            self._error_label.setText(ar.CUSTOMERS_CASHIER_NOT_ALLOWED)
            return
        except CustomerError as error:
            self._error_label.setText(str(error))
            return
        self.accept()
