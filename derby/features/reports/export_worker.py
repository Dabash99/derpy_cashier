"""Runs an export function on a background QThread so a slow PDF/Excel
write never freezes the UI. Shared by the Reports and Expenses screens.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide2.QtCore import QThread, Signal


class ExportWorker(QThread):
    finished_ok = Signal(str)  # the written file's path
    finished_error = Signal(str)  # a message to show the owner

    def __init__(self, export_fn: Callable[[], Path], parent=None) -> None:
        super().__init__(parent)
        self._export_fn = export_fn

    def run(self) -> None:
        try:
            result_path = self._export_fn()
        except Exception as error:  # noqa: BLE001 -- surfaced to the owner directly
            self.finished_error.emit(str(error))
            return
        self.finished_ok.emit(str(result_path))
