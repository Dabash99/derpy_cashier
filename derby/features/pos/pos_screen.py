"""The Cashier screen: choose a table/takeaway to start, then the usual
product-grid + cart layout. Also reachable with a specific order already
chosen (open_order), which is how the Tables screen hands off to it.
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from PySide2.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from derby.core.db import addons_repo, orders_repo, products_repo, ps_devices_repo, tables_repo, users_repo
from derby.core.i18n import ar
from derby.features.pos import orders_service
from derby.features.pos.addon_dialog import AddonDialog
from derby.features.pos.cart_panel import CartPanel
from derby.features.pos.discount_dialog import DiscountDialog
from derby.features.pos.exceptions import ApprovalLockedOutError, WrongApprovalPinError
from derby.features.pos.invoice_dialog import print_invoice
from derby.features.pos.owner_pin_prompt import ask_for_owner_pin
from derby.features.pos.payment_dialog import PaymentDialog
from derby.features.pos.product_grid import ProductGrid


class PosScreen(QWidget):
    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._current_order_id = None
        # Set while the working page shows a table/takeaway that has no
        # order row yet -- see _materialize_pending_order().
        self._pending_table_id = None
        self._pending_is_takeaway = False

        self._stack = QStackedWidget()
        outer = QVBoxLayout(self)
        outer.addWidget(self._stack)

        self._chooser_page = self._build_chooser_page()
        self._stack.addWidget(self._chooser_page)

        self._working_page, self._order_label, self._product_grid, self._cart_panel = self._build_working_page()
        self._stack.addWidget(self._working_page)

        self._refresh_chooser()

    # --- chooser (no order selected yet) ------------------------------------

    def _build_chooser_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel(ar.POS_TITLE))

        self._chooser_grid = QGridLayout()
        layout.addLayout(self._chooser_grid)

        takeaway_button = QPushButton(ar.POS_TAKEAWAY_BUTTON)
        takeaway_button.clicked.connect(self._on_start_takeaway)
        layout.addWidget(takeaway_button)

        layout.addStretch(1)
        return page

    def _refresh_chooser(self) -> None:
        while self._chooser_grid.count():
            item = self._chooser_grid.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

        free_tables = [
            table
            for table in tables_repo.list_tables(self._conn, active_only=True)
            if orders_repo.get_open_order_for_table(self._conn, table["id"]) is None
        ]
        for index, table in enumerate(free_tables):
            row, col = divmod(index, 4)
            button = QPushButton(table["name"])
            button.setMinimumSize(120, 80)
            button.clicked.connect(lambda _checked=False, tid=table["id"]: self._on_start_table(tid))
            self._chooser_grid.addWidget(button, row, col)

    def open_table(self, table_id: int) -> None:
        """Entry point for both the chooser grid above and the Tables
        screen's card click: an existing order is opened as-is, but a free
        table opens a PENDING working page with no order row at all --
        one is only created once the first item/session makes it real."""
        order = orders_repo.get_open_order_for_table(self._conn, table_id)
        if order is not None:
            self.open_order(order["id"])
            return
        table = tables_repo.get_table(self._conn, table_id)
        self._current_order_id = None
        self._pending_table_id = table_id
        self._pending_is_takeaway = False
        self._order_label.setText(table["name"] if table is not None else "")
        self._cart_panel.set_order(None)
        self._stack.setCurrentWidget(self._working_page)

    def _on_start_table(self, table_id: int) -> None:
        self.open_table(table_id)

    def _on_start_takeaway(self) -> None:
        self._current_order_id = None
        self._pending_table_id = None
        self._pending_is_takeaway = True
        self._order_label.setText(ar.TABLES_TAKEAWAY_SECTION)
        self._cart_panel.set_order(None)
        self._stack.setCurrentWidget(self._working_page)

    def _materialize_pending_order(self) -> Optional[int]:
        """Called the moment an order actually needs to exist (first item
        added). Returns None if there is nothing pending AND no current
        order either (shouldn't normally happen from the UI)."""
        if self._current_order_id is not None:
            return self._current_order_id
        if self._pending_is_takeaway:
            order = orders_service.create_takeaway_order(self._conn, self._user["id"])
        elif self._pending_table_id is not None:
            order = orders_service.get_or_create_table_order(self._conn, self._pending_table_id, self._user["id"])
        else:
            return None
        self._current_order_id = order["id"]
        self._pending_table_id = None
        self._pending_is_takeaway = False
        self._cart_panel.set_order(self._current_order_id)
        return self._current_order_id

    # --- working page (an order is open) --------------------------------------

    def _build_working_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)

        # Order matters under RTL: Qt mirrors a QHBoxLayout so the widget
        # added first lands at the right/start edge. "دفع" (primary) is
        # added first so it sits closest to the start side, "رجوع" last
        # (least prominent, a plain exit action).
        header = QHBoxLayout()
        order_label = QLabel("")
        order_label.setProperty("role", "title")
        header.addWidget(order_label)
        header.addStretch(1)

        self._pay_button = QPushButton(ar.POS_PAY_BUTTON)
        self._pay_button.setProperty("variant", "primary")
        self._pay_button.clicked.connect(self._on_pay_requested)
        header.addWidget(self._pay_button)

        cancel_button = QPushButton(ar.POS_CANCEL_ORDER_BUTTON)
        cancel_button.setProperty("danger", "true")
        cancel_button.clicked.connect(self._on_cancel_requested)
        header.addWidget(cancel_button)

        back_button = QPushButton(ar.POS_BACK_TO_TABLES_BUTTON)
        back_button.clicked.connect(self._on_back_to_chooser)
        header.addWidget(back_button)
        outer.addLayout(header)

        body = QHBoxLayout()
        product_grid = ProductGrid(self._conn)
        product_grid.product_clicked.connect(self._on_product_clicked)
        body.addWidget(product_grid, 2)

        cart_panel = CartPanel(self._conn, order_id=0, user=self._user)
        cart_panel.discount_requested.connect(self._on_discount_requested)
        cart_panel.pay_allowed_changed.connect(self._pay_button.setEnabled)
        body.addWidget(cart_panel, 1)

        outer.addLayout(body)
        return page, order_label, product_grid, cart_panel

    def open_order(self, order_id: int) -> None:
        self._current_order_id = order_id
        self._pending_table_id = None
        self._pending_is_takeaway = False
        order = orders_repo.get_order(self._conn, order_id)
        if order["table_id"]:
            table = tables_repo.get_table(self._conn, order["table_id"])
            self._order_label.setText(table["name"] if table is not None else "")
        elif order["device_id"]:
            device = ps_devices_repo.get_device(self._conn, order["device_id"])
            self._order_label.setText(device["name"] if device is not None else "")
        else:
            self._order_label.setText(ar.TABLES_TAKEAWAY_SECTION)
        self._cart_panel.set_order(order_id)
        self._stack.setCurrentWidget(self._working_page)

    def leave_screen(self) -> None:
        """Called by MainWindow whenever navigation moves away from the
        Cashier screen -- cleans up a pending (never materialized)
        selection and sweeps any order that ended up open with no items."""
        self._current_order_id = None
        self._pending_table_id = None
        self._pending_is_takeaway = False
        orders_service.auto_cancel_empty_open_orders(self._conn, self._user["id"])

    def _on_back_to_chooser(self) -> None:
        self.leave_screen()
        self._refresh_chooser()
        self._stack.setCurrentWidget(self._chooser_page)

    def _on_product_clicked(self, product_id: int) -> None:
        group_ids = addons_repo.get_product_group_ids(self._conn, product_id)
        active_groups = [gid for gid in group_ids if addons_repo.get_group(self._conn, gid)["is_active"]]

        addon_ids = []
        if active_groups:
            product = products_repo.get_product(self._conn, product_id)
            dialog = AddonDialog(self._conn, product_id, product["name_ar"], parent=self)
            if dialog.exec_() != QDialog.Accepted:
                return
            addon_ids = dialog.selected_addon_ids()

        order_id = self._materialize_pending_order()
        orders_service.add_item(self._conn, order_id, product_id, 1, addon_ids, None, self._user["id"])
        self._cart_panel.reload()

    def _on_pay_requested(self) -> None:
        if self._current_order_id is None:
            # Nothing was ever added -- same "empty cart" outcome as a
            # materialized order with a zero subtotal.
            QMessageBox.warning(self, ar.GENERIC_ERROR_TITLE, ar.POS_ERROR_EMPTY_CART_PAY)
            return
        order = orders_repo.get_order(self._conn, self._current_order_id)
        if order["subtotal_piasters"] <= 0:
            QMessageBox.warning(self, ar.GENERIC_ERROR_TITLE, ar.POS_ERROR_EMPTY_CART_PAY)
            return
        dialog = PaymentDialog(self._conn, order, self._user, parent=self)
        if dialog.exec_() == QDialog.Accepted and dialog.paid_order is not None:
            print_invoice(self._conn, dialog.paid_order["id"], is_copy=False, parent=self)
            self._on_back_to_chooser()

    def _on_discount_requested(self) -> None:
        if self._current_order_id is None:
            QMessageBox.information(self, ar.POS_CART_TITLE, ar.POS_EMPTY_CART)
            return
        dialog = DiscountDialog(self._conn, self._current_order_id, self._user, parent=self)
        dialog.exec_()
        self._cart_panel.reload()

    def _on_cancel_requested(self) -> None:
        if self._current_order_id is None:
            # Nothing was ever materialized -- just leave, there is
            # nothing in the database to cancel or approve.
            self._on_back_to_chooser()
            return
        confirmed = QMessageBox.question(self, ar.POS_CANCEL_CONFIRM_TITLE, ar.POS_CANCEL_CONFIRM_MESSAGE)
        if confirmed != QMessageBox.Yes:
            return

        has_items = len(orders_repo.list_order_items(self._conn, self._current_order_id)) > 0
        approving_pin = None
        if has_items and self._user["role"] != users_repo.ROLE_OWNER:
            approving_pin = ask_for_owner_pin(self)
            if approving_pin is None:
                return

        try:
            orders_service.cancel(self._conn, self._current_order_id, self._user, approving_pin=approving_pin)
        except WrongApprovalPinError:
            QMessageBox.warning(self, ar.GENERIC_ERROR_TITLE, ar.DISCOUNT_ERROR_WRONG_PIN)
            return
        except ApprovalLockedOutError:
            QMessageBox.warning(self, ar.GENERIC_ERROR_TITLE, ar.LOGIN_ERROR_LOCKED.format(minutes=0, seconds=0))
            return
        self._on_back_to_chooser()
