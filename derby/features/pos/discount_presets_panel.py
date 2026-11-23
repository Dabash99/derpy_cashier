"""خصومات محفوظة (owner only, inside الإعدادات): manage named discount
presets shown as quick-fill buttons in the checkout discount dialog.
"""
from __future__ import annotations

import sqlite3

from PySide2.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from derby.core import audit_service
from derby.core.db import discount_presets_repo
from derby.core.i18n import ar
from derby.core.utils.money import egp_to_piasters, format_egp
from derby.features.pos.discount_math import DISCOUNT_KIND_FIXED, DISCOUNT_KIND_PERCENT


class DiscountPresetsPanel(QWidget):
    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._selected_id = None
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel(ar.DISCOUNT_PRESETS_TITLE)
        title.setProperty("role", "title")
        layout.addWidget(title)

        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_selection_changed)
        layout.addWidget(self._list)

        form_row = QHBoxLayout()
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText(ar.DISCOUNT_PRESETS_NAME_LABEL)
        form_row.addWidget(self._name_input)
        self._kind_input = QComboBox()
        self._kind_input.addItem(ar.DISCOUNT_KIND_FIXED_LABEL, DISCOUNT_KIND_FIXED)
        self._kind_input.addItem(ar.DISCOUNT_KIND_PERCENT_LABEL, DISCOUNT_KIND_PERCENT)
        form_row.addWidget(self._kind_input)
        self._amount_input = QSpinBox()
        self._amount_input.setRange(1, 100_000)
        form_row.addWidget(self._amount_input)
        layout.addLayout(form_row)

        actions_row = QHBoxLayout()
        add_button = QPushButton(ar.DISCOUNT_PRESETS_ADD_BUTTON)
        add_button.clicked.connect(self._on_add)
        actions_row.addWidget(add_button)
        self._toggle_button = QPushButton(ar.DISCOUNT_PRESETS_DEACTIVATE_BUTTON)
        self._toggle_button.clicked.connect(self._on_toggle_active)
        self._toggle_button.setEnabled(False)
        actions_row.addWidget(self._toggle_button)
        layout.addLayout(actions_row)

        self._message_label = QLabel("")
        layout.addWidget(self._message_label)

    def reload(self) -> None:
        self._list.clear()
        for preset in discount_presets_repo.list_presets(self._conn):
            kind_label = ar.DISCOUNT_KIND_PERCENT_LABEL if preset["kind"] == DISCOUNT_KIND_PERCENT else ar.DISCOUNT_KIND_FIXED_LABEL
            amount_text = "{0}%".format(preset["amount"]) if preset["kind"] == DISCOUNT_KIND_PERCENT else format_egp(preset["amount"])
            status = "" if preset["is_active"] else " — معطّل"
            item = QListWidgetItem("{0} — {1} {2}{3}".format(preset["name"], kind_label, amount_text, status))
            item.setData(1000, preset["id"])
            self._list.addItem(item)

    def _on_selection_changed(self, current: QListWidgetItem, _previous) -> None:
        self._selected_id = current.data(1000) if current is not None else None
        self._toggle_button.setEnabled(self._selected_id is not None)
        if self._selected_id is not None:
            preset = discount_presets_repo.get_preset(self._conn, self._selected_id)
            self._toggle_button.setText(
                ar.DISCOUNT_PRESETS_REACTIVATE_BUTTON if not preset["is_active"] else ar.DISCOUNT_PRESETS_DEACTIVATE_BUTTON
            )

    def _on_add(self) -> None:
        name = self._name_input.text().strip()
        if not name:
            self._message_label.setText(ar.DISCOUNT_PRESETS_ERROR_NAME_REQUIRED)
            return
        kind = self._kind_input.currentData()
        amount = self._amount_input.value() if kind == DISCOUNT_KIND_PERCENT else egp_to_piasters(self._amount_input.value())
        preset_id = discount_presets_repo.create_preset(self._conn, name, kind, amount)
        audit_service.log(
            self._conn, "discount_preset_changed", user=self._user, entity_type="discount_preset", entity_id=preset_id,
            summary_ar="إضافة خصم محفوظ: {0}".format(name),
        )
        self._name_input.clear()
        self._message_label.setText(ar.DISCOUNT_PRESETS_SAVED_MESSAGE)
        self.reload()

    def _on_toggle_active(self) -> None:
        if self._selected_id is None:
            return
        preset = discount_presets_repo.get_preset(self._conn, self._selected_id)
        discount_presets_repo.set_active(self._conn, self._selected_id, not preset["is_active"])
        audit_service.log(
            self._conn, "discount_preset_changed", user=self._user, entity_type="discount_preset", entity_id=self._selected_id,
            summary_ar="{0} خصم محفوظ: {1}".format("تعطيل" if preset["is_active"] else "تفعيل", preset["name"]),
        )
        self._message_label.setText(ar.DISCOUNT_PRESETS_SAVED_MESSAGE)
        self.reload()
