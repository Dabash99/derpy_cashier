"""Right-hand side of the cashier screen: category pill chips (horizontally
scrollable so none get clipped), Arabic search, and a responsive grid of
ProductCard tiles (see product_card.py for the card itself).

Cards are built once per reload() (cheap -- no image decoding happens at
construction time, see ProductCard.set_placeholder_image), and each
card's real thumbnail is only decoded/cropped once it scrolls into the
visible viewport (_reveal_visible_cards), so opening the cashier screen
or switching category stays instant even with 100+ products.
"""
from __future__ import annotations

from PySide2.QtCore import QRect, Qt, QTimer, Signal
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
from derby.features.menu.arabic_search import filter_products_by_search
from derby.features.pos.product_card import CARD_WIDTH, ProductCard

_MIN_COLUMNS = 3
_MAX_COLUMNS = 5
_DEFAULT_COLUMNS = 4
_GRID_SPACING = 12
_REVEAL_LOOKAHEAD_PX = 200
_ALL_CATEGORIES = None


class ProductGrid(QWidget):
    product_clicked = Signal(int)

    def __init__(self, conn, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._selected_category_id = _ALL_CATEGORIES
        self._chip_buttons = {}
        self._cards = []
        self._columns = _DEFAULT_COLUMNS
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(ar.POS_SEARCH_PLACEHOLDER)
        self._search_input.textChanged.connect(self._reload_products)
        layout.addWidget(self._search_input)

        chips_scroll = QScrollArea()
        chips_scroll.setWidgetResizable(True)
        chips_scroll.setFixedHeight(48)
        chips_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        chips_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        chips_host = QWidget()
        self._chips_layout = QHBoxLayout(chips_host)
        chips_scroll.setWidget(chips_host)
        layout.addWidget(chips_scroll)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._grid_host = QWidget()
        # setWidgetResizable(True) stretches _grid_host to the viewport's
        # full height whenever the content is shorter than it -- without
        # this wrapper + trailing stretch, QGridLayout would spread that
        # leftover space into the cards themselves, stretching every
        # card tall with a dead gap under its price pill.
        host_layout = QVBoxLayout(self._grid_host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout = QGridLayout()
        self._grid_layout.setSpacing(_GRID_SPACING)
        host_layout.addLayout(self._grid_layout)
        host_layout.addStretch(1)
        self._scroll_area.setWidget(self._grid_host)
        self._scroll_area.verticalScrollBar().valueChanged.connect(self._reveal_visible_cards)
        layout.addWidget(self._scroll_area)

    def reload(self) -> None:
        self._reload_category_chips()
        self._reload_products()

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

    # --- category chips --------------------------------------------------

    def _reload_category_chips(self) -> None:
        self._clear_layout(self._chips_layout)
        self._chip_buttons = {}

        all_button = QPushButton(ar.MENU_ALL_CATEGORIES)
        all_button.setProperty("variant", "chip")
        all_button.clicked.connect(lambda: self._on_category_chip_clicked(_ALL_CATEGORIES))
        self._chips_layout.addWidget(all_button)
        self._chip_buttons[_ALL_CATEGORIES] = all_button

        for category in categories_repo.list_categories(self._conn, active_only=True):
            button = QPushButton(category["name"])
            button.setProperty("variant", "chip")
            button.clicked.connect(lambda _checked=False, cid=category["id"]: self._on_category_chip_clicked(cid))
            self._chips_layout.addWidget(button)
            self._chip_buttons[category["id"]] = button

        self._chips_layout.addStretch(1)
        self._update_chip_styles()

    def _update_chip_styles(self) -> None:
        for category_id, button in self._chip_buttons.items():
            button.setProperty("selected", "true" if category_id == self._selected_category_id else "false")
            button.style().unpolish(button)
            button.style().polish(button)

    def _on_category_chip_clicked(self, category_id) -> None:
        self._selected_category_id = category_id
        self._update_chip_styles()
        self._reload_products()

    # --- product cards ---------------------------------------------------

    def _compute_columns(self) -> int:
        viewport_width = self._scroll_area.viewport().width() or self.width()
        card_slot_width = CARD_WIDTH + _GRID_SPACING
        if viewport_width <= 0:
            return _DEFAULT_COLUMNS
        columns = viewport_width // card_slot_width
        return max(_MIN_COLUMNS, min(_MAX_COLUMNS, columns)) or _DEFAULT_COLUMNS

    def _reload_products(self) -> None:
        self._clear_layout(self._grid_layout)
        self._cards = []

        products = products_repo.list_products(self._conn, self._selected_category_id, active_only=True)
        filtered = filter_products_by_search(products, self._search_input.text())
        self._columns = self._compute_columns()

        for index, product in enumerate(filtered):
            row, col = divmod(index, self._columns)
            card = ProductCard(product["name_ar"], product["price_piasters"], product["image_file"])
            card.clicked.connect(lambda _checked=False, pid=product["id"]: self.product_clicked.emit(pid))
            self._grid_layout.addWidget(card, row, col)
            self._cards.append(card)

        QTimer.singleShot(0, self._reveal_visible_cards)

    def _relayout_cards(self) -> None:
        for index, card in enumerate(self._cards):
            row, col = divmod(index, self._columns)
            self._grid_layout.addWidget(card, row, col)

    def resizeEvent(self, event) -> None:  # noqa: N802 -- Qt override
        super().resizeEvent(event)
        new_columns = self._compute_columns()
        if new_columns != self._columns and self._cards:
            self._columns = new_columns
            self._relayout_cards()
        self._reveal_visible_cards()

    def _reveal_visible_cards(self) -> None:
        if not self._cards:
            return
        viewport = self._scroll_area.viewport()
        visible_rect = viewport.rect().adjusted(0, -_REVEAL_LOOKAHEAD_PX, 0, _REVEAL_LOOKAHEAD_PX)
        for card in self._cards:
            card_rect = QRect(card.mapTo(viewport, card.rect().topLeft()), card.size())
            if visible_rect.intersects(card_rect):
                card.load_image()
