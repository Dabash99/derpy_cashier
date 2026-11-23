"""A small reusable "stat tile": a label over a big number, styled as a
card. Used to replace a single long em-dash-separated summary line
(hard to read, and the first thing to overflow/clip at 1024px) with a
row of tiles that wraps naturally instead.
"""
from __future__ import annotations

from PySide2.QtCore import Qt
from PySide2.QtWidgets import QLabel, QVBoxLayout, QWidget

from derby.core.theme.fonts import latin_numeric_font
from derby.core.theme.styled import enable_styled_background


class StatTile(QWidget):
    def __init__(self, label_text: str, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setProperty("variant", "card")
        enable_styled_background(self)
        layout = QVBoxLayout(self)

        self._value_label = QLabel("")
        self._value_label.setProperty("role", "title")
        self._value_label.setFont(latin_numeric_font(18, bold=True))
        self._value_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._value_label)

        caption = QLabel(label_text)
        caption.setProperty("role", "subtitle")
        caption.setAlignment(Qt.AlignCenter)
        caption.setWordWrap(True)
        layout.addWidget(caption)

    def set_value(self, value_text: str, role: str = "title") -> None:
        """`role` lets a tile whose number IS a status (e.g. "آخر نسخة
        خارجية": سليمة/متأخرة/غير موجودة) recolor itself like any other
        QLabel[role=...] -- green/amber/red -- instead of always being
        plain title-colored; every numeric/money tile just keeps the
        default "title" role."""
        self._value_label.setText(value_text)
        if self._value_label.property("role") != role:
            self._value_label.setProperty("role", role)
            self._value_label.style().unpolish(self._value_label)
            self._value_label.style().polish(self._value_label)
