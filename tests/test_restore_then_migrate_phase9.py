"""End-to-end: a backup taken BEFORE Phase 9 (schema version 8) is
restored via the real restore_service flow, then the app's normal
startup migration path (migrate_with_pre_backup) must bring it up to
the Phase 9 schema with all prior data intact.
"""
from __future__ import annotations

from derby.app import migrate_with_pre_backup
from derby.core.db import orders_repo, settings_repo, tables_repo, users_repo
from derby.core.db.connection import connect
from derby.core.db.migrations import (
    MIGRATIONS,
    _migration_0001_initial,
    _migration_0002_menu,
    _migration_0003_cashier,
    _migration_0004_playstation,
    _migration_0005_expenses,
    _migration_0006_closing,
    _migration_0007_supplies,
    _migration_0008_order_label,
)
from derby.features.closing import restore_service


def _build_pre_phase9_backup(tmp_path):
    backup_path = tmp_path / "old_backup.db"
    conn = connect(backup_path)
    conn.execute("BEGIN")
    _migration_0001_initial(conn)
    _migration_0002_menu(conn)
    _migration_0003_cashier(conn)
    _migration_0004_playstation(conn)
    _migration_0005_expenses(conn)
    _migration_0006_closing(conn)
    _migration_0007_supplies(conn)
    _migration_0008_order_label(conn)
    conn.execute("PRAGMA user_version = 8")
    conn.commit()

    owner_id = users_repo.create_user(conn, "Owner", users_repo.ROLE_OWNER, "1234")
    table = tables_repo.list_tables(conn)[0]
    order_id = orders_repo.create_order(conn, table["id"], owner_id)
    conn.close()
    return backup_path, owner_id, order_id, table["id"]


def test_restoring_a_pre_phase9_backup_then_migrates_up_with_data_intact(tmp_path):
    app_data_dir = tmp_path / "appdata"
    app_data_dir.mkdir()
    primary_backup_dir = tmp_path / "backups"

    backup_path, owner_id, order_id, table_id = _build_pre_phase9_backup(tmp_path)

    from datetime import datetime, timezone

    marker = restore_service.stage_restore(backup_path, app_data_dir, primary_backup_dir, datetime.now(timezone.utc))
    assert marker.exists()

    result = restore_service.apply_pending_restore(app_data_dir)
    assert result["status"] == "ok"

    restored_db_path = app_data_dir / "derby.db"
    conn = connect(restored_db_path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 8

    settings_repo.ensure_defaults(conn)
    error = migrate_with_pre_backup(conn, restored_db_path)
    assert error is None
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)

    # Pre-Phase-9 data survived the restore + upgrade.
    order = orders_repo.get_order(conn, order_id)
    assert order is not None
    assert order["table_id"] == table_id

    # Phase 9 tables now exist and the owner can use them.
    tables_in_db = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"stock_items", "drawer_entries", "recipe_lines"}.issubset(tables_in_db)
    conn.close()
