"""The products table (middle of the menu screen): thumbnail, names,
price, status, "needs review" badge. Thumbnails are only loaded for rows
actually scrolled into view, on top of images.py's own small pixmap
cache -- a 106-row menu should never have to decode 106 images at once.
"""
from __future__ import annotations

from PySide2.QtCore import QSize, QTimer, Signal
from PySide2.QtGui import QIcon
from PySide2.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from derby.core.i18n import ar
from derby.core.theme.table_style import centered_item, configure_table, right_item
from derby.core.utils.money import format_egp
from derby.features.menu import images

_COLUMN_IMAGE = 0
_COLUMN_NAME_AR = 1
_COLUMN_NAME_EN = 2
_COLUMN_PRICE = 3
_COLUMN_STATUS = 4
_COLUMN_REVIEW = 5


class ProductsTable(QWidget):
    edit_requested = Signal(int)
    toggle_active_requested = Signal(int)
    confirm_price_requested = Signal(int)

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._products = []
        self._loaded_rows = set()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            [
                ar.MENU_COLUMN_IMAGE,
                ar.MENU_COLUMN_NAME_AR,
                ar.MENU_COLUMN_NAME_EN,
                ar.MENU_COLUMN_PRICE,
                ar.MENU_COLUMN_STATUS,
                ar.MENU_COLUMN_REVIEW,
            ]
        )
        self._table.setIconSize(QSize(40, 40))
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        configure_table(
            self._table,
            stretch_columns=(_COLUMN_NAME_AR, _COLUMN_NAME_EN),
            fixed_widths={_COLUMN_IMAGE: 64, _COLUMN_PRICE: 100, _COLUMN_STATUS: 90, _COLUMN_REVIEW: 120},
        )
        self._table.verticalScrollBar().valueChanged.connect(lambda _value: self._load_visible_thumbnails())
        self._table.cellDoubleClicked.connect(self._on_double_clicked)
        self._table.itemSelectionChanged.connect(self._refresh_actions_state)
        layout.addWidget(self._table)

        actions_row = QHBoxLayout()
        edit_button = QPushButton(ar.MENU_PRODUCT_EDIT_BUTTON)
        edit_button.clicked.connect(self._on_edit_clicked)
        actions_row.addWidget(edit_button)

        self._toggle_active_button = QPushButton(ar.MENU_PRODUCT_DEACTIVATE_BUTTON)
        self._toggle_active_button.clicked.connect(self._on_toggle_active_clicked)
        actions_row.addWidget(self._toggle_active_button)

        confirm_price_button = QPushButton(ar.MENU_PRODUCT_CONFIRM_PRICE_BUTTON)
        confirm_price_button.clicked.connect(self._on_confirm_price_clicked)
        actions_row.addWidget(confirm_price_button)

        layout.addLayout(actions_row)
        self._actions = [self._toggle_active_button]
        self._refresh_actions_state()

    def set_products(self, products) -> None:
        self._products = list(products)
        self._loaded_rows = set()
        self._table.setRowCount(len(self._products))
        for row, product in enumerate(self._products):
            self._table.setItem(row, _COLUMN_IMAGE, centered_item(""))
            self._table.setItem(row, _COLUMN_NAME_AR, right_item(product["name_ar"]))
            self._table.setItem(row, _COLUMN_NAME_EN, right_item(product["name_en"] or ""))
            self._table.setItem(row, _COLUMN_PRICE, centered_item(format_egp(product["price_piasters"])))
            status_text = ar.USERS_INACTIVE_LABEL if not product["is_active"] else ar.USERS_ACTIVE_LABEL
            self._table.setItem(row, _COLUMN_STATUS, centered_item(status_text))
            review_text = ar.MENU_NEEDS_REVIEW_BADGE if product["needs_price_review"] else ""
            self._table.setItem(row, _COLUMN_REVIEW, centered_item(review_text))
        QTimer.singleShot(0, self._load_visible_thumbnails)
        self._refresh_actions_state()

    def _load_visible_thumbnails(self) -> None:
        row_count = self._table.rowCount()
        if row_count == 0:
            return
        first_row = self._table.rowAt(0)
        last_row = self._table.rowAt(max(0, self._table.viewport().height() - 1))
        if first_row == -1:
            first_row = 0
        if last_row == -1:
            last_row = row_count - 1

        for row in range(first_row, last_row + 1):
            if row in self._loaded_rows or row >= len(self._products):
                continue
            self._loaded_rows.add(row)
            product = self._products[row]
            pixmap = images.load_thumbnail_pixmap(product["image_file"])
            item = self._table.item(row, _COLUMN_IMAGE)
            if pixmap is not None and item is not None:
                item.setIcon(QIcon(pixmap))

    def selected_product_id(self):
        row = self._table.currentRow()
        if row < 0 or row >= len(self._products):
            return None
        return self._products[row]["id"]

    def _refresh_actions_state(self) -> None:
        product_id = self.selected_product_id()
        for widget in self._actions:
            widget.setEnabled(product_id is not None)
        if product_id is not None:
            row = self._table.currentRow()
            product = self._products[row]
            self._toggle_active_button.setText(
                ar.MENU_PRODUCT_REACTIVATE_BUTTON if not product["is_active"] else ar.MENU_PRODUCT_DEACTIVATE_BUTTON
            )

    def _on_double_clicked(self, row: int, _column: int) -> None:
        if 0 <= row < len(self._products):
            self.edit_requested.emit(self._products[row]["id"])

    def _on_edit_clicked(self) -> None:
        product_id = self.selected_product_id()
        if product_id is not None:
            self.edit_requested.emit(product_id)

    def _on_toggle_active_clicked(self) -> None:
        product_id = self.selected_product_id()
        if product_id is not None:
            self.toggle_active_requested.emit(product_id)

    def _on_confirm_price_clicked(self) -> None:
        product_id = self.selected_product_id()
        if product_id is not None:
            self.confirm_price_requested.emit(product_id)
