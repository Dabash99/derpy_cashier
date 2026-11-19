"""On-screen invoice (no printer yet). print_invoice() is a clearly
marked hook: right now it just opens this dialog; a later phase will
replace its body with real printing without changing callers.
"""
from __future__ import annotations

import sqlite3

from PySide2.QtCore import Qt
from PySide2.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

from derby.core.db import orders_repo, ps_devices_repo, settings_repo, tables_repo, users_repo
from derby.core.i18n import ar
from derby.core.theme import icons
from derby.core.utils.money import format_egp
from derby.core.utils.time_utils import parse_utc_iso, to_cairo

_PAYMENT_METHOD_LABELS = {"cash": ar.PAYMENT_METHOD_CASH, "instapay": ar.PAYMENT_METHOD_INSTAPAY}


class InvoiceDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, order_id: int, is_copy: bool = True, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._order_id = order_id
        self._is_copy = is_copy
        self.setWindowTitle(ar.INVOICE_TITLE)
        self._build_ui()

    def _build_ui(self) -> None:
        order = orders_repo.get_order(self._conn, self._order_id)
        layout = QVBoxLayout(self)

        logo_label = QLabel()
        logo_label.setPixmap(icons.logo_pixmap("transparent", 110))
        logo_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo_label)

        cafe_name = settings_repo.get(self._conn, "cafe_name", "") or ""
        title = QLabel(cafe_name)
        title.setProperty("role", "title")
        layout.addWidget(title)

        if self._is_copy:
            copy_label = QLabel(ar.INVOICE_COPY_BADGE)
            layout.addWidget(copy_label)
        if order["status"] == "void":
            void_label = QLabel(ar.INVOICE_VOID_BADGE)
            void_label.setProperty("role", "error")
            layout.addWidget(void_label)

        layout.addWidget(QLabel("{0}: {1}".format(ar.INVOICE_NUMBER_LABEL, order["invoice_no"])))

        if order["paid_at_utc"]:
            cairo_time = to_cairo(parse_utc_iso(order["paid_at_utc"]))
            layout.addWidget(QLabel("{0}: {1}".format(ar.INVOICE_DATE_LABEL, cairo_time.strftime("%Y-%m-%d %H:%M"))))

        if order["table_id"]:
            table = tables_repo.get_table(self._conn, order["table_id"])
            table_name = table["name"] if table is not None else "-"
            layout.addWidget(QLabel("{0}: {1}".format(ar.INVOICE_TABLE_LABEL, table_name)))
        elif order["device_id"]:
            device = ps_devices_repo.get_device(self._conn, order["device_id"])
            device_name = device["name"] if device is not None else "-"
            layout.addWidget(QLabel("{0}: {1}".format(ar.INVOICE_DEVICE_LABEL, device_name)))
        else:
            layout.addWidget(QLabel(ar.INVOICE_TAKEAWAY_LABEL))

        for item in orders_repo.list_order_items(self._conn, order["id"]):
            line_text = "{0} × {1} — {2}".format(
                item["name_snapshot"], item["qty"], format_egp(item["line_total_piasters"])
            )
            layout.addWidget(QLabel(line_text))
            for addon in orders_repo.list_item_addons(self._conn, item["id"]):
                addon_text = "    + {0} ({1})".format(addon["name_snapshot"], format_egp(addon["price_delta_snapshot_piasters"]))
                layout.addWidget(QLabel(addon_text))
            if item["note"]:
                layout.addWidget(QLabel("    {0}".format(item["note"])))

        layout.addWidget(QLabel("{0}: {1}".format(ar.POS_SUBTOTAL_LABEL, format_egp(order["subtotal_piasters"]))))
        if order["discount_piasters"]:
            layout.addWidget(QLabel("{0}: {1}".format(ar.POS_DISCOUNT_LABEL, format_egp(order["discount_piasters"]))))
            if order["discount_reason"]:
                layout.addWidget(QLabel("{0}: {1}".format(ar.INVOICE_DISCOUNT_REASON_LABEL, order["discount_reason"])))
        total_label = QLabel("{0}: {1}".format(ar.POS_TOTAL_LABEL, format_egp(order["total_piasters"])))
        total_label.setProperty("role", "title")
        layout.addWidget(total_label)

        if order["payment_method"]:
            method_label = _PAYMENT_METHOD_LABELS.get(order["payment_method"], order["payment_method"])
            layout.addWidget(QLabel("{0}: {1}".format(ar.INVOICE_PAYMENT_METHOD_LABEL, method_label)))

        if order["paid_by"]:
            cashier = users_repo.get_user(self._conn, order["paid_by"])
            if cashier is not None:
                layout.addWidget(QLabel("{0}: {1}".format(ar.INVOICE_CASHIER_LABEL, cashier["name"])))

        close_button = QPushButton(ar.GENERIC_OK)
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)


def print_invoice(conn: sqlite3.Connection, order_id: int, is_copy: bool = True, parent=None) -> None:
    """Hook for a later printing phase -- for now it just opens the
    on-screen invoice dialog."""
    dialog = InvoiceDialog(conn, order_id, is_copy=is_copy, parent=parent)
    dialog.exec_()
