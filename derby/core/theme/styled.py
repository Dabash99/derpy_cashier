"""Call `enable_styled_background` on every custom QWidget (not QFrame, see
below) container that paints its background/border via an #objectName or
variant="..." QSS selector -- for example #Sidebar, #Header, or a future
QWidget[variant="banner"].

Qt's stylesheet engine does not paint `background-color`/`border` on a
plain QWidget unless Qt.WA_StyledBackground is set; without it the widget
stays transparent and shows whatever its parent painted underneath, which
is how the sidebar/header ended up with cream text on a cream background
instead of the intended black fill. A QFrame with
`setFrameShape(QFrame.StyledPanel)` already paints correctly without this
(that is what the shape is for) and a top-level window (QMainWindow/
QDialog) also already paints correctly -- only non-window QWidget
containers need this call.
"""
from __future__ import annotations

from PySide2.QtCore import Qt
from PySide2.QtWidgets import QWidget


def enable_styled_background(widget: QWidget) -> None:
    widget.setAttribute(Qt.WA_StyledBackground, True)
