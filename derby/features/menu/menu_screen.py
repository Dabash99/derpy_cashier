"""The owner-only Menu screen: products (with categories + search) and
addon groups, in two tabs.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide2.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from derby.core.db import products_repo
from derby.core.i18n import ar
from derby.core.theme.tab_bar import configure_tab_widget
from derby.features.menu.addon_groups_panel import AddonGroupsPanel
from derby.features.menu.arabic_search import filter_products_by_search
from derby.features.menu.categories_panel import CategoriesPanel
from derby.features.menu.csv_export import export_menu_csv
from derby.features.menu.import_dialog import ImportDialog
from derby.features.menu.product_dialog import ProductDialog
from derby.features.menu.products_table import ProductsTable


class MenuScreen(QWidget):
    def __init__(self, conn: sqlite3.Connection, user_id: int, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user_id = user_id
        self._selected_category_id = None
        self._build_ui()
        self._reload_products()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel(ar.MENU_TITLE)
        title.setProperty("role", "title")
        layout.addWidget(title)

        tabs = QTabWidget()
        configure_tab_widget(tabs)
        tabs.addTab(self._build_products_tab(), ar.MENU_TAB_PRODUCTS)
        self._addon_groups_panel = AddonGroupsPanel(self._conn)
        tabs.addTab(self._addon_groups_panel, ar.MENU_TAB_ADDONS)
        layout.addWidget(tabs)

    def _build_products_tab(self) -> QWidget:
        tab = QWidget()
        outer = QVBoxLayout(tab)

        toolbar = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(ar.MENU_SEARCH_PLACEHOLDER)
        self._search_input.textChanged.connect(self._reload_products)
        toolbar.addWidget(self._search_input)

        self._show_inactive_checkbox = QCheckBox(ar.MENU_SHOW_INACTIVE_CHECKBOX)
        self._show_inactive_checkbox.toggled.connect(self._reload_products)
        toolbar.addWidget(self._show_inactive_checkbox)

        add_product_button = QPushButton(ar.MENU_PRODUCT_ADD_BUTTON)
        add_product_button.clicked.connect(self._on_add_product)
        toolbar.addWidget(add_product_button)

        import_button = QPushButton(ar.MENU_CSV_IMPORT_BUTTON)
        import_button.clicked.connect(self._on_import_csv)
        toolbar.addWidget(import_button)

        export_button = QPushButton(ar.MENU_CSV_EXPORT_BUTTON)
        export_button.clicked.connect(self._on_export_csv)
        toolbar.addWidget(export_button)

        outer.addLayout(toolbar)

        body = QHBoxLayout()
        self._products_table = ProductsTable()
        self._products_table.edit_requested.connect(self._on_edit_product)
        self._products_table.toggle_active_requested.connect(self._on_toggle_product_active)
        self._products_table.confirm_price_requested.connect(self._on_confirm_price)
        body.addWidget(self._products_table, 2)

        self._categories_panel = CategoriesPanel(self._conn)
        self._categories_panel.selection_changed.connect(self._on_category_selected)
        self._categories_panel.categories_changed.connect(self._reload_products)
        body.addWidget(self._categories_panel, 1)

        outer.addLayout(body)
        return tab

    def _on_category_selected(self, category_id) -> None:
        self._selected_category_id = category_id
        self._reload_products()

    def _reload_products(self) -> None:
        active_only = not self._show_inactive_checkbox.isChecked()
        products = products_repo.list_products(self._conn, self._selected_category_id, active_only)
        filtered = filter_products_by_search(products, self._search_input.text())
        self._products_table.set_products(filtered)

    def _on_add_product(self) -> None:
        dialog = ProductDialog(
            self._conn, self._user_id, default_category_id=self._selected_category_id, parent=self
        )
        if dialog.exec_() == QDialog.Accepted:
            self._reload_products()

    def _on_edit_product(self, product_id: int) -> None:
        dialog = ProductDialog(self._conn, self._user_id, product_id=product_id, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self._reload_products()

    def _on_toggle_product_active(self, product_id: int) -> None:
        product = products_repo.get_product(self._conn, product_id)
        products_repo.set_active(self._conn, product_id, not product["is_active"])
        self._reload_products()

    def _on_confirm_price(self, product_id: int) -> None:
        products_repo.confirm_price(self._conn, product_id)
        self._reload_products()

    def _on_import_csv(self) -> None:
        dialog = ImportDialog(self._conn, self._user_id, parent=self)
        dialog.exec_()
        self._categories_panel.reload()
        self._reload_products()

    def _on_export_csv(self) -> None:
        file_path, _filter = QFileDialog.getSaveFileName(self, ar.MENU_CSV_EXPORT_BUTTON, "menu.csv", "CSV (*.csv)")
        if not file_path:
            return
        export_menu_csv(self._conn, Path(file_path))
        QMessageBox.information(self, ar.GENERIC_SUCCESS_TITLE, ar.MENU_CSV_EXPORT_SUCCESS.format(path=file_path))
