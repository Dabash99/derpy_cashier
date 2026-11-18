"""Prevents two copies of Derby writing to the same SQLite file at once.

QLockFile is used (not a bare file + os.path.exists check) because it
handles stale locks left behind by a crashed process automatically.
"""
from __future__ import annotations

from PySide2.QtCore import QLockFile

from derby.core.utils.paths import lock_file_path

_STALE_LOCK_TIME_MS = 30_000


class SingleInstanceGuard:
    def __init__(self) -> None:
        self._lock_file = QLockFile(str(lock_file_path()))
        self._lock_file.setStaleLockTime(_STALE_LOCK_TIME_MS)

    def try_acquire(self) -> bool:
        return self._lock_file.tryLock(100)

    def release(self) -> None:
        self._lock_file.unlock()
