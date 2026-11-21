"""Dialogs opened from الخزنة: open the drawer, deposit/withdrawal, and
a physical count (with the optional denomination breakdown).
"""
from __future__ import annotations

import sqlite3

from PySide2.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout

from derby.core.i18n import ar
from derby.core.utils.money import format_egp, parse_egp_input
from derby.features.inventory import drawer_service
from derby.features.inventory.exceptions import InventoryError, NoteRequiredError

DENOMINATIONS_EGP = (200, 100, 50, 20, 10, 5, 1)


class OpenDrawerDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self.setWindowTitle(ar.DRAWER_OPEN_BUTTON)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)
        self._amount_input = QLineEdit("0")
        form.addRow(ar.DRAWER_OPENING_AMOUNT_LABEL, self._amount_input)
        self._error_label = QLabel("")
        self._error_label.setProperty("role", "error")
        layout.addWidget(self._error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(ar.DRAWER_OPEN_BUTTON)
        buttons.button(QDialogButtonBox.Cancel).setText(ar.GENERIC_CANCEL)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_save(self) -> None:
        try:
            amount = parse_egp_input(self._amount_input.text())
        except ValueError:
            self._error_label.setText(ar.DRAWER_ERROR_AMOUNT_INVALID)
            return
        drawer_service.open_drawer(self._conn, amount, self._user["id"])
        self.accept()


class _CashMovementDialog(QDialog):
    """Shared shape for deposit/withdrawal -- amount + required note."""

    def __init__(self, title: str, action, conn: sqlite3.Connection, user: sqlite3.Row, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._action = action
        self.setWindowTitle(title)
        self._build_ui(title)

    def _build_ui(self, button_text: str) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)
        self._amount_input = QLineEdit()
        form.addRow(ar.DRAWER_AMOUNT_LABEL, self._amount_input)
        self._note_input = QLineEdit()
        form.addRow(ar.DRAWER_NOTE_LABEL, self._note_input)
        self._error_label = QLabel("")
        self._error_label.setProperty("role", "error")
        layout.addWidget(self._error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(button_text)
        buttons.button(QDialogButtonBox.Cancel).setText(ar.GENERIC_CANCEL)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_save(self) -> None:
        try:
            amount = parse_egp_input(self._amount_input.text())
        except ValueError:
            self._error_label.setText(ar.DRAWER_ERROR_AMOUNT_INVALID)
            return
        try:
            self._action(self._conn, amount, self._note_input.text(), self._user["id"])
        except NoteRequiredError:
            self._error_label.setText(ar.DRAWER_ERROR_NOTE_REQUIRED)
            return
        except InventoryError:
            self._error_label.setText(ar.DRAWER_ERROR_AMOUNT_INVALID)
            return
        self.accept()


class DepositDialog(_CashMovementDialog):
    def __init__(self, conn, user, parent=None) -> None:
        super().__init__(ar.DRAWER_DEPOSIT_BUTTON, drawer_service.record_deposit, conn, user, parent)


class WithdrawalDialog(_CashMovementDialog):
    def __init__(self, conn, user, parent=None) -> None:
        super().__init__(ar.DRAWER_WITHDRAWAL_BUTTON, drawer_service.record_withdrawal, conn, user, parent)


class DrawerCountDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._denomination_inputs = {}
        self.setWindowTitle(ar.DRAWER_COUNT_DIALOG_TITLE)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        expected = drawer_service.expected_cash_piasters(self._conn) or 0
        layout.addWidget(QLabel(ar.DRAWER_EXPECTED_CASH_LABEL + ": " + format_egp(expected)))

        form = QFormLayout()
        layout.addLayout(form)
        for note in DENOMINATIONS_EGP:
            field = QLineEdit("0")
            field.textChanged.connect(self._recompute_from_denominations)
            form.addRow(str(note), field)
            self._denomination_inputs[note] = field

        self._counted_input = QLineEdit("0")
        form.addRow(ar.DRAWER_COUNT_COUNTED_LABEL, self._counted_input)

        self._result_label = QLabel("")
        layout.addWidget(self._result_label)
        self._error_label = QLabel("")
        self._error_label.setProperty("role", "error")
        layout.addWidget(self._error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(ar.DRAWER_COUNT_BUTTON)
        buttons.button(QDialogButtonBox.Cancel).setText(ar.GENERIC_CANCEL)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _denominations(self):
        counts = {}
        for note, field in self._denomination_inputs.items():
            text = field.text().strip()
            if text.isdigit():
                counts[str(note)] = int(text)
        return counts

    def _recompute_from_denominations(self) -> None:
        total_piasters = sum(note * count for note, count in ((n, self._as_int(f)) for n, f in self._denomination_inputs.items()))
        if total_piasters:
            self._counted_input.setText(str(total_piasters // 100))

    @staticmethod
    def _as_int(field: QLineEdit) -> int:
        text = field.text().strip()
        return int(text) if text.isdigit() else 0

    def _on_save(self) -> None:
        try:
            counted = parse_egp_input(self._counted_input.text())
        except ValueError:
            self._error_label.setText(ar.DRAWER_ERROR_AMOUNT_INVALID)
            return
        denominations = self._denominations()
        count = drawer_service.record_count(self._conn, counted, self._user["id"], denominations=denominations or None)
        if count["difference_piasters"] > 0:
            self._result_label.setText(ar.DRAWER_COUNT_RESULT_SURPLUS.format(amount=format_egp(count["difference_piasters"])))
        elif count["difference_piasters"] < 0:
            self._result_label.setText(ar.DRAWER_COUNT_RESULT_SHORTAGE.format(amount=format_egp(-count["difference_piasters"])))
        else:
            self._result_label.setText(ar.DRAWER_COUNT_RESULT_EXACT)
        self.accept()
