"""Shows one closure's report text (read-only, selectable/copyable)."""
from __future__ import annotations

from PySide2.QtWidgets import QDialog, QPushButton, QTextEdit, QVBoxLayout

from derby.core.i18n import ar


class ClosingReportViewerDialog(QDialog):
    def __init__(self, report_text: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(ar.CLOSURES_VIEW_TEXT_BUTTON)
        layout = QVBoxLayout(self)

        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setPlainText(report_text)
        layout.addWidget(self._text_edit)

        close_button = QPushButton(ar.GENERIC_OK)
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)
