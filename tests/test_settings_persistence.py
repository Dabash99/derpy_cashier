"""Settings must survive a full close + reopen of the database file,
exactly like a real app restart would."""
from __future__ import annotations

from derby.core.db import settings_repo
from derby.core.db.connection import connect
from derby.core.db.migrations import run_pending_migrations
from derby.core.utils.time_utils import utc_now
from derby.features.closing import closing_service


def test_settings_persist_across_reconnect(tmp_path):
    db_path = tmp_path / "persist.db"

    conn = connect(db_path)
    run_pending_migrations(conn)
    settings_repo.ensure_defaults(conn)
    settings_repo.set_value(conn, "cafe_name", "Derby Menoufia")
    settings_repo.set_value(conn, "auto_lock_minutes", "15")
    conn.close()

    reconnected = connect(db_path)
    assert settings_repo.get(reconnected, "cafe_name") == "Derby Menoufia"
    assert settings_repo.get(reconnected, "auto_lock_minutes") == "15"
    reconnected.close()


def test_ensure_defaults_resolves_backup_folder_primary_lazily(tmp_path, monkeypatch):
    """Regression test: backup_folder_primary must never end up empty or
    stuck on a value computed before default_backup_dir() was
    monkeypatched -- see the "Fix: backup_folder_primary leaked into the
    real Documents\\Derby folder" commit."""
    sandboxed = tmp_path / "sandboxed_backups"
    monkeypatch.setattr("derby.core.db.settings_repo.default_backup_dir", lambda: sandboxed)

    conn = connect(tmp_path / "fresh.db")
    run_pending_migrations(conn)
    settings_repo.ensure_defaults(conn)

    assert settings_repo.get(conn, "backup_folder_primary") == str(sandboxed)
    conn.close()


def test_ensure_defaults_resolves_whatsapp_method_from_windows_version(tmp_path, monkeypatch):
    import sys
    import types

    monkeypatch.setattr(
        sys, "getwindowsversion", lambda: types.SimpleNamespace(major=6, minor=1), raising=False
    )

    conn = connect(tmp_path / "win7.db")
    run_pending_migrations(conn)
    settings_repo.ensure_defaults(conn)

    assert settings_repo.get(conn, "whatsapp_method") == "browser"
    conn.close()


def test_ensure_defaults_does_not_override_whatsapp_method_on_a_later_run(tmp_path, monkeypatch):
    """Only the very first ensure_defaults() may apply the Windows-version
    default; an owner who later changes whatsapp_method (or simply
    restarts the app) must never have it silently reset."""
    import sys
    import types

    conn = connect(tmp_path / "existing.db")
    run_pending_migrations(conn)
    settings_repo.ensure_defaults(conn)  # first run: not mocked, resolves to the real platform's default
    closing_service.ensure_first_run_date(conn, utc_now())  # same order app.py's main() calls these in
    settings_repo.set_value(conn, "whatsapp_method", "copy_only")

    monkeypatch.setattr(
        sys, "getwindowsversion", lambda: types.SimpleNamespace(major=6, minor=1), raising=False
    )
    settings_repo.ensure_defaults(conn)  # simulates a later app restart, now "on Windows 7"

    assert settings_repo.get(conn, "whatsapp_method") == "copy_only"
    conn.close()


def test_ensure_defaults_does_not_overwrite_an_explicitly_set_backup_folder(tmp_path):
    conn = connect(tmp_path / "fresh2.db")
    run_pending_migrations(conn)
    settings_repo.ensure_defaults(conn)
    settings_repo.set_value(conn, "backup_folder_primary", str(tmp_path / "chosen_by_owner"))

    settings_repo.ensure_defaults(conn)  # simulates a second app startup
    assert settings_repo.get(conn, "backup_folder_primary") == str(tmp_path / "chosen_by_owner")
    conn.close()
