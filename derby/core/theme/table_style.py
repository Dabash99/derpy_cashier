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
from PySide2.QtGui import QBrush, QColor
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
    header.setMinimumHeight(40)
    header.setDefaultAlignment(Qt.AlignRight | Qt.AlignVCenter)
    for column in range(table.columnCount()):
        if column in stretch_columns:
            header.setSectionResizeMode(column, QHeaderView.Stretch)
        elif column in fixed_widths:
            header.setSectionResizeMode(column, QHeaderView.Fixed)
            table.setColumnWidth(column, fixed_widths[column])
        else:
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)


def fit_table_height(table: QTableWidget, max_rows: int = 12) -> None:
    """Sizes a table that sits inside a page that itself scrolls (a
    reports section, not the one big list that owns a whole screen):
    a plain QVBoxLayout never grows a QTableWidget to fit its rows, so
    once several such tables share a page taller than the window, Qt's
    layout engine squeezes every one of them down toward its
    (near-zero) minimum size hint instead -- headers only, tiny stray
    internal scroll arrows, no data visible. Call this once after
    configure_table() and again every time the row count changes.

    Height = header + up to max_rows rows + frame. At or under
    max_rows, the table's own vertical scrollbar is off (every row is
    already visible); beyond it, the table scrolls internally at a
    sensible capped height instead of pushing the rest of the page
    further down."""
    header_height = max(table.horizontalHeader().sizeHint().height(), 40)
    row_height = max(table.verticalHeader().defaultSectionSize(), tokens.CONTROL_HEIGHT_ROW)
    frame = 2 * table.frameWidth()
    row_count = table.rowCount()
    visible_rows = min(max(row_count, 1), max_rows)
    content_height = header_height + visible_rows * row_height + frame
    table.setFixedHeight(content_height)
    needs_scroll = row_count > max_rows
    table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded if needs_scroll else Qt.ScrollBarAlwaysOff)


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


def mark_as_danger(item: QTableWidgetItem) -> QTableWidgetItem:
    """Recolors a cell's text (a critical audit-log row, an overdue
    customer, ...) to the brand's danger color. QTableWidgetItem is NOT
    a QWidget/QObject -- it has no setProperty()/stylesheet [role=...]
    support, unlike every QLabel elsewhere in this app, so this sets the
    foreground brush directly instead. Returns the same item, so this
    can wrap a right_item(...)/centered_item(...) call inline."""
    item.setForeground(QBrush(QColor(tokens.DANGER)))
    return item
