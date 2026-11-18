"""A tiny reusable "enter the owner's PIN" dialog, used wherever a cashier
needs owner approval (discount dialog has its own inline field; this one
is for one-off prompts like cancelling a non-empty order)."""
from __future__ import annotations

from typing import Optional

from PySide2.QtWidgets import QDialog, QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout

from derby.core.i18n import ar


class OwnerPinPrompt(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(ar.DISCOUNT_OWNER_PIN_LABEL)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(ar.DISCOUNT_OWNER_PIN_LABEL))

        self._pin_input = QLineEdit()
        self._pin_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self._pin_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def pin(self) -> str:
        return self._pin_input.text()


def ask_for_owner_pin(parent=None) -> Optional[str]:
    dialog = OwnerPinPrompt(parent)
    if dialog.exec_() == QDialog.Accepted:
        return dialog.pin()
    return None
