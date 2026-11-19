"""Settings must survive a full close + reopen of the database file,
exactly like a real app restart would."""
from __future__ import annotations

from derby.core.db import settings_repo
from derby.core.db.connection import connect
from derby.core.db.migrations import run_pending_migrations


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


def test_ensure_defaults_does_not_overwrite_an_explicitly_set_backup_folder(tmp_path):
    conn = connect(tmp_path / "fresh2.db")
    run_pending_migrations(conn)
    settings_repo.ensure_defaults(conn)
    settings_repo.set_value(conn, "backup_folder_primary", str(tmp_path / "chosen_by_owner"))

    settings_repo.ensure_defaults(conn)  # simulates a second app startup
    assert settings_repo.get(conn, "backup_folder_primary") == str(tmp_path / "chosen_by_owner")
    conn.close()
