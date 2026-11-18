"""Add a new expense, or void+replace ("edit") an existing one -- same
dialog, two modes, since the fields are identical. Replacing always
needs a reason; adding never does.
"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Optional

from PySide2.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from derby.core.db import expense_categories_repo
from derby.core.i18n import ar
from derby.features.expenses import expenses_service
from derby.features.expenses.exceptions import (
    FutureDateError,
    InvalidAmountError,
    InvalidReceiptImageError,
    VoidReasonRequiredError,
)
from derby.features.menu.price_parsing import parse_product_price

_CATEGORY_ID_ROLE = 1000
_IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp)"


class ExpenseDialog(QDialog):
    def __init__(
        self, conn: sqlite3.Connection, user: sqlite3.Row, existing_expense: Optional[sqlite3.Row] = None, parent=None
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._existing_expense = existing_expense
        self._pending_receipt_path: Optional[Path] = None
        self.setWindowTitle(ar.EXPENSE_DIALOG_REPLACE_TITLE if existing_expense is not None else ar.EXPENSE_DIALOG_ADD_TITLE)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self._category_input = QComboBox()
        categories = expense_categories_repo.list_categories(self._conn, active_only=True)
        if self._existing_expense is not None:
            current_id = self._existing_expense["category_id"]
            if current_id not in [c["id"] for c in categories]:
                current = expense_categories_repo.get_category(self._conn, current_id)
                if current is not None:
                    categories = [current] + list(categories)
        for category in categories:
            self._category_input.addItem(category["name"], category["id"])
        form.addRow(ar.EXPENSE_CATEGORY_LABEL, self._category_input)

        self._amount_input = QLineEdit()
        form.addRow(ar.EXPENSE_AMOUNT_LABEL, self._amount_input)

        self._date_input = QLineEdit()
        form.addRow(ar.EXPENSE_DATE_LABEL, self._date_input)

        self._description_input = QLineEdit()
        form.addRow(ar.EXPENSE_DESCRIPTION_LABEL, self._description_input)

        if self._existing_expense is not None:
            self._reason_input = QLineEdit()
            form.addRow(ar.EXPENSE_VOID_REASON_LABEL, self._reason_input)
        else:
            self._reason_input = None

        receipt_row = QFormLayout()
        self._receipt_label = QLabel(ar.EXPENSE_RECEIPT_NONE)
        choose_button = QPushButton(ar.EXPENSE_RECEIPT_CHOOSE_BUTTON)
        choose_button.clicked.connect(self._on_choose_receipt)
        remove_button = QPushButton(ar.EXPENSE_RECEIPT_REMOVE_BUTTON)
        remove_button.clicked.connect(self._on_remove_receipt)
        receipt_row.addRow(self._receipt_label)
        receipt_row.addRow(choose_button, remove_button)
        layout.addLayout(receipt_row)

        self._error_label = QLabel("")
        self._error_label.setProperty("role", "error")
        self._error_label.setWordWrap(True)
        layout.addWidget(self._error_label)

        self._prefill()

        if self._existing_expense is not None:
            replace_button = QPushButton(ar.EXPENSE_REPLACE_BUTTON)
            replace_button.clicked.connect(self._on_replace)
            layout.addWidget(replace_button)
            void_only_button = QPushButton(ar.EXPENSE_VOID_ONLY_BUTTON)
            void_only_button.setProperty("danger", "true")
            void_only_button.clicked.connect(self._on_void_only)
            layout.addWidget(void_only_button)
        else:
            save_button = QPushButton(ar.EXPENSE_SAVE_BUTTON)
            save_button.clicked.connect(self._on_add)
            layout.addWidget(save_button)

    def _prefill(self) -> None:
        if self._existing_expense is None:
            self._date_input.setText(expenses_service.today_business_date(self._conn).isoformat())
            return
        expense = self._existing_expense
        index = self._category_input.findData(expense["category_id"])
        if index >= 0:
            self._category_input.setCurrentIndex(index)
        self._amount_input.setText(str(expense["amount_piasters"] // 100) + ".{0:02d}".format(expense["amount_piasters"] % 100))
        self._date_input.setText(expense["expense_date"])
        self._description_input.setText(expense["description"] or "")
        if expense["receipt_file"]:
            self._receipt_label.setText(ar.EXPENSES_RECEIPT_HAS_ONE)

    def _on_choose_receipt(self) -> None:
        file_path, _filter = QFileDialog.getOpenFileName(self, ar.EXPENSE_RECEIPT_CHOOSE_BUTTON, "", _IMAGE_FILTER)
        if not file_path:
            return
        self._pending_receipt_path = Path(file_path)
        self._receipt_label.setText(ar.EXPENSES_RECEIPT_HAS_ONE)

    def _on_remove_receipt(self) -> None:
        self._pending_receipt_path = None
        self._receipt_label.setText(ar.EXPENSE_RECEIPT_NONE)

    def _read_common_fields(self):
        category_id = self._category_input.currentData()
        amount = parse_product_price(self._amount_input.text())
        expense_date = date.fromisoformat(self._date_input.text().strip())
        description = self._description_input.text().strip() or None
        return category_id, amount, expense_date, description

    def _on_add(self) -> None:
        try:
            category_id, amount, expense_date, description = self._read_common_fields()
        except ValueError:
            self._error_label.setText(ar.EXPENSE_ERROR_DATE_INVALID)
            return
        try:
            expenses_service.create_expense(
                self._conn, category_id, amount, expense_date, description, self._user["id"],
                receipt_source_path=self._pending_receipt_path,
            )
        except InvalidAmountError:
            self._error_label.setText(ar.EXPENSE_ERROR_AMOUNT_INVALID)
            return
        except FutureDateError:
            self._error_label.setText(ar.EXPENSE_ERROR_DATE_FUTURE)
            return
        except InvalidReceiptImageError:
            self._error_label.setText(ar.EXPENSE_ERROR_IMAGE_INVALID)
            return
        self.accept()

    def _on_replace(self) -> None:
        try:
            category_id, amount, expense_date, description = self._read_common_fields()
        except ValueError:
            self._error_label.setText(ar.EXPENSE_ERROR_DATE_INVALID)
            return
        try:
            expenses_service.replace_expense(
                self._conn, self._existing_expense["id"], self._reason_input.text(), category_id, amount,
                expense_date, description, self._user["id"], receipt_source_path=self._pending_receipt_path,
            )
        except VoidReasonRequiredError:
            self._error_label.setText(ar.EXPENSE_ERROR_REASON_REQUIRED)
            return
        except InvalidAmountError:
            self._error_label.setText(ar.EXPENSE_ERROR_AMOUNT_INVALID)
            return
        except FutureDateError:
            self._error_label.setText(ar.EXPENSE_ERROR_DATE_FUTURE)
            return
        except InvalidReceiptImageError:
            self._error_label.setText(ar.EXPENSE_ERROR_IMAGE_INVALID)
            return
        self.accept()

    def _on_void_only(self) -> None:
        try:
            expenses_service.void_expense(self._conn, self._existing_expense["id"], self._reason_input.text(), self._user["id"])
        except VoidReasonRequiredError:
            self._error_label.setText(ar.EXPENSE_ERROR_REASON_REQUIRED)
            return
        self.accept()
