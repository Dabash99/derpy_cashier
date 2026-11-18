"""Owner-only: manage recurring expense templates (name, category,
amount, day of month, active). This never creates an actual expense --
that only happens through the due-this-month prompt (recurring_due_dialog.py).
"""
from __future__ import annotations

import sqlite3

from PySide2.QtCore import Signal
from PySide2.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from derby.core.db import expense_categories_repo, recurring_expenses_repo
from derby.core.i18n import ar
from derby.core.utils.money import piasters_to_plain_text
from derby.features.expenses import expenses_service
from derby.features.expenses.exceptions import InvalidAmountError
from derby.features.menu.price_parsing import parse_product_price

_TEMPLATE_ID_ROLE = 1000


class RecurringManagementPanel(QWidget):
    templates_changed = Signal()

    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel(ar.RECURRING_TITLE)
        title.setProperty("role", "title")
        layout.addWidget(title)

        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._refresh_actions_state)
        layout.addWidget(self._list)

        self._message_label = QLabel("")
        self._message_label.setProperty("role", "error")
        self._message_label.setWordWrap(True)
        layout.addWidget(self._message_label)

        form = QFormLayout()
        self._name_input = QLineEdit()
        form.addRow(ar.RECURRING_NAME_LABEL, self._name_input)
        self._category_input = QComboBox()
        for category in expense_categories_repo.list_categories(self._conn, active_only=True):
            self._category_input.addItem(category["name"], category["id"])
        form.addRow(ar.RECURRING_CATEGORY_LABEL, self._category_input)
        self._amount_input = QLineEdit()
        form.addRow(ar.RECURRING_AMOUNT_LABEL, self._amount_input)
        self._day_input = QLineEdit()
        form.addRow(ar.RECURRING_DAY_LABEL, self._day_input)
        layout.addLayout(form)

        buttons_row = QHBoxLayout()
        self._save_button = QPushButton(ar.RECURRING_SAVE_BUTTON)
        self._save_button.clicked.connect(self._on_save)
        buttons_row.addWidget(self._save_button)
        self._toggle_active_button = QPushButton(ar.RECURRING_DEACTIVATE_BUTTON)
        self._toggle_active_button.clicked.connect(self._on_toggle_active)
        buttons_row.addWidget(self._toggle_active_button)
        layout.addLayout(buttons_row)

    def _selected_template_id(self):
        item = self._list.currentItem()
        return item.data(_TEMPLATE_ID_ROLE) if item is not None else None

    def reload(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for template in recurring_expenses_repo.list_templates(self._conn):
            status = "" if template["is_active"] else " ({0})".format(ar.USERS_INACTIVE_LABEL)
            item = QListWidgetItem("{0} — {1}{2}".format(template["name"], piasters_to_plain_text(template["amount_piasters"]), status))
            item.setData(_TEMPLATE_ID_ROLE, template["id"])
            self._list.addItem(item)
        self._list.blockSignals(False)
        self._message_label.setText("")
        self._refresh_actions_state()

    def _refresh_actions_state(self) -> None:
        template_id = self._selected_template_id()
        if template_id is None:
            self._name_input.clear()
            self._amount_input.clear()
            self._day_input.clear()
            self._toggle_active_button.setEnabled(False)
            return
        template = recurring_expenses_repo.get_template(self._conn, template_id)
        self._name_input.setText(template["name"])
        index = self._category_input.findData(template["category_id"])
        if index >= 0:
            self._category_input.setCurrentIndex(index)
        self._amount_input.setText(piasters_to_plain_text(template["amount_piasters"]))
        self._day_input.setText(str(template["day_of_month"]))
        self._toggle_active_button.setEnabled(True)
        self._toggle_active_button.setText(
            ar.RECURRING_REACTIVATE_BUTTON if not template["is_active"] else ar.RECURRING_DEACTIVATE_BUTTON
        )

    def _read_fields(self):
        name = self._name_input.text().strip()
        if not name:
            raise ValueError(ar.RECURRING_ERROR_NAME_REQUIRED)
        category_id = self._category_input.currentData()
        try:
            amount = parse_product_price(self._amount_input.text())
        except ValueError:
            raise ValueError(ar.RECURRING_ERROR_AMOUNT_INVALID)
        try:
            day_of_month = int(self._day_input.text().strip())
        except ValueError:
            raise ValueError(ar.RECURRING_ERROR_DAY_INVALID)
        if not (1 <= day_of_month <= 31):
            raise ValueError(ar.RECURRING_ERROR_DAY_INVALID)
        return name, category_id, amount, day_of_month

    def _on_save(self) -> None:
        try:
            name, category_id, amount, day_of_month = self._read_fields()
        except ValueError as error:
            self._message_label.setText(str(error))
            return
        template_id = self._selected_template_id()
        try:
            if template_id is None:
                expenses_service.add_recurring_template(self._conn, category_id, name, amount, day_of_month, self._user["id"])
            else:
                expenses_service.update_recurring_template(
                    self._conn, template_id, category_id, name, amount, day_of_month, self._user["id"]
                )
        except InvalidAmountError:
            self._message_label.setText(ar.RECURRING_ERROR_AMOUNT_INVALID)
            return
        self.reload()
        self.templates_changed.emit()

    def _on_toggle_active(self) -> None:
        template_id = self._selected_template_id()
        if template_id is None:
            return
        template = recurring_expenses_repo.get_template(self._conn, template_id)
        expenses_service.set_recurring_active(self._conn, template_id, not template["is_active"], self._user["id"])
        self.reload()
        self.templates_changed.emit()
