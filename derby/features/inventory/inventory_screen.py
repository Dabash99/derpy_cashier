"""المخزون (Inventory): stock items, purchases, and suppliers in one
owner-only screen with three tabs -- a small, light footprint rather
than three separate sidebar sections.
"""
from __future__ import annotations

import sqlite3

from PySide2.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from derby.core.db import purchases_repo, stock_items_repo, suppliers_repo
from derby.core.i18n import ar
from derby.core.theme.tab_bar import configure_tab_widget
from derby.core.theme.table_style import centered_item, configure_table, fit_table_height, right_item
from derby.core.utils.money import format_egp
from derby.core.utils.time_utils import utc_now
from derby.features.inventory import stock_service
from derby.features.inventory.inventory_dialogs import (
    PurchaseDialog,
    StockItemDialog,
    StocktakeDialog,
    SupplierDialog,
    WasteDialog,
)
from derby.features.inventory.reorder_list_dialog import ReorderListDialog
from derby.features.reports.export_panel import ExportPanel
from derby.features.reports.export_service import (
    export_purchases_csv,
    export_purchases_xlsx,
    export_stock_csv,
    export_stock_xlsx,
)


class InventoryScreen(QWidget):
    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        title = QLabel(ar.INVENTORY_TITLE)
        title.setProperty("role", "title")
        outer.addWidget(title)

        self._tabs = QTabWidget()
        configure_tab_widget(self._tabs)
        outer.addWidget(self._tabs)

        self._build_stock_tab()
        self._build_purchases_tab()
        self._build_suppliers_tab()

    # --- stock tab -----------------------------------------------------

    def _build_stock_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        top_row = QHBoxLayout()
        add_button = QPushButton(ar.INVENTORY_ADD_ITEM_BUTTON)
        add_button.setProperty("variant", "primary")
        add_button.clicked.connect(self._on_add_item)
        top_row.addWidget(add_button)
        reorder_button = QPushButton(ar.REORDER_LIST_TITLE)
        reorder_button.clicked.connect(self._on_open_reorder_list)
        top_row.addWidget(reorder_button)
        top_row.addStretch(1)
        layout.addLayout(top_row)

        self._stock_table = QTableWidget(0, 7)
        self._stock_table.setHorizontalHeaderLabels(
            [
                ar.INVENTORY_COLUMN_NAME, ar.INVENTORY_COLUMN_QTY, ar.INVENTORY_COLUMN_MIN_QTY,
                ar.INVENTORY_COLUMN_AVG_COST, ar.INVENTORY_COLUMN_VALUE, ar.INVENTORY_COLUMN_STATUS, "",
            ]
        )
        configure_table(self._stock_table, stretch_columns=(0,), fixed_widths={6: 400})
        # Four action buttons share this row; QPushButton's natural height
        # (padding + Cairo font metrics) exceeds the app-wide row height,
        # which silently clips the tops/bottoms of their Arabic glyphs --
        # taller rows just for this table, not a global token change.
        self._stock_table.verticalHeader().setDefaultSectionSize(64)
        self._stock_table.verticalHeader().setMinimumSectionSize(64)
        layout.addWidget(self._stock_table)

        self._stock_export_panel = ExportPanel(lambda: "المخزون_{0}".format(utc_now().strftime("%Y%m%d")))
        self._stock_export_panel.set_exporters(
            csv_fn=lambda path: export_stock_csv(stock_items_repo.list_stock_items(self._conn), path),
            xlsx_fn=lambda path: export_stock_xlsx(stock_items_repo.list_stock_items(self._conn), path),
        )
        layout.addWidget(self._stock_export_panel)

        self._tabs.addTab(tab, ar.INVENTORY_TAB_STOCK)

    def _reload_stock_tab(self) -> None:
        items = stock_items_repo.list_stock_items(self._conn)
        self._stock_table.setRowCount(len(items))
        for row_index, item in enumerate(items):
            value = int(round(item["current_qty"] * item["avg_cost_piasters"]))
            if item["current_qty"] < 0:
                status = ar.INVENTORY_STATUS_NEGATIVE
            elif item["current_qty"] <= item["min_qty"]:
                status = ar.INVENTORY_STATUS_LOW
            else:
                status = ar.INVENTORY_STATUS_OK
            self._stock_table.setItem(row_index, 0, right_item(item["name"]))
            self._stock_table.setItem(row_index, 1, centered_item("{0:g} {1}".format(item["current_qty"], item["unit"])))
            self._stock_table.setItem(row_index, 2, centered_item("{0:g}".format(item["min_qty"])))
            self._stock_table.setItem(row_index, 3, centered_item(format_egp(int(round(item["avg_cost_piasters"])))))
            self._stock_table.setItem(row_index, 4, centered_item(format_egp(value)))
            self._stock_table.setItem(row_index, 5, centered_item(status))

            actions = QWidget()
            actions_layout = QHBoxLayout(actions)
            actions_layout.setContentsMargins(0, 0, 0, 0)
            actions_layout.setSpacing(4)
            edit_button = QPushButton(ar.INVENTORY_EDIT_BUTTON)
            edit_button.clicked.connect(lambda _c=False, i=item: self._on_edit_item(i))
            actions_layout.addWidget(edit_button)
            purchase_button = QPushButton(ar.INVENTORY_PURCHASE_BUTTON)
            purchase_button.clicked.connect(lambda _c=False: self._on_add_purchase())
            actions_layout.addWidget(purchase_button)
            waste_button = QPushButton(ar.INVENTORY_WASTE_BUTTON)
            waste_button.clicked.connect(lambda _c=False, i=item: self._on_waste(i))
            actions_layout.addWidget(waste_button)
            stocktake_button = QPushButton(ar.INVENTORY_STOCKTAKE_BUTTON)
            stocktake_button.clicked.connect(lambda _c=False, i=item: self._on_stocktake(i))
            actions_layout.addWidget(stocktake_button)
            self._stock_table.setCellWidget(row_index, 6, actions)

        fit_table_height(self._stock_table, max_rows=15)

    def _on_add_item(self) -> None:
        dialog = StockItemDialog(self._conn, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self.reload()

    def _on_open_reorder_list(self) -> None:
        ReorderListDialog(self._conn, parent=self).exec_()

    def _on_edit_item(self, item: sqlite3.Row) -> None:
        dialog = StockItemDialog(self._conn, item, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self.reload()

    def _on_waste(self, item: sqlite3.Row) -> None:
        dialog = WasteDialog(self._conn, item, self._user, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self.reload()

    def _on_stocktake(self, item: sqlite3.Row) -> None:
        dialog = StocktakeDialog(self._conn, item, self._user, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self.reload()

    # --- purchases tab ----------------------------------------------------

    def _build_purchases_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        add_button = QPushButton(ar.INVENTORY_PURCHASE_DIALOG_TITLE)
        add_button.setProperty("variant", "primary")
        add_button.clicked.connect(self._on_add_purchase)
        layout.addWidget(add_button)

        layout.addWidget(QLabel(ar.INVENTORY_PURCHASE_HISTORY_TITLE))
        self._purchases_table = QTableWidget(0, 5)
        self._purchases_table.setHorizontalHeaderLabels(
            [
                ar.INVENTORY_PURCHASE_COLUMN_DATE, ar.INVENTORY_PURCHASE_COLUMN_SUPPLIER,
                ar.INVENTORY_PURCHASE_COLUMN_TOTAL, ar.INVENTORY_PURCHASE_COLUMN_STATUS, "",
            ]
        )
        configure_table(self._purchases_table, stretch_columns=(1,), fixed_widths={4: 160})
        layout.addWidget(self._purchases_table)

        self._purchases_export_panel = ExportPanel(lambda: "المشتريات_{0}".format(utc_now().strftime("%Y%m%d")))
        self._purchases_export_panel.set_exporters(
            csv_fn=lambda path: export_purchases_csv(purchases_repo.list_purchases(self._conn), self._supplier_name_by_id(), path),
            xlsx_fn=lambda path: export_purchases_xlsx(purchases_repo.list_purchases(self._conn), self._supplier_name_by_id(), path),
        )
        layout.addWidget(self._purchases_export_panel)

        self._tabs.addTab(tab, ar.INVENTORY_TAB_PURCHASES)

    def _reload_purchases_tab(self) -> None:
        purchases = list(reversed(purchases_repo.list_purchases(self._conn)))
        self._purchases_table.setRowCount(len(purchases))
        for row_index, purchase in enumerate(purchases):
            supplier = suppliers_repo.get_supplier(self._conn, purchase["supplier_id"]) if purchase["supplier_id"] else None
            status = ar.INVENTORY_PURCHASE_STATUS_PAID if purchase["is_paid"] else ar.INVENTORY_PURCHASE_STATUS_UNPAID
            self._purchases_table.setItem(row_index, 0, centered_item(purchase["purchase_date"]))
            self._purchases_table.setItem(row_index, 1, right_item(supplier["name"] if supplier else "—"))
            self._purchases_table.setItem(row_index, 2, centered_item(format_egp(purchase["total_cost_piasters"])))
            self._purchases_table.setItem(row_index, 3, centered_item(status))
            if not purchase["is_paid"]:
                mark_paid_button = QPushButton(ar.INVENTORY_PURCHASE_MARK_PAID_BUTTON)
                mark_paid_button.clicked.connect(lambda _c=False, p=purchase: self._on_mark_paid(p))
                self._purchases_table.setCellWidget(row_index, 4, mark_paid_button)
            else:
                self._purchases_table.setCellWidget(row_index, 4, QWidget())
        fit_table_height(self._purchases_table, max_rows=15)

    def _on_add_purchase(self) -> None:
        dialog = PurchaseDialog(self._conn, self._user, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self.reload()

    def _on_mark_paid(self, purchase: sqlite3.Row) -> None:
        stock_service.mark_purchase_paid(self._conn, purchase["id"], self._user["id"])
        self.reload()

    # --- suppliers tab ----------------------------------------------------

    def _build_suppliers_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        add_button = QPushButton(ar.INVENTORY_SUPPLIER_ADD_BUTTON)
        add_button.setProperty("variant", "primary")
        add_button.clicked.connect(self._on_add_supplier)
        layout.addWidget(add_button)

        self._suppliers_table = QTableWidget(0, 4)
        self._suppliers_table.setHorizontalHeaderLabels(
            [ar.INVENTORY_SUPPLIER_COLUMN_NAME, ar.INVENTORY_SUPPLIER_COLUMN_PHONE, ar.INVENTORY_SUPPLIER_COLUMN_OWED, ""]
        )
        configure_table(self._suppliers_table, stretch_columns=(0,), fixed_widths={3: 120})
        layout.addWidget(self._suppliers_table)

        self._tabs.addTab(tab, ar.INVENTORY_TAB_SUPPLIERS)

    def _reload_suppliers_tab(self) -> None:
        suppliers = suppliers_repo.list_suppliers(self._conn)
        self._suppliers_table.setRowCount(len(suppliers))
        for row_index, supplier in enumerate(suppliers):
            owed = suppliers_repo.amount_owed_piasters(self._conn, supplier["id"])
            self._suppliers_table.setItem(row_index, 0, right_item(supplier["name"]))
            self._suppliers_table.setItem(row_index, 1, centered_item(supplier["phone"] or "—"))
            self._suppliers_table.setItem(row_index, 2, centered_item(format_egp(owed)))
            edit_button = QPushButton(ar.INVENTORY_SUPPLIER_EDIT_BUTTON)
            edit_button.clicked.connect(lambda _c=False, s=supplier: self._on_edit_supplier(s))
            self._suppliers_table.setCellWidget(row_index, 3, edit_button)
        fit_table_height(self._suppliers_table, max_rows=15)

    def _on_add_supplier(self) -> None:
        dialog = SupplierDialog(self._conn, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self.reload()

    def _on_edit_supplier(self, supplier: sqlite3.Row) -> None:
        dialog = SupplierDialog(self._conn, supplier, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self.reload()

    def _supplier_name_by_id(self):
        return {supplier["id"]: supplier["name"] for supplier in suppliers_repo.list_suppliers(self._conn)}

    # --- shared ----------------------------------------------------------

    def reload(self) -> None:
        self._reload_stock_tab()
        self._reload_purchases_tab()
        self._reload_suppliers_tab()
