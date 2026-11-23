"""قائمة إعادة الطلب dialog, opened from المخزون (owner only)."""
from __future__ import annotations

import sqlite3

from PySide2.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QTableWidget, QVBoxLayout

from derby.core.db import settings_repo
from derby.core.i18n import ar
from derby.core.theme.table_style import centered_item, configure_table, right_item
from derby.features.inventory import reorder_service


class ReorderListDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self.setWindowTitle(ar.REORDER_LIST_TITLE)
        self.resize(640, 440)
        layout = QVBoxLayout(self)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            [
                ar.REORDER_LIST_COLUMN_SUPPLIER, ar.REORDER_LIST_COLUMN_ITEM, ar.REORDER_LIST_COLUMN_CURRENT,
                ar.REORDER_LIST_COLUMN_TARGET, ar.REORDER_LIST_COLUMN_SUGGESTED,
            ]
        )
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        configure_table(self._table, stretch_columns=(1,), fixed_widths={0: 110, 2: 80, 3: 80, 4: 110})
        layout.addWidget(self._table)

        self._empty_label = QLabel(ar.REORDER_LIST_EMPTY)
        self._empty_label.setVisible(False)
        layout.addWidget(self._empty_label)

        copy_button = QPushButton(ar.REORDER_LIST_COPY_BUTTON)
        copy_button.clicked.connect(self._on_copy)
        layout.addWidget(copy_button)

        self._message_label = QLabel("")
        layout.addWidget(self._message_label)

        self.reload()

    def reload(self) -> None:
        grouped = reorder_service.build_reorder_list(self._conn)
        rows = []
        for supplier_name, lines in grouped.items():
            for line in lines:
                rows.append((supplier_name, line))

        self._table.setRowCount(len(rows))
        for row_index, (supplier_name, line) in enumerate(rows):
            makers = [right_item, right_item, centered_item, centered_item, centered_item]
            values = [
                supplier_name,
                line.stock_item["name"],
                reorder_service.format_quantity(line.stock_item["current_qty"], line.stock_item["unit"]),
                reorder_service.format_quantity(line.target_qty, line.stock_item["unit"]),
                reorder_service.format_quantity(line.suggested_qty, line.stock_item["unit"]),
            ]
            for column, (value, make_item) in enumerate(zip(values, makers)):
                self._table.setItem(row_index, column, make_item(value))

        self._empty_label.setVisible(len(rows) == 0)

    def _on_copy(self) -> None:
        cafe_name = settings_repo.get(self._conn, "cafe_name", "") or "ديربي"
        text = reorder_service.build_plain_text(self._conn, cafe_name)
        QApplication.clipboard().setText(text)
        self._message_label.setText(ar.REORDER_LIST_COPIED_MESSAGE)
