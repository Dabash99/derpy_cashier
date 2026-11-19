"""Small dialogs the supplies screen opens: editing a needed item, and
(owner only) converting a bought item into a real expense.
"""
from __future__ import annotations

import sqlite3

from PySide2.QtWidgets import QComboBox, QDialog, QFormLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from derby.core.db import expense_categories_repo
from derby.core.i18n import ar
from derby.features.menu.price_parsing import parse_product_price
from derby.features.supplies import supplies_service
from derby.features.supplies.exceptions import InvalidCostError, SupplyNameRequiredError, SupplyNotBoughtError

_DEFAULT_EXPENSE_CATEGORY_NAME = "أدوات شغل"


class SupplyEditDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, supply: sqlite3.Row, user: sqlite3.Row, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._supply = supply
        self._user = user
        self.setWindowTitle(ar.SUPPLIES_EDIT_DIALOG_TITLE)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self._name_input = QLineEdit(self._supply["name"])
        form.addRow(ar.SUPPLIES_NAME_PLACEHOLDER, self._name_input)

        self._quantity_input = QLineEdit(self._supply["quantity_note"] or "")
        form.addRow(ar.SUPPLIES_QUANTITY_PLACEHOLDER, self._quantity_input)

        self._priority_input = QComboBox()
        self._priority_input.addItem(ar.SUPPLIES_PRIORITY_NORMAL, supplies_service.PRIORITY_NORMAL)
        self._priority_input.addItem(ar.SUPPLIES_PRIORITY_URGENT, supplies_service.PRIORITY_URGENT)
        index = self._priority_input.findData(self._supply["priority"])
        if index >= 0:
            self._priority_input.setCurrentIndex(index)
        form.addRow(ar.SUPPLIES_PRIORITY_NORMAL, self._priority_input)

        self._note_input = QLineEdit(self._supply["note"] or "")
        form.addRow(ar.SUPPLIES_NOTE_PLACEHOLDER, self._note_input)

        self._error_label = QLabel("")
        self._error_label.setProperty("role", "error")
        layout.addWidget(self._error_label)

        save_button = QPushButton(ar.SUPPLIES_SAVE_BUTTON)
        save_button.setProperty("variant", "primary")
        save_button.clicked.connect(self._on_save)
        layout.addWidget(save_button)

    def _on_save(self) -> None:
        try:
            supplies_service.update_supply(
                self._conn, self._supply["id"], self._name_input.text(), self._quantity_input.text(),
                self._priority_input.currentData(), self._note_input.text(), self._user["id"],
            )
        except SupplyNameRequiredError:
            self._error_label.setText(ar.SUPPLIES_ERROR_NAME_REQUIRED)
            return
        self.accept()


class ConvertToExpenseDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, supply: sqlite3.Row, user: sqlite3.Row, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._supply = supply
        self._user = user
        self.setWindowTitle(ar.SUPPLIES_CONVERT_DIALOG_TITLE)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self._supply["name"]))
        form = QFormLayout()
        layout.addLayout(form)

        self._category_input = QComboBox()
        categories = expense_categories_repo.list_categories(self._conn, active_only=True)
        default_index = 0
        for index, category in enumerate(categories):
            self._category_input.addItem(category["name"], category["id"])
            if category["name"] == _DEFAULT_EXPENSE_CATEGORY_NAME:
                default_index = index
        self._category_input.setCurrentIndex(default_index)
        form.addRow(ar.SUPPLIES_CATEGORY_LABEL, self._category_input)

        self._cost_input = QLineEdit()
        form.addRow(ar.SUPPLIES_COST_LABEL, self._cost_input)

        self._error_label = QLabel("")
        self._error_label.setProperty("role", "error")
        layout.addWidget(self._error_label)

        convert_button = QPushButton(ar.SUPPLIES_CONVERT_TO_EXPENSE_BUTTON)
        convert_button.setProperty("variant", "primary")
        convert_button.clicked.connect(self._on_convert)
        layout.addWidget(convert_button)

    def _on_convert(self) -> None:
        try:
            cost_piasters = parse_product_price(self._cost_input.text())
        except ValueError:
            self._error_label.setText(ar.SUPPLIES_ERROR_COST_INVALID)
            return
        try:
            supplies_service.convert_to_expense(
                self._conn, self._supply["id"], self._category_input.currentData(), cost_piasters, self._user
            )
        except (InvalidCostError, SupplyNotBoughtError):
            self._error_label.setText(ar.SUPPLIES_ERROR_COST_INVALID)
            return
        self.accept()
