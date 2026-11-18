"""Shown before a product with attached addon groups is added to the cart.
Groups with max_select == 1 render as radio buttons (visually enforcing
"pick one"); anything else renders as checkboxes.
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from PySide2.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QRadioButton,
    QVBoxLayout,
)

from derby.core.db import addons_repo
from derby.core.i18n import ar
from derby.core.utils.money import format_egp
from derby.features.pos.addon_selection import validate_and_snapshot_addons
from derby.features.pos.exceptions import AddonSelectionError


class AddonDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, product_id: int, product_name: str, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._product_id = product_id
        self._checkboxes: List[QCheckBox] = []
        self._selected_addon_ids: Optional[List[int]] = None

        self.setWindowTitle("{0} — {1}".format(ar.ADDON_DIALOG_TITLE, product_name))
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        group_ids = addons_repo.get_product_group_ids(self._conn, self._product_id)
        for group_id in group_ids:
            group = addons_repo.get_group(self._conn, group_id)
            if group is None or not group["is_active"]:
                continue
            layout.addWidget(QLabel(group["name"]))

            addons = addons_repo.list_addons(self._conn, group_id, active_only=True)
            is_single_choice = group["max_select"] == 1
            button_group = QButtonGroup(self) if is_single_choice else None

            for addon in addons:
                label = "{0} (+{1})".format(addon["name"], format_egp(addon["price_delta_piasters"]))
                checkbox = QRadioButton(label) if is_single_choice else QCheckBox(label)
                checkbox.setProperty("addon_id", addon["id"])
                layout.addWidget(checkbox)
                self._checkboxes.append(checkbox)
                if button_group is not None:
                    button_group.addButton(checkbox)

        self._error_label = QLabel("")
        self._error_label.setProperty("role", "error")
        self._error_label.setWordWrap(True)
        layout.addWidget(self._error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(ar.ADDON_DIALOG_CONFIRM_BUTTON)
        buttons.accepted.connect(self._on_confirm)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_confirm(self) -> None:
        selected_ids = [
            checkbox.property("addon_id") for checkbox in self._checkboxes if checkbox.isChecked()
        ]
        try:
            validate_and_snapshot_addons(self._conn, self._product_id, selected_ids)
        except AddonSelectionError:
            self._error_label.setText(ar.ADDON_DIALOG_ERROR_SELECTION)
            return
        self._selected_addon_ids = selected_ids
        self.accept()

    def selected_addon_ids(self) -> List[int]:
        return self._selected_addon_ids or []
