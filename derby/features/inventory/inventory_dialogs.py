"""Dialogs opened from the Inventory screen: add/edit a stock item,
waste, stocktake, record a purchase, and add/edit a supplier.
"""
from __future__ import annotations

import sqlite3
from datetime import date
from typing import Optional

from PySide2.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from derby.core.db import stock_items_repo, suppliers_repo
from derby.core.i18n import ar
from derby.core.utils.money import format_egp
from derby.features.inventory import stock_service
from derby.features.inventory.exceptions import InvalidQuantityError, WasteReasonRequiredError

_UNIT_LABELS = (
    (stock_items_repo.UNITS[0], ar.INVENTORY_UNIT_GRAM),
    (stock_items_repo.UNITS[1], ar.INVENTORY_UNIT_KG),
    (stock_items_repo.UNITS[2], ar.INVENTORY_UNIT_ML),
    (stock_items_repo.UNITS[3], ar.INVENTORY_UNIT_L),
    (stock_items_repo.UNITS[4], ar.INVENTORY_UNIT_PIECE),
)


def _parse_qty(text: str) -> Optional[float]:
    text = text.strip().replace(",", ".")
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value


class StockItemDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, item: Optional[sqlite3.Row] = None, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._item = item
        self.setWindowTitle(ar.INVENTORY_ITEM_DIALOG_TITLE)
        self._build_ui()
        if item is not None:
            self._name_input.setText(item["name"])
            unit_index = self._unit_input.findData(item["unit"])
            if unit_index >= 0:
                self._unit_input.setCurrentIndex(unit_index)
            self._min_qty_input.setText(str(item["min_qty"]))
            self._active_checkbox.setChecked(bool(item["is_active"]))

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self._name_input = QLineEdit()
        form.addRow(ar.INVENTORY_ITEM_NAME_LABEL, self._name_input)

        self._unit_input = QComboBox()
        for unit, label in _UNIT_LABELS:
            self._unit_input.addItem(label, unit)
        form.addRow(ar.INVENTORY_ITEM_UNIT_LABEL, self._unit_input)

        self._min_qty_input = QLineEdit("0")
        form.addRow(ar.INVENTORY_ITEM_MIN_QTY_LABEL, self._min_qty_input)

        self._active_checkbox = QCheckBox(ar.INVENTORY_ITEM_ACTIVE_CHECKBOX)
        self._active_checkbox.setChecked(True)
        form.addRow("", self._active_checkbox)

        self._error_label = QLabel("")
        self._error_label.setProperty("role", "error")
        layout.addWidget(self._error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(ar.GENERIC_SAVE)
        buttons.button(QDialogButtonBox.Cancel).setText(ar.GENERIC_CANCEL)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_save(self) -> None:
        name = self._name_input.text().strip()
        if not name:
            self._error_label.setText(ar.INVENTORY_ERROR_NAME_REQUIRED)
            return
        existing = stock_items_repo.find_by_name(self._conn, name)
        if existing is not None and (self._item is None or existing["id"] != self._item["id"]):
            self._error_label.setText(ar.INVENTORY_ERROR_DUPLICATE_NAME)
            return
        min_qty = _parse_qty(self._min_qty_input.text()) or 0.0
        unit = self._unit_input.currentData()

        if self._item is None:
            stock_items_repo.create_stock_item(self._conn, name, unit, min_qty=min_qty)
        else:
            stock_items_repo.update_stock_item(
                self._conn, self._item["id"], name, unit, min_qty, self._active_checkbox.isChecked()
            )
        self.accept()


class WasteDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, item: sqlite3.Row, user: sqlite3.Row, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._item = item
        self._user = user
        self.setWindowTitle(ar.INVENTORY_WASTE_DIALOG_TITLE)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self._item["name"]))
        form = QFormLayout()
        layout.addLayout(form)

        self._qty_input = QLineEdit()
        form.addRow(ar.INVENTORY_WASTE_QTY_LABEL, self._qty_input)
        self._reason_input = QLineEdit()
        form.addRow(ar.INVENTORY_WASTE_REASON_LABEL, self._reason_input)

        self._error_label = QLabel("")
        self._error_label.setProperty("role", "error")
        layout.addWidget(self._error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(ar.GENERIC_SAVE)
        buttons.button(QDialogButtonBox.Cancel).setText(ar.GENERIC_CANCEL)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_save(self) -> None:
        qty = _parse_qty(self._qty_input.text())
        if qty is None or qty <= 0:
            self._error_label.setText(ar.INVENTORY_ERROR_QTY_INVALID)
            return
        try:
            stock_service.record_waste(self._conn, self._item["id"], qty, self._reason_input.text(), self._user["id"])
        except WasteReasonRequiredError:
            self._error_label.setText(ar.INVENTORY_ERROR_REASON_REQUIRED)
            return
        except InvalidQuantityError:
            self._error_label.setText(ar.INVENTORY_ERROR_QTY_INVALID)
            return
        self.accept()


class StocktakeDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, item: sqlite3.Row, user: sqlite3.Row, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._item = item
        self._user = user
        self.setWindowTitle(ar.INVENTORY_STOCKTAKE_DIALOG_TITLE)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self._item["name"]))
        form = QFormLayout()
        layout.addLayout(form)

        form.addRow(ar.INVENTORY_STOCKTAKE_CURRENT_LABEL, QLabel(str(self._item["current_qty"])))
        self._counted_input = QLineEdit(str(self._item["current_qty"]))
        form.addRow(ar.INVENTORY_STOCKTAKE_COUNTED_LABEL, self._counted_input)
        self._note_input = QLineEdit()
        form.addRow(ar.INVENTORY_STOCKTAKE_NOTE_LABEL, self._note_input)

        self._difference_label = QLabel("")
        layout.addWidget(self._difference_label)
        self._error_label = QLabel("")
        self._error_label.setProperty("role", "error")
        layout.addWidget(self._error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(ar.GENERIC_SAVE)
        buttons.button(QDialogButtonBox.Cancel).setText(ar.GENERIC_CANCEL)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_save(self) -> None:
        counted = _parse_qty(self._counted_input.text())
        if counted is None or counted < 0:
            self._error_label.setText(ar.INVENTORY_ERROR_QTY_INVALID)
            return
        difference = counted - self._item["current_qty"]
        value = format_egp(int(round(abs(difference) * self._item["avg_cost_piasters"])))
        self._difference_label.setText(ar.INVENTORY_STOCKTAKE_DIFFERENCE_LABEL.format(difference=difference, value=value))
        stock_service.record_stocktake(self._conn, self._item["id"], counted, self._user["id"], note=self._note_input.text() or None)
        self.accept()


class SupplierDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, supplier: Optional[sqlite3.Row] = None, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._supplier = supplier
        self.setWindowTitle(ar.INVENTORY_SUPPLIER_DIALOG_TITLE)
        self._build_ui()
        if supplier is not None:
            self._name_input.setText(supplier["name"])
            self._phone_input.setText(supplier["phone"] or "")
            self._notes_input.setText(supplier["notes"] or "")

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self._name_input = QLineEdit()
        form.addRow(ar.INVENTORY_SUPPLIER_NAME_LABEL, self._name_input)
        self._phone_input = QLineEdit()
        form.addRow(ar.INVENTORY_SUPPLIER_PHONE_LABEL, self._phone_input)
        self._notes_input = QLineEdit()
        form.addRow(ar.INVENTORY_SUPPLIER_NOTES_LABEL, self._notes_input)

        self._error_label = QLabel("")
        self._error_label.setProperty("role", "error")
        layout.addWidget(self._error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(ar.GENERIC_SAVE)
        buttons.button(QDialogButtonBox.Cancel).setText(ar.GENERIC_CANCEL)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_save(self) -> None:
        name = self._name_input.text().strip()
        if not name:
            self._error_label.setText(ar.INVENTORY_ERROR_NAME_REQUIRED)
            return
        if self._supplier is None:
            suppliers_repo.create_supplier(self._conn, name, self._phone_input.text().strip() or None, self._notes_input.text().strip() or None)
        else:
            suppliers_repo.update_supplier(
                self._conn, self._supplier["id"], name, self._phone_input.text().strip() or None,
                self._notes_input.text().strip() or None, True,
            )
        self.accept()


class _PurchaseLineRow(QWidget):
    def __init__(self, stock_items, on_changed, on_remove) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        self._stock_item_input = QComboBox()
        for item in stock_items:
            self._stock_item_input.addItem("{0} ({1})".format(item["name"], item["unit"]), item["id"])
        self._stock_item_input.currentIndexChanged.connect(lambda _i: on_changed())
        layout.addWidget(self._stock_item_input, 2)

        self._qty_input = QLineEdit()
        self._qty_input.setPlaceholderText(ar.INVENTORY_PURCHASE_LINE_QTY_PLACEHOLDER)
        self._qty_input.textChanged.connect(lambda _t: on_changed())
        layout.addWidget(self._qty_input, 1)

        self._cost_input = QLineEdit()
        self._cost_input.setPlaceholderText(ar.INVENTORY_PURCHASE_LINE_COST_PLACEHOLDER)
        self._cost_input.textChanged.connect(lambda _t: on_changed())
        layout.addWidget(self._cost_input, 1)

        remove_button = QPushButton(ar.RECIPE_REMOVE_LINE_BUTTON)
        remove_button.clicked.connect(lambda: on_remove(self))
        layout.addWidget(remove_button)

    def values(self):
        """Returns (stock_item_id, qty, unit_cost_piasters) or None if the
        row is incomplete/invalid."""
        stock_item_id = self._stock_item_input.currentData()
        qty = _parse_qty(self._qty_input.text())
        cost = _parse_qty(self._cost_input.text())
        if stock_item_id is None or qty is None or qty <= 0 or cost is None or cost < 0:
            return None
        return stock_item_id, qty, cost


class PurchaseDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._rows = []
        self.setWindowTitle(ar.INVENTORY_PURCHASE_DIALOG_TITLE)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self._supplier_input = QComboBox()
        self._supplier_input.addItem("—", None)
        for supplier in suppliers_repo.list_suppliers(self._conn, active_only=True):
            self._supplier_input.addItem(supplier["name"], supplier["id"])
        form.addRow(ar.INVENTORY_PURCHASE_SUPPLIER_LABEL, self._supplier_input)

        self._date_input = QLineEdit(date.today().isoformat())
        form.addRow(ar.INVENTORY_PURCHASE_DATE_LABEL, self._date_input)

        self._paid_checkbox = QCheckBox(ar.INVENTORY_PURCHASE_PAID_CHECKBOX)
        form.addRow("", self._paid_checkbox)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        self._rows_host = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_host)
        scroll_area.setWidget(self._rows_host)
        layout.addWidget(scroll_area, 1)

        add_line_button = QPushButton(ar.INVENTORY_PURCHASE_ADD_LINE_BUTTON)
        add_line_button.clicked.connect(self._add_row)
        layout.addWidget(add_line_button)

        self._total_label = QLabel(ar.INVENTORY_PURCHASE_TOTAL_LABEL.format(total=format_egp(0)))
        layout.addWidget(self._total_label)

        self._error_label = QLabel("")
        self._error_label.setProperty("role", "error")
        layout.addWidget(self._error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(ar.INVENTORY_PURCHASE_SAVE_BUTTON)
        buttons.button(QDialogButtonBox.Cancel).setText(ar.GENERIC_CANCEL)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._add_row()

    def _stock_items(self):
        return stock_items_repo.list_stock_items(self._conn, active_only=True)

    def _add_row(self) -> None:
        stock_items = self._stock_items()
        if not stock_items:
            self._error_label.setText(ar.RECIPE_NO_STOCK_ITEMS)
            return
        row = _PurchaseLineRow(stock_items, self._recompute_total, self._remove_row)
        self._rows.append(row)
        self._rows_layout.addWidget(row)

    def _remove_row(self, row: _PurchaseLineRow) -> None:
        self._rows.remove(row)
        row.setParent(None)
        row.deleteLater()
        self._recompute_total()

    def _recompute_total(self) -> None:
        total = 0
        for row in self._rows:
            values = row.values()
            if values is not None:
                _stock_item_id, qty, cost = values
                total += int(round(qty * cost))
        self._total_label.setText(ar.INVENTORY_PURCHASE_TOTAL_LABEL.format(total=format_egp(total)))

    def _on_save(self) -> None:
        lines = []
        for row in self._rows:
            values = row.values()
            if values is None:
                continue
            stock_item_id, qty, cost = values
            lines.append({"stock_item_id": stock_item_id, "qty": qty, "unit_cost_piasters": cost})
        if not lines:
            self._error_label.setText(ar.INVENTORY_PURCHASE_ERROR_NO_LINES)
            return
        try:
            purchase_date = date.fromisoformat(self._date_input.text().strip())
        except ValueError:
            self._error_label.setText(ar.INVENTORY_PURCHASE_ERROR_LINE_INVALID)
            return
        stock_service.record_purchase(
            self._conn, self._supplier_input.currentData(), purchase_date.isoformat(), lines,
            self._paid_checkbox.isChecked(), self._user["id"],
        )
        self.accept()
