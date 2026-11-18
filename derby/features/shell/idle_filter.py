"""Detects "no mouse/keyboard activity for N minutes" to trigger auto-lock.

Installed as an application-wide event filter so it sees activity
anywhere in the window, not just on one widget.
"""
from __future__ import annotations

from PySide2.QtCore import QEvent, QObject, QTimer, Signal

_ACTIVITY_EVENT_TYPES = (
    QEvent.MouseMove,
    QEvent.MouseButtonPress,
    QEvent.KeyPress,
    QEvent.Wheel,
    QEvent.TouchBegin,
)


class IdleTimer(QObject):
    idle_timeout = Signal()

    def __init__(self, timeout_minutes: int = 10, parent: QObject = None) -> None:
        super().__init__(parent)
        self._timeout_minutes = timeout_minutes
        self._elapsed_seconds = 0
        self._active = False
        self._check_timer = QTimer(self)
        self._check_timer.setInterval(1000)
        self._check_timer.timeout.connect(self._on_tick)

    def set_timeout_minutes(self, minutes: int) -> None:
        self._timeout_minutes = minutes

    def start(self) -> None:
        self._elapsed_seconds = 0
        self._active = True
        self._check_timer.start()

    def stop(self) -> None:
        self._active = False
        self._check_timer.stop()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt override)
        if self._active and event.type() in _ACTIVITY_EVENT_TYPES:
            self._elapsed_seconds = 0
        return False

    def _on_tick(self) -> None:
        if not self._active:
            return
        self._elapsed_seconds += 1
        if self._elapsed_seconds >= self._timeout_minutes * 60:
            self.stop()
            self.idle_timeout.emit()
