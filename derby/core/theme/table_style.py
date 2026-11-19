"""Shared setup for every QTableWidget in the app, so header clipping,
cramped rows, and RTL column/elision bugs get fixed once instead of once
per screen.

Qt's own defaults don't suit this app: new columns start at a fixed
~100px (too narrow for an Arabic header like "اسم بالعربي", which then
shows clipped), rows default to a ~30px size hint (well under the 44px
minimum touch target this app uses everywhere else), and nothing stops
`resizeColumnsToContents()` from leaving the name column far too narrow
while a status/price column has empty room.
"""
from __future__ import annotations

from typing import Dict, Iterable

from PySide2.QtCore import Qt
from PySide2.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem

from derby.core.theme import tokens


def configure_table(table: QTableWidget, stretch_columns: Iterable[int], fixed_widths: Dict[int, int] = None) -> None:
    """`stretch_columns` get the remaining space (name/description columns);
    every other column either gets a width from `fixed_widths` (image,
    status, price -- short, known content) or falls back to
    ResizeToContents. Call this once, right after the column headers are
    set, before any row is added."""
    fixed_widths = fixed_widths or {}
    table.verticalHeader().setDefaultSectionSize(tokens.CONTROL_HEIGHT_ROW)
    table.verticalHeader().setMinimumSectionSize(tokens.CONTROL_HEIGHT_ROW)
    table.verticalHeader().setVisible(False)
    # ElideRight is correct under RTL, not a bug to work around: it keeps
    # the start of the (logical) string and appends "…" at its end, which
    # renders at the visual LEFT -- the reading-end side for RTL text.
    table.setTextElideMode(Qt.ElideRight)

    header = table.horizontalHeader()
    header.setMinimumSectionSize(44)
    header.setDefaultAlignment(Qt.AlignRight | Qt.AlignVCenter)
    for column in range(table.columnCount()):
        if column in stretch_columns:
            header.setSectionResizeMode(column, QHeaderView.Stretch)
        elif column in fixed_widths:
            header.setSectionResizeMode(column, QHeaderView.Fixed)
            table.setColumnWidth(column, fixed_widths[column])
        else:
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)


def right_item(text: str) -> QTableWidgetItem:
    """A cell for Arabic text (names, notes, free text) -- right-aligned
    so it hugs the reading-start edge under RTL instead of Qt's plain-left
    default, which otherwise pins it to the wrong (left) edge of the cell."""
    item = QTableWidgetItem(text)
    item.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
    return item


def centered_item(text: str) -> QTableWidgetItem:
    """A cell for short, direction-neutral content (status, price, a
    badge) -- centered rather than hugging either edge."""
    item = QTableWidgetItem(text)
    item.setTextAlignment(int(Qt.AlignCenter))
    return item
