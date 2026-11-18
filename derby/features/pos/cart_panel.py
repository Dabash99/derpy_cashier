"""Left-hand side of the cashier screen: the cart. Rebuilt from the DB on
every reload() (same simple pattern as the rest of the app) since a
cashier's cart realistically has a handful of lines, not hundreds.
"""
from __future__ import annotations

import sqlite3

from PySide2.QtCore import Signal
from PySide2.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from derby.core.db import orders_repo
from derby.core.i18n import ar
from derby.core.utils.money import format_egp
from derby.features.pos import orders_service
from derby.features.pos.exceptions import QuantityOutOfRangeError


class CartPanel(QWidget):
    pay_requested = Signal()
    discount_requested = Signal()
    cancel_requested = Signal()
    changed = Signal()  # fires after any successful cart mutation

    def __init__(self, conn: sqlite3.Connection, order_id: int, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._order_id = order_id
        self._build_ui()
        self.reload()

    def set_order(self, order_id: int) -> None:
        self._order_id = order_id
        self.reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        title = QLabel(ar.POS_CART_TITLE)
        title.setProperty("role", "title")
        layout.addWidget(title)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        self._lines_host = QWidget()
        self._lines_layout = QVBoxLayout(self._lines_host)
        scroll_area.setWidget(self._lines_host)
        layout.addWidget(scroll_area)

        self._subtotal_label = QLabel("")
        layout.addWidget(self._subtotal_label)
        self._discount_label = QLabel("")
        layout.addWidget(self._discount_label)
        self._total_label = QLabel("")
        self._total_label.setProperty("role", "title")
        layout.addWidget(self._total_label)

        buttons_row = QHBoxLayout()
        discount_button = QPushButton(ar.POS_DISCOUNT_BUTTON)
        discount_button.clicked.connect(self.discount_requested.emit)
        buttons_row.addWidget(discount_button)

        pay_button = QPushButton(ar.POS_PAY_BUTTON)
        pay_button.clicked.connect(self.pay_requested.emit)
        buttons_row.addWidget(pay_button)

        cancel_button = QPushButton(ar.POS_CANCEL_ORDER_BUTTON)
        cancel_button.setProperty("danger", "true")
        cancel_button.clicked.connect(self.cancel_requested.emit)
        buttons_row.addWidget(cancel_button)
        layout.addLayout(buttons_row)

    def reload(self) -> None:
        while self._lines_layout.count():
            item = self._lines_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        order = orders_repo.get_order(self._conn, self._order_id)
        if order is None:
            # No order chosen yet (e.g. the chooser page hasn't handed off
            # to a table/takeaway order) -- show an empty cart, not a crash.
            self._lines_layout.addWidget(QLabel(ar.POS_EMPTY_CART))
            self._lines_layout.addStretch(1)
            self._subtotal_label.setText("")
            self._discount_label.setText("")
            self._total_label.setText("")
            return

        items = orders_repo.list_order_items(self._conn, self._order_id)
        if not items:
            self._lines_layout.addWidget(QLabel(ar.POS_EMPTY_CART))
        for item in items:
            self._lines_layout.addWidget(self._build_line_widget(item))
        self._lines_layout.addStretch(1)

        self._subtotal_label.setText("{0}: {1}".format(ar.POS_SUBTOTAL_LABEL, format_egp(order["subtotal_piasters"])))
        self._discount_label.setText("{0}: {1}".format(ar.POS_DISCOUNT_LABEL, format_egp(order["discount_piasters"])))
        self._total_label.setText("{0}: {1}".format(ar.POS_TOTAL_LABEL, format_egp(order["total_piasters"])))

    def _build_line_widget(self, item: sqlite3.Row) -> QWidget:
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        outer = QVBoxLayout(frame)

        row = QHBoxLayout()
        name_label = QLabel("{0} — {1}".format(item["name_snapshot"], format_egp(item["line_total_piasters"])))
        row.addWidget(name_label)

        minus_button = QPushButton("−")
        minus_button.setFixedWidth(36)
        minus_button.clicked.connect(lambda: self._on_change_qty(item["id"], item["qty"] - 1))
        row.addWidget(minus_button)

        qty_label = QLabel(str(item["qty"]))
        row.addWidget(qty_label)

        plus_button = QPushButton("+")
        plus_button.setFixedWidth(36)
        plus_button.clicked.connect(lambda: self._on_change_qty(item["id"], item["qty"] + 1))
        row.addWidget(plus_button)

        note_button = QPushButton(ar.POS_NOTE_BUTTON)
        note_button.clicked.connect(lambda: self._on_edit_note(item["id"], item["note"] or ""))
        row.addWidget(note_button)

        remove_button = QPushButton(ar.POS_REMOVE_ITEM_BUTTON)
        remove_button.clicked.connect(lambda: self._on_remove_item(item["id"]))
        row.addWidget(remove_button)

        outer.addLayout(row)

        for addon in orders_repo.list_item_addons(self._conn, item["id"]):
            outer.addWidget(QLabel("+ {0}".format(addon["name_snapshot"])))
        if item["note"]:
            outer.addWidget(QLabel(item["note"]))

        return frame

    def _on_change_qty(self, item_id: int, new_qty: int) -> None:
        if new_qty < 1:
            self._on_remove_item(item_id)
            return
        try:
            orders_service.change_qty(self._conn, self._order_id, item_id, new_qty)
        except QuantityOutOfRangeError:
            return
        self.reload()
        self.changed.emit()

    def _on_remove_item(self, item_id: int) -> None:
        orders_service.remove_item(self._conn, self._order_id, item_id)
        self.reload()
        self.changed.emit()

    def _on_edit_note(self, item_id: int, current_note: str) -> None:
        text, confirmed = QInputDialog.getText(
            self, ar.POS_NOTE_DIALOG_TITLE, ar.POS_NOTE_DIALOG_TITLE, QLineEdit.Normal, current_note
        )
        if not confirmed:
            return
        orders_service.set_item_note(self._conn, self._order_id, item_id, text)
        self.reload()
        self.changed.emit()
