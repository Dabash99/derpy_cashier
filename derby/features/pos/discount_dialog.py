"""Discount dialog: owner applies directly, a cashier must enter an
owner's PIN (verified through orders_service, which reuses the existing
global login lockout for wrong attempts).
"""
from __future__ import annotations

import sqlite3

from PySide2.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from derby.core.db import users_repo
from derby.core.i18n import ar
from derby.features.menu.price_parsing import parse_product_price
from derby.features.pos import orders_service
from derby.features.pos.discount_math import DISCOUNT_KIND_FIXED, DISCOUNT_KIND_PERCENT
from derby.features.pos.exceptions import (
    ApprovalLockedOutError,
    DiscountExceedsSubtotalError,
    DiscountReasonRequiredError,
    WrongApprovalPinError,
)


class DiscountDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, order_id: int, requesting_user: sqlite3.Row, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._order_id = order_id
        self._requesting_user = requesting_user
        self.setWindowTitle(ar.DISCOUNT_DIALOG_TITLE)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self._kind_input = QComboBox()
        self._kind_input.addItem(ar.DISCOUNT_KIND_FIXED_LABEL, DISCOUNT_KIND_FIXED)
        self._kind_input.addItem(ar.DISCOUNT_KIND_PERCENT_LABEL, DISCOUNT_KIND_PERCENT)
        form.addRow(self._kind_input)

        self._amount_input = QLineEdit()
        form.addRow(ar.DISCOUNT_AMOUNT_LABEL, self._amount_input)

        self._reason_input = QLineEdit()
        form.addRow(ar.DISCOUNT_REASON_LABEL, self._reason_input)

        self._pin_input = QLineEdit()
        self._pin_input.setEchoMode(QLineEdit.Password)
        if self._requesting_user["role"] != users_repo.ROLE_OWNER:
            form.addRow(ar.DISCOUNT_OWNER_PIN_LABEL, self._pin_input)

        self._error_label = QLabel("")
        self._error_label.setProperty("role", "error")
        self._error_label.setWordWrap(True)
        layout.addWidget(self._error_label)

        apply_button = QPushButton(ar.DISCOUNT_APPLY_BUTTON)
        apply_button.clicked.connect(self._on_apply)
        layout.addWidget(apply_button)

        remove_button = QPushButton(ar.POS_REMOVE_DISCOUNT_BUTTON)
        remove_button.clicked.connect(self._on_remove)
        layout.addWidget(remove_button)

    def _on_apply(self) -> None:
        kind = self._kind_input.currentData()
        try:
            if kind == DISCOUNT_KIND_PERCENT:
                amount = int(self._amount_input.text().strip())
            else:
                amount = parse_product_price(self._amount_input.text())
        except ValueError:
            self._error_label.setText(ar.MENU_PRODUCT_ERROR_PRICE_INVALID)
            return

        try:
            orders_service.apply_discount(
                self._conn,
                self._order_id,
                kind,
                amount,
                self._reason_input.text(),
                self._requesting_user,
                approving_pin=self._pin_input.text(),
            )
        except DiscountReasonRequiredError:
            self._error_label.setText(ar.DISCOUNT_ERROR_REASON_REQUIRED)
            return
        except DiscountExceedsSubtotalError:
            self._error_label.setText(ar.DISCOUNT_ERROR_EXCEEDS_SUBTOTAL)
            return
        except WrongApprovalPinError:
            self._error_label.setText(ar.DISCOUNT_ERROR_WRONG_PIN)
            return
        except ApprovalLockedOutError:
            self._error_label.setText(ar.LOGIN_ERROR_LOCKED.format(minutes=0, seconds=0))
            return
        self.accept()

    def _on_remove(self) -> None:
        try:
            orders_service.remove_discount(
                self._conn, self._order_id, self._requesting_user, approving_pin=self._pin_input.text()
            )
        except WrongApprovalPinError:
            self._error_label.setText(ar.DISCOUNT_ERROR_WRONG_PIN)
            return
        except ApprovalLockedOutError:
            self._error_label.setText(ar.LOGIN_ERROR_LOCKED.format(minutes=0, seconds=0))
            return
        self.accept()
