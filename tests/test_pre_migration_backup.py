"""Phase 8 safety net: migrating an EXISTING database must take a
verified backup first, and must NOT migrate at all if that backup
fails. A brand-new database (version 0) needs neither."""
from __future__ import annotations

from derby.app import migrate_with_pre_backup
from derby.core.db import settings_repo
from derby.core.db.connection import connect
from derby.core.db.migrations import (
    MIGRATIONS,
    _migration_0001_initial,
    _migration_0002_menu,
    _migration_0003_cashier,
    _migration_0004_playstation,
    _migration_0005_expenses,
)
from derby.features.closing import backup_service


def _db_at_version_5(tmp_path):
    db_path = tmp_path / "existing.db"
    conn = connect(db_path)
    conn.execute("BEGIN")
    _migration_0001_initial(conn)
    _migration_0002_menu(conn)
    _migration_0003_cashier(conn)
    _migration_0004_playstation(conn)
    _migration_0005_expenses(conn)
    conn.execute("PRAGMA user_version = 5")
    conn.commit()
    settings_repo.ensure_defaults(conn)
    settings_repo.set_value(conn, "backup_folder_primary", str(tmp_path / "primary_backups"))
    return conn, db_path


def test_successful_pre_migration_backup_then_migrates(tmp_path):
    conn, db_path = _db_at_version_5(tmp_path)

    error = migrate_with_pre_backup(conn, db_path)

    assert error is None
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    backups = list((tmp_path / "primary_backups").glob("derby-pre-migration-v5-to-v{0}-*.db".format(len(MIGRATIONS))))
    assert len(backups) == 1
    conn.close()


def test_failed_pre_migration_backup_aborts_the_migration(tmp_path, monkeypatch):
    conn, db_path = _db_at_version_5(tmp_path)

    def _boom(*args, **kwargs):
        raise backup_service.BackupError("فشل محاكى للاختبار")

    monkeypatch.setattr("derby.app.backup_service.verified_pre_migration_backup", _boom)

    error = migrate_with_pre_backup(conn, db_path)

    assert error is not None
    assert "فشل محاكى للاختبار" in error
    # Migration must NOT have run -- version is unchanged, data untouched.
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
    tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "day_closures" not in tables  # migration 6's table
    conn.close()


def test_brand_new_database_needs_no_backup_and_migrates_directly(tmp_path, monkeypatch):
    conn = connect(tmp_path / "fresh.db")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 0

    def _should_not_be_called(*args, **kwargs):
        raise AssertionError("a fresh database must never trigger a pre-migration backup")

    monkeypatch.setattr("derby.app.backup_service.verified_pre_migration_backup", _should_not_be_called)

    error = migrate_with_pre_backup(conn, tmp_path / "fresh.db")

    assert error is None
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    conn.close()


def test_already_up_to_date_database_needs_no_backup(tmp_path, monkeypatch):
    db_path = tmp_path / "current.db"
    conn = connect(db_path)
    migrate_with_pre_backup(conn, db_path)  # brings it fully up to date
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)

    def _should_not_be_called(*args, **kwargs):
        raise AssertionError("an already-current database must never trigger a pre-migration backup")

    monkeypatch.setattr("derby.app.backup_service.verified_pre_migration_backup", _should_not_be_called)

    error = migrate_with_pre_backup(conn, db_path)  # second "startup" against the same db
    assert error is None
    conn.close()
