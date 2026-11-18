"""Shared pytest fixtures.

Every DB-touching test uses `db_conn`, a fresh file-backed SQLite
database inside pytest's own tmp_path — never the real %APPDATA%.
"""
from __future__ import annotations

import os

# Headless on purpose: pytest must never pop up a real window on the
# developer's desktop. "offscreen" is a real Qt platform plugin, not a
# mock, so widgets still render/layout/grab() exactly as they would
# on-screen.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide2.QtWidgets import QApplication  # noqa: E402

from derby.core.db import settings_repo  # noqa: E402
from derby.core.db.connection import connect  # noqa: E402
from derby.core.db.migrations import run_pending_migrations  # noqa: E402


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
