"""Top bar: cafe name, current user + role, and the manual lock button."""
from __future__ import annotations

from PySide2.QtCore import QSize, Signal
from PySide2.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from derby.core.db.users_repo import ROLE_OWNER
from derby.core.i18n import ar
from derby.core.theme import icons
from derby.core.theme.styled import enable_styled_background


class Header(QWidget):
    lock_requested = Signal()

    def __init__(self, cafe_name: str, user_name: str, role: str, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setObjectName("Header")
        enable_styled_background(self)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(10)

        logo_label = QLabel()
        logo_label.setPixmap(icons.icon_mark_pixmap("mono-white", 32))
        layout.addWidget(logo_label)

        self._cafe_name_label = QLabel(cafe_name)
        self._cafe_name_label.setProperty("role", "title")
        layout.addWidget(self._cafe_name_label)

        layout.addStretch(1)

        role_label = ar.HEADER_USER_ROLE_OWNER if role == ROLE_OWNER else ar.HEADER_USER_ROLE_CASHIER
        self._user_label = QLabel("{0} — {1}".format(user_name, role_label))
        self._user_label.setProperty("role", "subtitle")
        layout.addWidget(self._user_label)

        lock_button = QPushButton(ar.HEADER_LOCK_BUTTON)
        lock_button.setIcon(icons.icon("lock", variant="light"))
        lock_button.setIconSize(QSize(18, 18))
        lock_button.clicked.connect(self.lock_requested.emit)
        layout.addWidget(lock_button)
