"""A light QPainter bar chart for "المبيعات حسب الساعة" -- no QtCharts,
no animation, per the hard constraints. RTL-aware: hour 0 is drawn at
the right (the reading-start side), hour 23 at the left, same mirroring
convention as every QHBoxLayout/QTableView in the app.
"""
from __future__ import annotations

from typing import List, Optional

from PySide2.QtCore import QRect, Qt
from PySide2.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent
from PySide2.QtWidgets import QToolTip, QWidget

from derby.core.theme import tokens
from derby.core.utils.money import format_egp

_BAR_COLOR = QColor(tokens.JET_BLACK)
_PEAK_COLOR = QColor(tokens.AMBER_500)
_AXIS_COLOR = QColor(tokens.BLACK_100)
_LABEL_EVERY = 3  # show an hour label every 3 bars, or every bar would overlap
_CHART_HEIGHT = 160
_LABEL_HEIGHT = 20


class HourlyBarChart(QWidget):
    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._values: List[int] = [0] * 24
        self.setMouseTracking(True)
        self.setMinimumHeight(_CHART_HEIGHT + _LABEL_HEIGHT)

    def set_values(self, values: List[int]) -> None:
        self._values = list(values) if values else [0] * 24
        self.update()

    def _bar_rect(self, visual_index: int) -> QRect:
        bar_count = 24
        chart_rect = QRect(0, 0, self.width(), _CHART_HEIGHT)
        bar_width = chart_rect.width() / bar_count
        max_value = max(self._values) or 1
        value = self._values[self._hour_for_visual_index(visual_index)]
        bar_height = int((value / max_value) * (_CHART_HEIGHT - 10))
        x = int(visual_index * bar_width)
        y = _CHART_HEIGHT - bar_height
        return QRect(x + 1, y, max(1, int(bar_width) - 2), bar_height)

    @staticmethod
    def _hour_for_visual_index(visual_index: int) -> int:
        # QPainter always draws left-to-right regardless of widget
        # layoutDirection -- visual_index 0 is the LEFTMOST drawn bar.
        # Mapping it to hour 23 (and visual_index 23 to hour 0) puts
        # hour 0 at the right, matching every other RTL-mirrored list
        # in the app (see module docstring).
        return 23 - visual_index

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 -- Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)  # light on weak PCs, no smoothing needed for flat bars

        painter.setPen(_AXIS_COLOR)
        painter.drawLine(0, _CHART_HEIGHT, self.width(), _CHART_HEIGHT)

        peak_value = max(self._values)
        peak_hour = self._values.index(peak_value) if peak_value > 0 else -1

        for visual_index in range(24):
            hour = self._hour_for_visual_index(visual_index)
            rect = self._bar_rect(visual_index)
            color = _PEAK_COLOR if hour == peak_hour else _BAR_COLOR
            painter.fillRect(rect, color)

            if hour % _LABEL_EVERY == 0:
                label_rect = QRect(rect.x() - 10, _CHART_HEIGHT + 2, rect.width() + 20, _LABEL_HEIGHT)
                painter.setPen(QColor(tokens.BLACK_500))
                painter.drawText(label_rect, Qt.AlignHCenter | Qt.AlignTop, "{0:02d}".format(hour))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 -- Qt override
        pos = event.pos()
        if 0 <= pos.y() <= _CHART_HEIGHT:
            bar_width = self.width() / 24
            visual_index = int(pos.x() // bar_width) if bar_width else -1
            if 0 <= visual_index < 24:
                hour = self._hour_for_visual_index(visual_index)
                value = self._values[hour]
                QToolTip.showText(
                    event.globalPos(), "{0:02d}:00 — {1}".format(hour, format_egp(value)), self
                )
                return
        QToolTip.hideText()

    def value_for_hour(self, hour: int) -> Optional[int]:
        if 0 <= hour < len(self._values):
            return self._values[hour]
        return None
