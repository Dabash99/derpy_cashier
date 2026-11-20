"""DERBY_DATA_DIR / DERBY_DOCS_DIR let tests, tools/preview_screens.py,
--selftest, and build checks redirect every path paths.py computes,
without ever touching the real %APPDATA%\\Derby or Documents\\Derby."""
from __future__ import annotations

from derby.core.utils import paths


def test_derby_data_dir_override_redirects_app_data_dir(tmp_path, monkeypatch):
    sandbox = tmp_path / "sandboxed_appdata"
    monkeypatch.setenv("DERBY_DATA_DIR", str(sandbox))

    assert paths.app_data_dir() == sandbox
    assert paths.database_path() == sandbox / "derby.db"
    assert paths.lock_file_path() == sandbox / "derby.lock"
    assert sandbox.exists()


def test_derby_docs_dir_override_redirects_backup_and_export_dirs(tmp_path, monkeypatch):
    # default_backup_dir()/default_export_dir() themselves are patched by
    # conftest's autouse safety net on every test (belt-and-suspenders
    # against a real Documents\Derby leak); exercise the override via the
    # underlying _documents_derby_dir(), which is what they both delegate
    # to and what conftest leaves untouched.
    sandbox = tmp_path / "sandboxed_documents_derby"
    monkeypatch.setenv("DERBY_DOCS_DIR", str(sandbox))

    assert paths._documents_derby_dir() == sandbox


def test_overrides_take_priority_over_appdata_and_userprofile(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "real_looking_appdata"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "real_looking_userprofile"))
    data_sandbox = tmp_path / "data_override"
    docs_sandbox = tmp_path / "docs_override"
    monkeypatch.setenv("DERBY_DATA_DIR", str(data_sandbox))
    monkeypatch.setenv("DERBY_DOCS_DIR", str(docs_sandbox))

    assert paths.app_data_dir() == data_sandbox
    assert paths._documents_derby_dir() == docs_sandbox


def test_without_override_still_falls_back_to_appdata_and_userprofile(tmp_path, monkeypatch):
    monkeypatch.delenv("DERBY_DATA_DIR", raising=False)
    monkeypatch.delenv("DERBY_DOCS_DIR", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "fake_appdata"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "fake_userprofile"))

    assert paths.app_data_dir() == tmp_path / "fake_appdata" / "Derby"
    assert paths._documents_derby_dir() == tmp_path / "fake_userprofile" / "Documents" / "Derby"
