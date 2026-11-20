"""Right-hand side of the cashier screen: category chips + a searchable
grid of product cards. Reuses Phase 2's thumbnail cache and Arabic search.
"""
from __future__ import annotations

import sqlite3

from PySide2.QtCore import QSize, Signal
from PySide2.QtGui import QIcon
from PySide2.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from derby.core.db import categories_repo, products_repo
from derby.core.i18n import ar
from derby.core.utils.money import format_egp
from derby.features.menu import images
from derby.features.menu.arabic_search import filter_products_by_search

_GRID_COLUMNS = 4
_ALL_CATEGORIES = None


class ProductGrid(QWidget):
    product_clicked = Signal(int)

    def __init__(self, conn: sqlite3.Connection, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._selected_category_id = _ALL_CATEGORIES
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(ar.POS_SEARCH_PLACEHOLDER)
        self._search_input.textChanged.connect(self._reload_products)
        layout.addWidget(self._search_input)

        self._chips_layout = QHBoxLayout()
        layout.addLayout(self._chips_layout)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        self._grid_host = QWidget()
        self._grid_layout = QGridLayout(self._grid_host)
        scroll_area.setWidget(self._grid_host)
        layout.addWidget(scroll_area)

    def reload(self) -> None:
        self._reload_category_chips()
        self._reload_products()

    def _reload_category_chips(self) -> None:
        while self._chips_layout.count():
            item = self._chips_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

        all_button = QPushButton(ar.MENU_ALL_CATEGORIES)
        all_button.clicked.connect(lambda: self._on_category_chip_clicked(_ALL_CATEGORIES))
        self._chips_layout.addWidget(all_button)

        for category in categories_repo.list_categories(self._conn, active_only=True):
            button = QPushButton(category["name"])
            button.clicked.connect(lambda _checked=False, cid=category["id"]: self._on_category_chip_clicked(cid))
            self._chips_layout.addWidget(button)
        self._chips_layout.addStretch(1)

    def _on_category_chip_clicked(self, category_id) -> None:
        self._selected_category_id = category_id
        self._reload_products()

    def _reload_products(self) -> None:
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

        products = products_repo.list_products(self._conn, self._selected_category_id, active_only=True)
        filtered = filter_products_by_search(products, self._search_input.text())

        for index, product in enumerate(filtered):
            row, col = divmod(index, _GRID_COLUMNS)
            self._grid_layout.addWidget(self._build_product_card(product), row, col)

    def _build_product_card(self, product) -> QPushButton:
        button = QPushButton("{0}\n{1}".format(product["name_ar"], format_egp(product["price_piasters"])))
        button.setMinimumSize(140, 110)
        button.setIconSize(QSize(64, 64))
        pixmap = images.load_thumbnail_pixmap(product["image_file"])
        if pixmap is not None:
            button.setIcon(QIcon(pixmap))
        button.clicked.connect(lambda _checked=False, pid=product["id"]: self.product_clicked.emit(pid))
        return button
