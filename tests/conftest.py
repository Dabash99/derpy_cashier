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


@pytest.fixture(autouse=True)
def _never_touch_real_documents_folder(tmp_path, monkeypatch):
    """Safety net, on every single test: derby/core/utils/paths.py's
    default_backup_dir()/default_export_dir() read %USERPROFILE%, which
    this process does not otherwise sandbox -- a test that forgets to
    override a backup/export folder setting explicitly would silently
    write into the real Documents\\Derby folder. Redirect both to a
    per-test tmp_path instead, no matter what any individual test does.
    """
    fake_documents_derby = tmp_path / "fake_documents_derby"
    monkeypatch.setattr("derby.core.utils.paths.default_backup_dir", lambda: fake_documents_derby / "Backups")
    monkeypatch.setattr("derby.core.utils.paths.default_export_dir", lambda: fake_documents_derby / "Exports")
    monkeypatch.setattr("derby.core.db.settings_repo.default_backup_dir", lambda: fake_documents_derby / "Backups")


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
