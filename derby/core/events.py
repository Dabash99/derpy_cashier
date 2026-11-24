"""Central "data changed" notification bus.

Services call `events.bus.notify()` once a write has actually committed
(order paid/voided/moved, a PlayStation session started/stopped, a stock
movement, a drawer entry, an expense, ...). Screens connect to
`events.bus.changed` and either refresh immediately (if visible) or mark
themselves dirty and refresh in `showEvent` -- see
`derby/core/utils/screen_refresh.py`.

Bursts of several notify() calls inside one user action (e.g. pay() which
touches orders, stock and the drawer) collapse into a single `changed`
emission after a short idle window, so a screen's reload() runs once, not
three times.
"""
from __future__ import annotations

from PySide2.QtCore import QObject, QTimer, Signal

_DEBOUNCE_MS = 200


class _DataEventBus(QObject):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(_DEBOUNCE_MS)
        self._timer.timeout.connect(self.changed.emit)

    def notify(self) -> None:
        self._timer.start()


bus = _DataEventBus()
