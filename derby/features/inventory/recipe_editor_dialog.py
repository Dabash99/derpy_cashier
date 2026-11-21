"""The "الوصفة" editor opened from a product's or add-on's edit screen:
pick stock items and a quantity per unit, with a live computed cost and
margin vs the selling price. Saves the full recipe (recipes_repo.set_recipe
replaces it wholesale) -- there is no incremental add/remove on the DB
side, only in this dialog's in-memory rows until Save is pressed.
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from PySide2.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from derby.core.db import recipes_repo, stock_items_repo
from derby.core.i18n import ar
from derby.core.utils.money import format_egp

_STOCK_ITEM_ID_ROLE = 1000


class _RecipeRow(QWidget):
    def __init__(self, stock_items, on_changed, on_remove, stock_item_id: Optional[int] = None, qty_per_unit: str = "") -> None:
        super().__init__()
        self._on_changed = on_changed
        layout = QHBoxLayout(self)
        self._stock_item_input = QComboBox()
        for item in stock_items:
            self._stock_item_input.addItem("{0} ({1})".format(item["name"], item["unit"]), item["id"])
        if stock_item_id is not None:
            index = self._stock_item_input.findData(stock_item_id)
            if index >= 0:
                self._stock_item_input.setCurrentIndex(index)
        self._stock_item_input.currentIndexChanged.connect(lambda _i: on_changed())
        layout.addWidget(self._stock_item_input, 2)

        self._qty_input = QLineEdit(qty_per_unit)
        self._qty_input.setPlaceholderText(ar.RECIPE_QTY_PER_UNIT_PLACEHOLDER)
        self._qty_input.textChanged.connect(lambda _t: on_changed())
        layout.addWidget(self._qty_input, 1)

        remove_button = QPushButton(ar.RECIPE_REMOVE_LINE_BUTTON)
        remove_button.clicked.connect(lambda: on_remove(self))
        layout.addWidget(remove_button)

    def stock_item_id(self) -> Optional[int]:
        return self._stock_item_input.currentData()

    def qty_per_unit(self) -> Optional[float]:
        text = self._qty_input.text().strip().replace(",", ".")
        if not text:
            return None
        try:
            value = float(text)
        except ValueError:
            return None
        return value if value > 0 else None

    def avg_cost_piasters(self, stock_items_by_id) -> float:
        item = stock_items_by_id.get(self.stock_item_id())
        return item["avg_cost_piasters"] if item is not None else 0.0


class RecipeEditorDialog(QDialog):
    def __init__(
        self,
        conn: sqlite3.Connection,
        owner_type: str,
        owner_id: int,
        owner_name: str,
        selling_price_piasters: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        self._owner_type = owner_type
        self._owner_id = owner_id
        self._selling_price_piasters = selling_price_piasters
        self._rows = []
        self.setWindowTitle(ar.RECIPE_DIALOG_TITLE.format(name=owner_name))
        self._build_ui()
        self._load_existing()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        self._rows_host = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_host)
        scroll_area.setWidget(self._rows_host)
        layout.addWidget(scroll_area, 1)

        add_button = QPushButton(ar.RECIPE_ADD_LINE_BUTTON)
        add_button.clicked.connect(lambda: self._add_row())
        layout.addWidget(add_button)

        self._cost_label = QLabel("")
        layout.addWidget(self._cost_label)
        self._margin_label = QLabel("")
        layout.addWidget(self._margin_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(ar.GENERIC_SAVE)
        buttons.button(QDialogButtonBox.Cancel).setText(ar.GENERIC_CANCEL)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _stock_items(self):
        return stock_items_repo.list_stock_items(self._conn, active_only=True)

    def _load_existing(self) -> None:
        for line in recipes_repo.list_recipe_lines(self._conn, self._owner_type, self._owner_id):
            self._add_row(stock_item_id=line["stock_item_id"], qty_per_unit=str(line["qty_per_unit"]))
        if not self._rows:
            self._add_row()
        self._recompute()

    def _add_row(self, stock_item_id: Optional[int] = None, qty_per_unit: str = "") -> None:
        stock_items = self._stock_items()
        if not stock_items:
            self._cost_label.setText(ar.RECIPE_NO_STOCK_ITEMS)
            return
        row = _RecipeRow(stock_items, self._recompute, self._remove_row, stock_item_id, qty_per_unit)
        self._rows.append(row)
        self._rows_layout.addWidget(row)

    def _remove_row(self, row: _RecipeRow) -> None:
        self._rows.remove(row)
        row.setParent(None)
        row.deleteLater()
        self._recompute()

    def _recompute(self) -> None:
        stock_items_by_id = {item["id"]: item for item in self._stock_items()}
        total_cost = 0.0
        for row in self._rows:
            qty = row.qty_per_unit()
            if qty is None:
                continue
            total_cost += qty * row.avg_cost_piasters(stock_items_by_id)
        total_cost_int = int(round(total_cost))
        self._cost_label.setText(ar.RECIPE_COST_LABEL.format(cost=format_egp(total_cost_int)))
        if self._selling_price_piasters > 0:
            margin = (self._selling_price_piasters - total_cost_int) / self._selling_price_piasters * 100.0
            self._margin_label.setText(ar.RECIPE_MARGIN_LABEL.format(margin=margin))
        else:
            self._margin_label.setText("")

    def _on_save(self) -> None:
        lines = []
        for row in self._rows:
            stock_item_id = row.stock_item_id()
            qty = row.qty_per_unit()
            if stock_item_id is None or qty is None:
                continue
            lines.append({"stock_item_id": stock_item_id, "qty_per_unit": qty})
        recipes_repo.set_recipe(self._conn, self._owner_type, self._owner_id, lines)
        self.accept()
