"""Add/edit product dialog: name, price, image, active flag, addon groups.

Image changes are only written to disk when the dialog is actually saved
(Cancel leaves the filesystem untouched) -- we keep the chosen source path
in memory and run it through the real resize pipeline on save.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from PySide2.QtCore import Qt
from PySide2.QtGui import QPixmap
from PySide2.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from derby.core.db import addons_repo, audit_repo, categories_repo, products_repo
from derby.core.i18n import ar
from derby.core.utils.money import piasters_to_plain_text
from derby.features.menu import images
from derby.features.menu.price_parsing import parse_product_price

_IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.gif)"
_GROUP_ID_ROLE = 1000

_IMAGE_ACTION_KEEP = "keep"
_IMAGE_ACTION_SET = "set"
_IMAGE_ACTION_REMOVE = "remove"


class ProductDialog(QDialog):
    def __init__(
        self,
        conn: sqlite3.Connection,
        user_id: int,
        product_id: Optional[int] = None,
        default_category_id: Optional[int] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user_id = user_id
        self._product_id = product_id
        self._image_action = _IMAGE_ACTION_KEEP
        self._pending_image_source_path: Optional[Path] = None
        self._existing_image_file: Optional[str] = None

        self.setWindowTitle(
            ar.MENU_PRODUCT_DIALOG_EDIT_TITLE if product_id is not None else ar.MENU_PRODUCT_DIALOG_ADD_TITLE
        )
        self._build_ui()

        if product_id is not None:
            self._load_existing_product(product_id)
        elif default_category_id is not None:
            self._select_category(default_category_id)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self._category_input = QComboBox()
        for category in categories_repo.list_categories(self._conn):
            self._category_input.addItem(category["name"], category["id"])
        form.addRow(ar.MENU_PRODUCT_CATEGORY_LABEL, self._category_input)

        self._name_ar_input = QLineEdit()
        form.addRow(ar.MENU_PRODUCT_NAME_AR_LABEL, self._name_ar_input)

        self._name_en_input = QLineEdit()
        form.addRow(ar.MENU_PRODUCT_NAME_EN_LABEL, self._name_en_input)

        self._price_input = QLineEdit()
        form.addRow(ar.MENU_PRODUCT_PRICE_LABEL, self._price_input)

        image_row = QHBoxLayout()
        self._image_preview = QLabel()
        self._image_preview.setFixedSize(80, 80)
        self._image_preview.setAlignment(Qt.AlignCenter)
        self._image_preview.setStyleSheet("border: 1px solid #D0D4DA;")
        image_row.addWidget(self._image_preview)
        choose_button = QPushButton(ar.MENU_PRODUCT_IMAGE_CHOOSE_BUTTON)
        choose_button.clicked.connect(self._on_choose_image)
        image_row.addWidget(choose_button)
        remove_button = QPushButton(ar.MENU_PRODUCT_IMAGE_REMOVE_BUTTON)
        remove_button.clicked.connect(self._on_remove_image)
        image_row.addWidget(remove_button)
        form.addRow(ar.MENU_PRODUCT_IMAGE_LABEL, image_row)

        self._active_checkbox = QCheckBox(ar.MENU_PRODUCT_ACTIVE_CHECKBOX)
        self._active_checkbox.setChecked(True)
        form.addRow("", self._active_checkbox)

        layout.addWidget(QLabel(ar.MENU_PRODUCT_ADDON_GROUPS_LABEL))
        self._groups_list = QListWidget()
        for group in addons_repo.list_groups(self._conn):
            item = QListWidgetItem(group["name"])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            item.setData(_GROUP_ID_ROLE, group["id"])
            self._groups_list.addItem(item)
        layout.addWidget(self._groups_list)

        self._error_label = QLabel("")
        self._error_label.setProperty("role", "error")
        self._error_label.setWordWrap(True)
        layout.addWidget(self._error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(ar.GENERIC_SAVE)
        buttons.button(QDialogButtonBox.Cancel).setText(ar.GENERIC_CANCEL)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _select_category(self, category_id: int) -> None:
        index = self._category_input.findData(category_id)
        if index >= 0:
            self._category_input.setCurrentIndex(index)

    def _load_existing_product(self, product_id: int) -> None:
        product = products_repo.get_product(self._conn, product_id)
        self._select_category(product["category_id"])
        self._name_ar_input.setText(product["name_ar"])
        self._name_en_input.setText(product["name_en"] or "")
        self._price_input.setText(piasters_to_plain_text(product["price_piasters"]))
        self._active_checkbox.setChecked(bool(product["is_active"]))
        self._existing_image_file = product["image_file"]
        self._update_image_preview()

        attached_group_ids = set(addons_repo.get_product_group_ids(self._conn, product_id))
        for row in range(self._groups_list.count()):
            item = self._groups_list.item(row)
            if item.data(_GROUP_ID_ROLE) in attached_group_ids:
                item.setCheckState(Qt.Checked)

    def _update_image_preview(self) -> None:
        if self._image_action == _IMAGE_ACTION_SET and self._pending_image_source_path is not None:
            pixmap = QPixmap(str(self._pending_image_source_path))
        elif self._image_action == _IMAGE_ACTION_REMOVE:
            pixmap = QPixmap()
        elif self._existing_image_file:
            pixmap = images.load_thumbnail_pixmap(self._existing_image_file) or QPixmap()
        else:
            pixmap = QPixmap()

        if pixmap.isNull():
            self._image_preview.clear()
        else:
            self._image_preview.setPixmap(
                pixmap.scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )

    def _on_choose_image(self) -> None:
        file_path, _filter = QFileDialog.getOpenFileName(self, ar.MENU_PRODUCT_IMAGE_CHOOSE_BUTTON, "", _IMAGE_FILTER)
        if not file_path:
            return
        self._pending_image_source_path = Path(file_path)
        self._image_action = _IMAGE_ACTION_SET
        self._update_image_preview()

    def _on_remove_image(self) -> None:
        self._pending_image_source_path = None
        self._image_action = _IMAGE_ACTION_REMOVE
        self._update_image_preview()

    def _selected_group_ids(self):
        selected = []
        for row in range(self._groups_list.count()):
            item = self._groups_list.item(row)
            if item.checkState() == Qt.Checked:
                selected.append(item.data(_GROUP_ID_ROLE))
        return selected

    def _on_save(self) -> None:
        category_id = self._category_input.currentData()
        if category_id is None:
            self._error_label.setText(ar.MENU_PRODUCT_ERROR_CATEGORY_REQUIRED)
            return

        name_ar = self._name_ar_input.text().strip()
        if not name_ar:
            self._error_label.setText(ar.MENU_PRODUCT_ERROR_NAME_AR_REQUIRED)
            return
        if products_repo.is_name_duplicate(self._conn, category_id, name_ar, exclude_id=self._product_id):
            self._error_label.setText(ar.MENU_PRODUCT_ERROR_NAME_TAKEN)
            return

        try:
            price_piasters = parse_product_price(self._price_input.text())
        except ValueError:
            self._error_label.setText(ar.MENU_PRODUCT_ERROR_PRICE_INVALID)
            return

        try:
            image_file = self._resolve_image_file()
        except images.InvalidImageError:
            self._error_label.setText(ar.MENU_PRODUCT_ERROR_IMAGE_INVALID)
            return

        name_en = self._name_en_input.text().strip()
        is_active = self._active_checkbox.isChecked()
        old_price_piasters = None

        if self._product_id is None:
            self._product_id = products_repo.create_product(
                self._conn, category_id, name_ar, name_en, price_piasters, image_file=image_file
            )
        else:
            existing = products_repo.get_product(self._conn, self._product_id)
            old_price_piasters = existing["price_piasters"]
            products_repo.update_product(
                self._conn, self._product_id, category_id, name_ar, name_en, price_piasters, image_file, is_active
            )

        addons_repo.set_product_addon_groups(self._conn, self._product_id, self._selected_group_ids())

        if old_price_piasters is not None and old_price_piasters != price_piasters:
            audit_repo.log(
                self._conn,
                "product_price_changed",
                user_id=self._user_id,
                details="product_id={0} old={1} new={2}".format(
                    self._product_id, old_price_piasters, price_piasters
                ),
            )

        self.accept()

    def _resolve_image_file(self) -> Optional[str]:
        if self._image_action == _IMAGE_ACTION_SET and self._pending_image_source_path is not None:
            if self._existing_image_file:
                images.delete_product_image(self._existing_image_file)
            return images.save_product_image(self._pending_image_source_path)
        if self._image_action == _IMAGE_ACTION_REMOVE:
            if self._existing_image_file:
                images.delete_product_image(self._existing_image_file)
            return None
        return self._existing_image_file
