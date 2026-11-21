"""The Home screen's "الطلبات المفتوحة" section: a responsive grid of
cards, one per currently open table/PlayStation/takeaway order, replacing
the old plain-text "الآن" block.

Refresh policy (per the Phase 10 UI spec): one lightweight DB query every
5 seconds (open_orders_service.list_open_order_cards, itself built on a
single orders_repo query plus one ps_service.current_state() call per
active device -- never per order), and a separate 1-second local timer
that only re-renders the already-fetched elapsed time on any running
PlayStation cards, with no DB access. Both timers start/stop with
showEvent/hideEvent so a hidden Home screen never polls.

A single failing card (e.g. a device row with incomplete data) is caught,
logged, and skipped -- this section must never crash the Home screen.
"""
from __future__ import annotations

import sys
import time
from typing import List, Optional

from PySide2.QtCore import Qt, QTimer, Signal
from PySide2.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from derby.core.i18n import ar
from derby.core.theme import tokens
from derby.core.theme.fonts import latin_numeric_font
from derby.core.theme.icons import icon, icon_mark_pixmap
from derby.core.theme.styled import enable_styled_background
from derby.core.utils import error_log
from derby.core.utils.money import format_egp
from derby.features.dashboard import open_orders_service
from derby.features.dashboard.open_orders_service import OpenOrderCard

_REFRESH_INTERVAL_MS = 5_000
_TICK_INTERVAL_MS = 1_000
_GRID_COLUMNS = 4

_KIND_ICON_NAME = {
    open_orders_service.KIND_TABLE: "tables",
    open_orders_service.KIND_PLAYSTATION: "playstation",
    open_orders_service.KIND_TAKEAWAY: "cashier",
}

FILTER_ALL = "all"
FILTER_TABLES = "tables"
FILTER_PLAYSTATION = "playstation"


def _format_elapsed(total_seconds: int) -> str:
    total_seconds = max(0, int(total_seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return "{0:02d}:{1:02d}:{2:02d}".format(hours, minutes, seconds)


class _OpenOrderCardWidget(QFrame):
    clicked = Signal(int)

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setProperty("variant", "openOrderCard")
        enable_styled_background(self)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumSize(200, 120)
        self._order_id: Optional[int] = None
        self._base_elapsed_seconds = 0
        self._base_monotonic: Optional[float] = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        header_row = QHBoxLayout()
        self._icon_label = QLabel()
        header_row.addWidget(self._icon_label)
        self._name_label = QLabel("")
        self._name_label.setProperty("role", "title")
        header_row.addWidget(self._name_label)
        header_row.addStretch(1)
        layout.addLayout(header_row)

        self._elapsed_label = QLabel("")
        self._elapsed_label.setFont(latin_numeric_font(tokens.FONT_SIZE_SUBTITLE, bold=True))
        layout.addWidget(self._elapsed_label)

        self._mode_label = QLabel("")
        self._mode_label.setProperty("variant", "badge")
        self._mode_label.setVisible(False)
        layout.addWidget(self._mode_label)

        self._total_label = QLabel("")
        layout.addWidget(self._total_label)

        self._items_label = QLabel("")
        self._items_label.setProperty("role", "subtitle")
        layout.addWidget(self._items_label)

        self._opened_by_label = QLabel("")
        self._opened_by_label.setProperty("role", "subtitle")
        self._opened_by_label.setVisible(False)
        layout.addWidget(self._opened_by_label)

    def set_data(self, card: OpenOrderCard) -> None:
        self._order_id = card.order_id
        self._icon_label.setPixmap(icon(_KIND_ICON_NAME.get(card.kind, "tables")).pixmap(20, 20))
        self._name_label.setText(card.name)

        self.setProperty("kind", card.kind)
        is_stale = card.elapsed_seconds >= open_orders_service.STALE_ORDER_THRESHOLD_SECONDS
        self.setProperty("stale", "true" if is_stale else "false")
        self.style().unpolish(self)
        self.style().polish(self)

        self._base_elapsed_seconds = card.elapsed_seconds
        self._base_monotonic = time.monotonic()
        self._render_elapsed()

        if card.ps_mode_label:
            self._mode_label.setText(card.ps_mode_label)
            self._mode_label.setVisible(True)
        else:
            self._mode_label.setVisible(False)

        total_text = format_egp(card.total_piasters)
        if card.is_estimated_total:
            total_text = ar.DASHBOARD_OPEN_ORDER_ESTIMATED_TOTAL.format(total=total_text)
        self._total_label.setText(total_text)

        self._items_label.setText(ar.DASHBOARD_OPEN_ORDER_ITEM_COUNT.format(count=card.item_count))

        if card.opened_by_name:
            self._opened_by_label.setText(ar.DASHBOARD_OPEN_ORDER_OPENED_BY.format(name=card.opened_by_name))
            self._opened_by_label.setVisible(True)
        else:
            self._opened_by_label.setVisible(False)

    def tick_local(self) -> None:
        self._render_elapsed()

    def _render_elapsed(self) -> None:
        extra = 0.0 if self._base_monotonic is None else (time.monotonic() - self._base_monotonic)
        self._elapsed_label.setText(_format_elapsed(self._base_elapsed_seconds + extra))

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 -- Qt override
        super().mouseReleaseEvent(event)
        if self._order_id is not None and self.rect().contains(event.pos()):
            self.clicked.emit(self._order_id)


class OpenOrdersPanel(QWidget):
    order_opened = Signal(int)

    def __init__(self, conn, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._filter = FILTER_ALL
        self._all_cards_data: List[OpenOrderCard] = []
        self._running_ps_widgets: List[_OpenOrderCardWidget] = []

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(_REFRESH_INTERVAL_MS)
        self._refresh_timer.timeout.connect(self.reload)
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(_TICK_INTERVAL_MS)
        self._tick_timer.timeout.connect(self._tick)

        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._header_label = QLabel("")
        self._header_label.setProperty("role", "subtitle")
        layout.addWidget(self._header_label)

        chips_row = QHBoxLayout()
        self._chip_buttons = {}
        for value, label_text in (
            (FILTER_ALL, ar.DASHBOARD_OPEN_ORDERS_FILTER_ALL),
            (FILTER_TABLES, ar.DASHBOARD_OPEN_ORDERS_FILTER_TABLES),
            (FILTER_PLAYSTATION, ar.DASHBOARD_OPEN_ORDERS_FILTER_PLAYSTATION),
        ):
            button = QPushButton(label_text)
            button.setProperty("variant", "chip")
            button.clicked.connect(lambda _checked=False, v=value: self._on_filter(v))
            chips_row.addWidget(button)
            self._chip_buttons[value] = button
        chips_row.addStretch(1)
        layout.addLayout(chips_row)
        self._update_chip_styles()

        self._grid_host = QWidget()
        self._grid_layout = QGridLayout(self._grid_host)
        layout.addWidget(self._grid_host)

        self._empty_container = QWidget()
        empty_layout = QVBoxLayout(self._empty_container)
        empty_icon = QLabel()
        empty_icon.setPixmap(icon_mark_pixmap("mono-black", 48))
        empty_icon.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_icon)
        empty_text = QLabel(ar.DASHBOARD_OPEN_ORDERS_EMPTY)
        empty_text.setAlignment(Qt.AlignCenter)
        empty_text.setProperty("role", "subtitle")
        empty_layout.addWidget(empty_text)
        layout.addWidget(self._empty_container)

    # --- live refresh ----------------------------------------------------

    def showEvent(self, event) -> None:  # noqa: N802 -- Qt override
        super().showEvent(event)
        self.reload()
        self._refresh_timer.start()
        self._update_tick_timer_state()

    def hideEvent(self, event) -> None:  # noqa: N802 -- Qt override
        super().hideEvent(event)
        self._refresh_timer.stop()
        self._tick_timer.stop()

    def _tick(self) -> None:
        for widget in self._running_ps_widgets:
            widget.tick_local()

    def _update_tick_timer_state(self) -> None:
        if self._running_ps_widgets and not self._tick_timer.isActive():
            self._tick_timer.start()
        elif not self._running_ps_widgets and self._tick_timer.isActive():
            self._tick_timer.stop()

    # --- filtering ---------------------------------------------------------

    def _on_filter(self, value: str) -> None:
        self._filter = value
        self._update_chip_styles()
        self._render()

    def _update_chip_styles(self) -> None:
        for value, button in self._chip_buttons.items():
            button.setProperty("selected", "true" if value == self._filter else "false")
            button.style().unpolish(button)
            button.style().polish(button)

    def _matches_filter(self, card: OpenOrderCard) -> bool:
        if self._filter == FILTER_TABLES:
            return card.kind == open_orders_service.KIND_TABLE
        if self._filter == FILTER_PLAYSTATION:
            return card.kind == open_orders_service.KIND_PLAYSTATION
        return True

    # --- rendering -----------------------------------------------------

    def reload(self) -> None:
        try:
            self._all_cards_data = open_orders_service.list_open_order_cards(self._conn)
        except Exception:
            error_log.log_exception(*sys.exc_info())
            self._all_cards_data = []
        self._render()

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

    def _render(self) -> None:
        filtered = [card for card in self._all_cards_data if self._matches_filter(card)]

        self._clear_layout(self._grid_layout)
        self._running_ps_widgets = []

        total_piasters = sum(card.total_piasters for card in filtered)
        self._header_label.setText(
            ar.DASHBOARD_OPEN_ORDERS_HEADER.format(count=len(filtered), total=format_egp(total_piasters))
        )

        is_empty = len(filtered) == 0
        self._empty_container.setVisible(is_empty)
        self._grid_host.setVisible(not is_empty)

        for index, card_data in enumerate(filtered):
            try:
                widget = _OpenOrderCardWidget()
                widget.set_data(card_data)
            except Exception:
                error_log.log_exception(*sys.exc_info())
                continue
            widget.clicked.connect(self.order_opened.emit)
            row, col = divmod(index, _GRID_COLUMNS)
            self._grid_layout.addWidget(widget, row, col)
            if card_data.is_estimated_total:
                self._running_ps_widgets.append(widget)

        self._update_tick_timer_state()
