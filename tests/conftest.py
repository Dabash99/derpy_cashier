"""Shared pytest fixtures.

Every DB-touching test uses `db_conn`, a fresh file-backed SQLite
database inside pytest's own tmp_path — never the real %APPDATA%.
"""
from __future__ import annotations

import pytest
from PySide2.QtWidgets import QApplication

from derby.core.db import settings_repo
from derby.core.db.connection import connect
from derby.core.db.migrations import run_pending_migrations


@pytest.fixture()
def db_conn(tmp_path):
    conn = connect(tmp_path / "test_derby.db")
    run_pending_migrations(conn)
    settings_repo.ensure_defaults(conn)
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def qapp():
    """One QApplication for the whole test session (Qt forbids more than one)."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app
