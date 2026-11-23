from __future__ import annotations

from datetime import date

from derby.core.db import users_repo
from derby.features.closing import closing_service
from derby.features.closing.backups_list_dialog import BackupsListDialog


def test_dialog_lists_backup_rows_with_version_columns(qapp, db_conn, tmp_path):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    primary_dir = tmp_path / "primary"
    db_path = tmp_path / "test_derby.db"
    closing_service.close_or_rebuild_day(db_conn, db_path, date(2026, 1, 1), "auto", "ديربي", primary_dir, None, 30, date(2026, 1, 1))

    dialog = BackupsListDialog(db_conn, owner)
    assert dialog._table.rowCount() >= 1
    assert dialog._rows_by_index[0]["app_version"]


def test_cleanup_button_applies_retention_and_logs_audit(qapp, db_conn, tmp_path, monkeypatch):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    from PySide2.QtWidgets import QMessageBox

    from derby.core.db import settings_repo

    primary_dir = tmp_path / "primary"
    primary_dir.mkdir()
    for day in range(1, 40):
        (primary_dir / "derby-2026-01-{0:02d}.db".format(day % 28 + 1)).write_text("x")
    settings_repo.set_value(db_conn, "backup_folder_primary", str(primary_dir))
    settings_repo.set_value(db_conn, "backup_keep_count", "5")

    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))

    dialog = BackupsListDialog(db_conn, owner)
    dialog._on_cleanup()

    row = db_conn.execute("SELECT * FROM audit_log WHERE action = 'backup_retention_cleanup'").fetchone()
    assert row is not None
