"""Mixin that keeps a data-showing screen fresh without a restart.

Every screen is built once in `MainWindow._build_screens()` and then
shown/hidden by the `QStackedWidget` as the sidebar is clicked -- it is
never rebuilt. Without this, a screen's `reload()` only ever ran once, at
construction, so anything created elsewhere (an order paid on another
screen, a PlayStation session stopped, a stock deduction) stayed
invisible until the app was closed and reopened.

A screen that mixes this in subscribes to `derby.core.events.bus` and
reloads right away if it is the one currently on screen, or otherwise
just remembers it is stale (`_dirty`) and reloads the moment it is shown
again (`showEvent`, which Qt fires for free when `QStackedWidget` switches
to it) -- a cheap safety net that also covers plain navigation to a
screen whose data changed while it was hidden.

Use for a screen that does NOT already define its own `showEvent`
(a few screens, such as the home dashboard, already refresh on every
show via their own timer-driven `showEvent` and don't need this).
"""
from __future__ import annotations

import sys

from derby.core.events import bus
from derby.core.utils import error_log


class RefreshOnChangeMixin:
    def _init_refresh_on_change(self) -> None:
        self._dirty = False
        bus.changed.connect(self._on_bus_changed)

    def _on_bus_changed(self) -> None:
        if self.isVisible():
            self._safe_reload()
        else:
            self._dirty = True

    def _safe_reload(self) -> None:
        try:
            self.reload()
        except Exception:
            error_log.log_exception(*sys.exc_info())

    def showEvent(self, event) -> None:  # noqa: N802 -- Qt override
        super().showEvent(event)
        if self._dirty:
            self._dirty = False
            self._safe_reload()
