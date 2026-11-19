"""configure_table() is the one place every QTableWidget in the app gets
its column sizing, row height, and RTL text elision from -- see item C
of the UI fix pass (narrow fixed columns clipped headers, no stretch on
the name column, default ~30px rows)."""
from __future__ import annotations

from PySide2.QtCore import Qt
from PySide2.QtWidgets import QHeaderView, QTableWidget

from derby.core.theme import tokens
from derby.core.theme.table_style import centered_item, configure_table, right_item


def test_configure_table_sets_row_height_and_elide_mode(qapp):
    table = QTableWidget(0, 3)
    configure_table(table, stretch_columns=(0,))

    assert table.verticalHeader().defaultSectionSize() == tokens.CONTROL_HEIGHT_ROW
    assert table.verticalHeader().defaultSectionSize() >= 44
    assert table.textElideMode() == Qt.ElideRight


def test_configure_table_applies_stretch_and_fixed_resize_modes(qapp):
    table = QTableWidget(0, 4)
    configure_table(table, stretch_columns=(1,), fixed_widths={0: 64, 2: 90})

    header = table.horizontalHeader()
    assert header.sectionResizeMode(0) == QHeaderView.Fixed
    assert table.columnWidth(0) == 64
    assert header.sectionResizeMode(1) == QHeaderView.Stretch
    assert header.sectionResizeMode(2) == QHeaderView.Fixed
    assert table.columnWidth(2) == 90
    assert header.sectionResizeMode(3) == QHeaderView.ResizeToContents


def test_right_item_and_centered_item_set_alignment(qapp):
    right = right_item("اسم")
    assert int(right.textAlignment()) & Qt.AlignRight

    centered = centered_item("10.00")
    assert int(centered.textAlignment()) & Qt.AlignHCenter
