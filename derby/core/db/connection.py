"""Opens the single SQLite connection Derby uses for its database file.

WAL mode lets the UI thread read while a background update-check (or any
future worker) writes an audit row without locking the whole app, and
foreign_keys must be turned on explicitly per-connection in SQLite.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from derby.core.utils.paths import database_path


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path if db_path is not None else database_path()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
