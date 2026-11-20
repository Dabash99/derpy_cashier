"""Runs a closing-service operation on its OWN sqlite3 connection, off
the UI thread -- the scheduler tick, the startup catch-up, and the
manual closure/backup buttons all go through this, same QThread pattern
as derby/features/reports/export_worker.py.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide2.QtCore import QThread, Signal

from derby.core.db.connection import connect


class ClosingWorker(QThread):
    finished_ok = Signal(object)
    finished_error = Signal(str)

    def __init__(self, db_path: Path, work_fn: Callable, parent=None) -> None:
        super().__init__(parent)
        self._db_path = db_path
        self._work_fn = work_fn

    def run(self) -> None:
        conn = connect(self._db_path)
        try:
            result = self._work_fn(conn)
        except Exception as error:  # noqa: BLE001 -- surfaced to the caller, never crashes the worker
            self.finished_error.emit(str(error))
            return
        finally:
            conn.close()
        self.finished_ok.emit(result)
