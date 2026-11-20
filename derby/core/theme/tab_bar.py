"""Shared QTabWidget setup, fixing a real clipping bug: Qt's native tab
width calculation (and whatever internal margin its style reserves for
the selection indicator) leaves the first Arabic glyph touching -- and
sometimes past -- the tab's right edge under RTL, regardless of how
much horizontal QSS padding is declared. Reported symptom: "المصروفات"
rendering as "لمصروفات", the selected tab specifically no wider but
no better either.

The fix computes each tab's width ourselves, generously, from the real
font metrics -- not from whatever the style/stylesheet interaction
would otherwise produce -- so there is always slack left over even if
the native paint step eats a few pixels from one edge.

`configure_tab_widget()` must be called right after constructing the
QTabWidget and BEFORE any addTab() call: QTabWidget requires its tab
bar to be set before tabs are added.
"""
from __future__ import annotations

from PySide2.QtCore import QSize, Qt
from PySide2.QtGui import QFontMetrics
from PySide2.QtWidgets import QTabBar, QTabWidget

# Generous on purpose: this is slack against whatever the native style's
# own internal reservation eats, not a tight fit against the real text.
_HORIZONTAL_PADDING = 24
_MIN_HEIGHT = 44


class _MetricsTabBar(QTabBar):
    def tabSizeHint(self, index: int) -> QSize:
        metrics = QFontMetrics(self.font())
        text_width = metrics.horizontalAdvance(self.tabText(index))
        width = text_width + 2 * _HORIZONTAL_PADDING
        height = max(super().tabSizeHint(index).height(), _MIN_HEIGHT)
        return QSize(width, height)


def configure_tab_widget(tab_widget: QTabWidget) -> None:
    bar = _MetricsTabBar(tab_widget)
    bar.setElideMode(Qt.ElideNone)
    # Left at Qt's default (True): with generous per-tab width, six tabs
    # can legitimately not all fit at 1024px -- scrolling to the rest is
    # the right fallback, not squeezing/clipping them back down.
    bar.setExpanding(False)
    tab_widget.setTabBar(bar)
