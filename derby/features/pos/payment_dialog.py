"""Payment dialog: pick cash or InstaPay. The "received -> change" helper
is UI-only arithmetic -- the spec is explicit that it is never stored.
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from PySide2.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from derby.core.i18n import ar
from derby.core.utils.money import format_egp
from derby.features.menu.price_parsing import parse_product_price
from derby.features.pos import orders_service


class PaymentDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, order: sqlite3.Row, requesting_user: sqlite3.Row, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._order = order
        self._requesting_user = requesting_user
        self.paid_order: Optional[sqlite3.Row] = None

        self.setWindowTitle(ar.PAYMENT_DIALOG_TITLE)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        total_label = QLabel("{0}: {1}".format(ar.PAYMENT_TOTAL_LABEL, format_egp(self._order["total_piasters"])))
        total_label.setProperty("role", "title")
        layout.addWidget(total_label)

        received_row = QHBoxLayout()
        received_row.addWidget(QLabel(ar.PAYMENT_RECEIVED_LABEL))
        self._received_input = QLineEdit()
        self._received_input.textChanged.connect(self._update_change)
        received_row.addWidget(self._received_input)
        layout.addLayout(received_row)

        self._change_label = QLabel("")
        layout.addWidget(self._change_label)

        buttons_row = QHBoxLayout()
        cash_button = QPushButton(ar.PAYMENT_CASH_BUTTON)
        cash_button.clicked.connect(lambda: self._on_pay("cash"))
        buttons_row.addWidget(cash_button)

        instapay_button = QPushButton(ar.PAYMENT_INSTAPAY_BUTTON)
        instapay_button.clicked.connect(lambda: self._on_pay("instapay"))
        buttons_row.addWidget(instapay_button)
        layout.addLayout(buttons_row)

        self._error_label = QLabel("")
        self._error_label.setProperty("role", "error")
        layout.addWidget(self._error_label)

    def _update_change(self) -> None:
        text = self._received_input.text().strip()
        if not text:
            self._change_label.setText("")
            return
        try:
            received_piasters = parse_product_price(text)
        except ValueError:
            self._change_label.setText("")
            return
        change = received_piasters - self._order["total_piasters"]
        self._change_label.setText("{0}: {1}".format(ar.PAYMENT_CHANGE_LABEL, format_egp(max(0, change))))

    def _on_pay(self, method: str) -> None:
        self.paid_order = orders_service.pay(self._conn, self._order["id"], method, self._requesting_user)
        self.accept()
