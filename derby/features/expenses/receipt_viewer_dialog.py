"""Shows one receipt's full-size photo (not the thumbnail) in a dialog."""
from __future__ import annotations

from typing import Optional

from PySide2.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

from derby.core.i18n import ar
from derby.features.expenses import receipts


class ReceiptViewerDialog(QDialog):
    def __init__(self, receipt_file: Optional[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(ar.EXPENSE_RECEIPT_VIEWER_TITLE)
        layout = QVBoxLayout(self)

        pixmap = receipts.load_full_pixmap(receipt_file)
        if pixmap is None:
            layout.addWidget(QLabel(ar.EXPENSE_RECEIPT_NONE))
        else:
            image_label = QLabel()
            image_label.setPixmap(pixmap)
            layout.addWidget(image_label)

        close_button = QPushButton(ar.GENERIC_OK)
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)
