"""Drives the real ClosuresListDialog -- db_path is always a temp file
passed in explicitly, never the real %APPDATA%."""
from __future__ import annotations

from derby.core.db import day_closures_repo, users_repo
from derby.features.closing.closures_list_dialog import ClosuresListDialog


def test_lists_closures_with_backup_and_sent_status(qapp, db_conn, tmp_path):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    day_closures_repo.create_closure(db_conn, "2026-01-10", "auto", "نص", 3, 5000, 0, 5000, 0, 0)

    dialog = ClosuresListDialog(db_conn, users_repo.get_user(db_conn, owner_id), tmp_path / "test_derby.db")
    assert dialog._table.rowCount() == 1
    assert dialog._table.item(0, 0).text() == "2026-01-10"
    assert "في الانتظار" in dialog._table.item(0, 4).text()


def test_mark_sent_updates_status(qapp, db_conn, tmp_path):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    day_closures_repo.create_closure(db_conn, "2026-01-10", "auto", "نص", 3, 5000, 0, 5000, 0, 0)

    dialog = ClosuresListDialog(db_conn, users_repo.get_user(db_conn, owner_id), tmp_path / "test_derby.db")
    dialog._table.selectRow(0)
    dialog._on_mark_sent()
    assert "تم الإرسال" in dialog._table.item(0, 4).text()


def test_rebuild_increments_revision(qapp, db_conn, tmp_path):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    closure_id = day_closures_repo.create_closure(db_conn, "2026-01-10", "auto", "نص", 3, 5000, 0, 5000, 0, 0)

    dialog = ClosuresListDialog(db_conn, users_repo.get_user(db_conn, owner_id), tmp_path / "test_derby.db")
    dialog._table.selectRow(0)
    dialog._on_rebuild()

    reloaded = day_closures_repo.get_closure(db_conn, closure_id)
    assert reloaded["revision"] == 2
