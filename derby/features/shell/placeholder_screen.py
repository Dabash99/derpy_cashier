"""Generic "not built yet" screen for sidebar sections from later phases."""
from __future__ import annotations

from PySide2.QtCore import Qt
from PySide2.QtWidgets import QLabel, QVBoxLayout, QWidget

from derby.core.i18n import ar


class PlaceholderScreen(QWidget):
    def __init__(self, phase: int, parent: QWidget = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        label = QLabel(ar.PLACEHOLDER_COMING_SOON.format(phase=phase))
        label.setProperty("role", "subtitle")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
