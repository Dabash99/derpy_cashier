"""The PlayStation screen: one card per device (state, live elapsed timer,
provisional price, flags) plus an owner-only device management tab.

A single shared 1-second QTimer drives all cards' live labels, and only
runs while at least one session is actually running -- kept light for a
weak PC, per the spec.
"""
from __future__ import annotations

import sqlite3

from PySide2.QtCore import QTimer, Signal
from PySide2.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from derby.core.db import orders_repo, ps_devices_repo, ps_sessions_repo
from derby.core.i18n import ar
from derby.core.utils.money import format_egp
from derby.features.auth import permissions
from derby.features.playstation import ps_service
from derby.features.playstation.ps_device_management_panel import PsDeviceManagementPanel
from derby.features.pos.exceptions import DeviceRateNotSetError, SessionRunningError
from derby.features.tables.move_order_dialog import MoveOrderDialog


class _DeviceCard(QFrame):
    order_opened = Signal(int)
    state_changed = Signal()

    def __init__(self, conn: sqlite3.Connection, device_id: int, user: sqlite3.Row, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self._conn = conn
        self._device_id = device_id
        self._user = user
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._name_label = QLabel("")
        self._name_label.setProperty("role", "title")
        layout.addWidget(self._name_label)
        self._state_label = QLabel("")
        layout.addWidget(self._state_label)
        self._elapsed_label = QLabel("")
        layout.addWidget(self._elapsed_label)
        self._price_label = QLabel("")
        layout.addWidget(self._price_label)
        self._flags_label = QLabel("")
        self._flags_label.setProperty("role", "error")
        layout.addWidget(self._flags_label)

        row1 = QHBoxLayout()
        self._start_single_button = QPushButton(ar.PS_START_SINGLE_BUTTON)
        self._start_single_button.clicked.connect(lambda: self._on_start(ps_service.MODE_SINGLE))
        row1.addWidget(self._start_single_button)
        self._start_multi_button = QPushButton(ar.PS_START_MULTI_BUTTON)
        self._start_multi_button.clicked.connect(lambda: self._on_start(ps_service.MODE_MULTI))
        row1.addWidget(self._start_multi_button)
        self._switch_button = QPushButton("")
        self._switch_button.clicked.connect(self._on_switch)
        row1.addWidget(self._switch_button)
        self._stop_button = QPushButton(ar.PS_STOP_BUTTON)
        self._stop_button.clicked.connect(self._on_stop)
        row1.addWidget(self._stop_button)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        self._open_invoice_button = QPushButton(ar.PS_OPEN_INVOICE_BUTTON)
        self._open_invoice_button.clicked.connect(self._on_open_invoice)
        row2.addWidget(self._open_invoice_button)
        self._move_button = QPushButton(ar.TABLES_MOVE_ORDER_BUTTON)
        self._move_button.clicked.connect(self._on_move)
        row2.addWidget(self._move_button)
        layout.addLayout(row2)

        self._error_label = QLabel("")
        self._error_label.setProperty("role", "error")
        self._error_label.setWordWrap(True)
        layout.addWidget(self._error_label)

    def has_running_session(self) -> bool:
        return ps_sessions_repo.get_running_session(self._conn, self._device_id) is not None

    def refresh(self) -> None:
        """Only sets text/visibility on the persistent widgets above -- no
        widget is ever created or destroyed here, so this is cheap enough
        to call once a second from the shared timer."""
        device = ps_devices_repo.get_device(self._conn, self._device_id)
        self._name_label.setText(device["name"])
        state = ps_service.current_state(self._conn, self._device_id)
        running = state["running_session"]
        order = state["order"]

        flags = []
        if state["is_long_session"]:
            flags.append(ar.PS_FLAG_LONG_SESSION)
        if state["is_previous_day"]:
            flags.append(ar.PS_FLAG_PREVIOUS_DAY)
        self._flags_label.setText(" | ".join(flags))

        if running is not None:
            mode_label = ar.PS_MODE_SINGLE_LABEL if running["mode"] == ps_service.MODE_SINGLE else ar.PS_MODE_MULTI_LABEL
            self._state_label.setText(ar.PS_STATE_RUNNING.format(mode=mode_label))
            total_seconds = state["elapsed_seconds"]
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            self._elapsed_label.setText(
                ar.PS_ELAPSED_LABEL.format(time="{0:02d}:{1:02d}:{2:02d}".format(hours, minutes, seconds))
            )
            self._price_label.setText(
                ar.PS_PROVISIONAL_PRICE_LABEL.format(price=format_egp(state["provisional_price_piasters"]))
            )
            self._switch_button.setText(
                ar.PS_SWITCH_TO_MULTI_BUTTON if running["mode"] == ps_service.MODE_SINGLE else ar.PS_SWITCH_TO_SINGLE_BUTTON
            )
            self._set_buttons_visible(start=False, switch=True, stop=True, open_invoice=True, move=False)
        elif order is not None:
            self._state_label.setText(ar.PS_STATE_STOPPED_WITH_ORDER)
            self._elapsed_label.setText("")
            self._price_label.setText("")
            self._set_buttons_visible(start=True, switch=False, stop=False, open_invoice=True, move=True)
        else:
            self._state_label.setText(ar.PS_STATE_FREE)
            self._elapsed_label.setText("")
            self._price_label.setText("")
            self._set_buttons_visible(start=True, switch=False, stop=False, open_invoice=False, move=False)

    def _set_buttons_visible(self, start: bool, switch: bool, stop: bool, open_invoice: bool, move: bool) -> None:
        self._start_single_button.setVisible(start)
        self._start_multi_button.setVisible(start)
        self._switch_button.setVisible(switch)
        self._stop_button.setVisible(stop)
        self._open_invoice_button.setVisible(open_invoice)
        self._move_button.setVisible(move)

    def _on_start(self, mode: str) -> None:
        self._error_label.setText("")
        try:
            ps_service.start_session(self._conn, self._device_id, mode, self._user["id"])
        except (DeviceRateNotSetError, SessionRunningError) as error:
            self._error_label.setText(str(error))
            return
        self.refresh()
        self.state_changed.emit()

    def _on_switch(self) -> None:
        self._error_label.setText("")
        running = ps_sessions_repo.get_running_session(self._conn, self._device_id)
        if running is None:
            return
        new_mode = ps_service.MODE_MULTI if running["mode"] == ps_service.MODE_SINGLE else ps_service.MODE_SINGLE
        try:
            ps_service.switch_mode(self._conn, self._device_id, new_mode, self._user["id"])
        except DeviceRateNotSetError as error:
            self._error_label.setText(str(error))
            return
        self.refresh()
        self.state_changed.emit()

    def _on_stop(self) -> None:
        ps_service.stop_session(self._conn, self._device_id, self._user["id"])
        self.refresh()
        self.state_changed.emit()

    def _on_open_invoice(self) -> None:
        order = orders_repo.get_open_order_for_device(self._conn, self._device_id)
        if order is not None:
            self.order_opened.emit(order["id"])

    def _on_move(self) -> None:
        order = orders_repo.get_open_order_for_device(self._conn, self._device_id)
        if order is None:
            return
        dialog = MoveOrderDialog(self._conn, order["id"], self._user, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self.refresh()
            self.state_changed.emit()


class PlaystationScreen(QWidget):
    order_opened = Signal(int)

    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._cards = {}

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel(ar.PS_TITLE)
        title.setProperty("role", "title")
        layout.addWidget(title)

        tabs = QTabWidget()
        tabs.addTab(self._build_grid_tab(), ar.PS_GRID_TAB)
        if permissions.manage_ps_devices(self._user["role"]):
            self._management_panel = PsDeviceManagementPanel(self._conn, self._user)
            self._management_panel.devices_changed.connect(self.reload)
            tabs.addTab(self._management_panel, ar.PS_MANAGE_TAB)
        layout.addWidget(tabs)

    def _build_grid_tab(self) -> QWidget:
        tab = QWidget()
        self._cards_layout = QHBoxLayout(tab)
        return tab

    def reload(self) -> None:
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards = {}
        for device in ps_devices_repo.list_devices(self._conn, active_only=True):
            card = _DeviceCard(self._conn, device["id"], self._user, parent=self)
            card.order_opened.connect(self.order_opened.emit)
            card.state_changed.connect(self._update_timer_state)
            self._cards[device["id"]] = card
            self._cards_layout.addWidget(card)
        self._cards_layout.addStretch(1)
        self._update_timer_state()

    def _tick(self) -> None:
        for card in self._cards.values():
            card.refresh()
        self._update_timer_state()

    def _update_timer_state(self) -> None:
        any_running = any(card.has_running_session() for card in self._cards.values())
        if any_running and not self._timer.isActive():
            self._timer.start()
        elif not any_running and self._timer.isActive():
            self._timer.stop()
