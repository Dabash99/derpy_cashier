"""Left-hand side of the cashier screen: the cart. Rebuilt from the DB on
every reload() (same simple pattern as the rest of the app) since a
cashier's cart realistically has a handful of lines, not hundreds.
"""
from __future__ import annotations

import sqlite3

from PySide2.QtCore import QTimer, Signal
from PySide2.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from derby.core.db import orders_repo, ps_sessions_repo, users_repo
from derby.core.i18n import ar
from derby.core.theme.fonts import latin_numeric_font
from derby.core.utils.money import format_egp
from derby.features.playstation import ps_service
from derby.features.pos import orders_service
from derby.features.pos.exceptions import (
    ApprovalLockedOutError,
    QuantityOutOfRangeError,
    WrongApprovalPinError,
)
from derby.features.pos.owner_pin_prompt import ask_for_owner_pin


class CartPanel(QWidget):
    discount_requested = Signal()
    changed = Signal()  # fires after any successful cart mutation
    pay_allowed_changed = Signal(bool)  # the Cashier screen's top bar "دفع" button follows this

    def __init__(self, conn: sqlite3.Connection, order_id: int, user: sqlite3.Row, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._order_id = order_id
        self._user = user
        self._pay_allowed = True
        self._provisional_session_id = None
        self._provisional_timer = QTimer(self)
        self._provisional_timer.setInterval(1000)
        self._provisional_timer.timeout.connect(self._update_provisional_label)
        self._build_ui()
        self.reload()

    def set_order(self, order_id: int) -> None:
        self._order_id = order_id
        self.reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        title = QLabel(ar.POS_CART_TITLE)
        title.setProperty("role", "title")
        layout.addWidget(title)

        self._provisional_label = QLabel("")
        self._provisional_label.setVisible(False)
        layout.addWidget(self._provisional_label)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        self._lines_host = QWidget()
        self._lines_layout = QVBoxLayout(self._lines_host)
        scroll_area.setWidget(self._lines_host)
        layout.addWidget(scroll_area)

        self._subtotal_label = QLabel("")
        layout.addWidget(self._subtotal_label)
        self._discount_label = QLabel("")
        layout.addWidget(self._discount_label)
        self._total_label = QLabel("")
        self._total_label.setProperty("role", "title")
        self._total_label.setFont(latin_numeric_font())
        layout.addWidget(self._total_label)

        self._pay_hint_label = QLabel("")
        self._pay_hint_label.setProperty("role", "error")
        self._pay_hint_label.setVisible(False)
        layout.addWidget(self._pay_hint_label)

        # Pay/cancel live in the Cashier screen's top bar (clearer, always
        # visible without scrolling the cart) -- this row only keeps the
        # discount action, which is specific to the cart contents.
        buttons_row = QHBoxLayout()
        discount_button = QPushButton(ar.POS_DISCOUNT_BUTTON)
        discount_button.clicked.connect(self.discount_requested.emit)
        buttons_row.addWidget(discount_button)
        layout.addLayout(buttons_row)

    def reload(self) -> None:
        while self._lines_layout.count():
            item = self._lines_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        order = orders_repo.get_order(self._conn, self._order_id)
        if order is None:
            # No order chosen yet (e.g. the chooser page hasn't handed off
            # to a table/takeaway order) -- show an empty cart, not a crash.
            self._lines_layout.addWidget(QLabel(ar.POS_EMPTY_CART))
            self._lines_layout.addStretch(1)
            self._subtotal_label.setText("")
            self._discount_label.setText("")
            self._total_label.setText("")
            self._set_running_session(None)
            return

        running_session = None
        if order["device_id"]:
            running_session = ps_sessions_repo.get_running_session(self._conn, order["device_id"])
        self._set_running_session(running_session)

        items = orders_repo.list_order_items(self._conn, self._order_id)
        if not items:
            self._lines_layout.addWidget(QLabel(ar.POS_EMPTY_CART))
        for item in items:
            self._lines_layout.addWidget(self._build_line_widget(item))
        self._lines_layout.addStretch(1)

        self._subtotal_label.setText("{0}: {1}".format(ar.POS_SUBTOTAL_LABEL, format_egp(order["subtotal_piasters"])))
        self._discount_label.setText("{0}: {1}".format(ar.POS_DISCOUNT_LABEL, format_egp(order["discount_piasters"])))
        self._total_label.setText("{0}: {1}".format(ar.POS_TOTAL_LABEL, format_egp(order["total_piasters"])))

    def pay_allowed(self) -> bool:
        """Whether the Cashier screen's top-bar "دفع" button should be
        enabled -- false while a PlayStation session is still running on
        this order (its total isn't final yet)."""
        return self._pay_allowed

    def _set_running_session(self, running_session) -> None:
        self._provisional_session_id = running_session["id"] if running_session is not None else None
        self._pay_allowed = running_session is None
        self.pay_allowed_changed.emit(self._pay_allowed)
        if running_session is not None:
            self._pay_hint_label.setText(ar.POS_PS_SESSION_RUNNING_HINT)
            self._pay_hint_label.setVisible(True)
            self._provisional_label.setVisible(True)
            self._update_provisional_label()
            self._provisional_timer.start()
        else:
            self._pay_hint_label.setVisible(False)
            self._provisional_label.setVisible(False)
            self._provisional_timer.stop()

    def _update_provisional_label(self) -> None:
        if self._provisional_session_id is None:
            return
        session = ps_sessions_repo.get_session(self._conn, self._provisional_session_id)
        if session is None or session["stopped_at_utc"] is not None:
            self._set_running_session(None)
            return
        state = ps_service.current_state(self._conn, session["device_id"])
        mode_label = ar.PS_MODE_SINGLE_LABEL if session["mode"] == ps_service.MODE_SINGLE else ar.PS_MODE_MULTI_LABEL
        self._provisional_label.setText(
            ar.POS_PS_PROVISIONAL_LINE.format(
                device=session["device_name_snapshot"], mode=mode_label, price=format_egp(state["provisional_price_piasters"])
            )
        )

    def _build_line_widget(self, item: sqlite3.Row) -> QWidget:
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        outer = QVBoxLayout(frame)

        row = QHBoxLayout()
        name_label = QLabel("{0} — {1}".format(item["name_snapshot"], format_egp(item["line_total_piasters"])))
        row.addWidget(name_label)

        is_ps_line = item["kind"] == "ps_time"
        if not is_ps_line:
            minus_button = QPushButton("−")
            minus_button.setFixedWidth(36)
            minus_button.clicked.connect(lambda: self._on_change_qty(item["id"], item["qty"] - 1))
            row.addWidget(minus_button)

            qty_label = QLabel(str(item["qty"]))
            row.addWidget(qty_label)

            plus_button = QPushButton("+")
            plus_button.setFixedWidth(36)
            plus_button.clicked.connect(lambda: self._on_change_qty(item["id"], item["qty"] + 1))
            row.addWidget(plus_button)

            note_button = QPushButton(ar.POS_NOTE_BUTTON)
            note_button.clicked.connect(lambda: self._on_edit_note(item["id"], item["note"] or ""))
            row.addWidget(note_button)

        remove_button = QPushButton(ar.POS_REMOVE_ITEM_BUTTON)
        if is_ps_line:
            remove_button.clicked.connect(lambda: self._on_remove_ps_item(item["id"]))
        else:
            remove_button.clicked.connect(lambda: self._on_remove_item(item["id"]))
        row.addWidget(remove_button)

        outer.addLayout(row)

        for addon in orders_repo.list_item_addons(self._conn, item["id"]):
            outer.addWidget(QLabel("+ {0}".format(addon["name_snapshot"])))
        if item["note"]:
            outer.addWidget(QLabel(item["note"]))

        return frame

    def _on_change_qty(self, item_id: int, new_qty: int) -> None:
        if new_qty < 1:
            self._on_remove_item(item_id)
            return
        try:
            orders_service.change_qty(self._conn, self._order_id, item_id, new_qty)
        except QuantityOutOfRangeError:
            return
        self.reload()
        self.changed.emit()

    def _on_remove_item(self, item_id: int) -> None:
        orders_service.remove_item(self._conn, self._order_id, item_id)
        self.reload()
        self.changed.emit()

    def _on_remove_ps_item(self, item_id: int) -> None:
        confirmed = QMessageBox.question(
            self, ar.POS_REMOVE_PS_LINE_CONFIRM_TITLE, ar.POS_REMOVE_PS_LINE_CONFIRM_MESSAGE
        )
        if confirmed != QMessageBox.Yes:
            return
        approving_pin = None
        if self._user["role"] != users_repo.ROLE_OWNER:
            approving_pin = ask_for_owner_pin(self)
            if approving_pin is None:
                return
        try:
            orders_service.remove_ps_item(self._conn, self._order_id, item_id, self._user, approving_pin=approving_pin)
        except WrongApprovalPinError:
            QMessageBox.warning(self, ar.GENERIC_ERROR_TITLE, ar.DISCOUNT_ERROR_WRONG_PIN)
            return
        except ApprovalLockedOutError:
            QMessageBox.warning(self, ar.GENERIC_ERROR_TITLE, ar.LOGIN_ERROR_LOCKED.format(minutes=0, seconds=0))
            return
        self.reload()
        self.changed.emit()

    def _on_edit_note(self, item_id: int, current_note: str) -> None:
        text, confirmed = QInputDialog.getText(
            self, ar.POS_NOTE_DIALOG_TITLE, ar.POS_NOTE_DIALOG_TITLE, QLineEdit.Normal, current_note
        )
        if not confirmed:
            return
        orders_service.set_item_note(self._conn, self._order_id, item_id, text)
        self.reload()
        self.changed.emit()
