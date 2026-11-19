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

# Every module that does `from derby.core.utils.paths import
# default_backup_dir` (or default_export_dir) binds that name into its
# OWN namespace -- patching derby.core.utils.paths.default_backup_dir
# alone does NOT affect those already-bound references. Every such
# module must be patched individually, by its own dotted path.
_BACKUP_DIR_PATCH_TARGETS = (
    "derby.core.utils.paths.default_backup_dir",
    "derby.core.db.settings_repo.default_backup_dir",
    "derby.features.closing.closures_list_dialog.default_backup_dir",
    "derby.features.closing.restore_dialog.default_backup_dir",
)
_EXPORT_DIR_PATCH_TARGETS = (
    "derby.core.utils.paths.default_export_dir",
    "derby.features.reports.export_panel.default_export_dir",
)


@pytest.fixture(autouse=True)
def _never_touch_real_documents_folder(tmp_path, monkeypatch):
    """Safety net, on every single test: default_backup_dir()/
    default_export_dir() read %USERPROFILE%, which this process does not
    otherwise sandbox -- a test that forgets to override a backup/export
    folder setting explicitly would silently write into the real
    Documents\\Derby folder. Redirect every known call site to a
    per-test tmp_path instead, no matter what any individual test does.
    """
    fake_documents_derby = tmp_path / "fake_documents_derby"
    for target in _BACKUP_DIR_PATCH_TARGETS:
        monkeypatch.setattr(target, lambda: fake_documents_derby / "Backups")
    for target in _EXPORT_DIR_PATCH_TARGETS:
        monkeypatch.setattr(target, lambda: fake_documents_derby / "Exports")


@pytest.fixture(autouse=True)
def _never_touch_real_appdata_folder(tmp_path, monkeypatch):
    """Safety net, on every single test: paths.app_data_dir() reads
    DERBY_DATA_DIR (falling back to %APPDATA%) fresh on every call -- see
    its docstring -- so setting this one env var redirects every call
    site at once, no per-module patching needed (unlike
    default_backup_dir/default_export_dir above, which predate this
    override and still need it for modules that bound their own name)."""
    monkeypatch.setenv("DERBY_DATA_DIR", str(tmp_path / "fake_appdata_derby"))


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
