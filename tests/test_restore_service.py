from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from derby.core.db import users_repo
from derby.core.db.connection import connect
from derby.core.db.migrations import MIGRATIONS, run_pending_migrations
from derby.features.closing import backup_service, restore_service


def _make_db(path):
    conn = connect(path)
    run_pending_migrations(conn)
    return conn


def test_validate_backup_file_accepts_a_good_backup(tmp_path):
    db_path = tmp_path / "derby.db"
    conn = _make_db(db_path)
    conn.close()
    backup_path = tmp_path / "backup.db"
    backup_service.backup_to_file(db_path, backup_path)

    restore_service.validate_backup_file(backup_path)  # must not raise


def test_validate_backup_file_rejects_corrupted(tmp_path):
    bogus = tmp_path / "bogus.db"
    bogus.write_bytes(b"not a database")
    with pytest.raises(restore_service.RestoreValidationError):
        restore_service.validate_backup_file(bogus)


def test_validate_backup_file_rejects_missing_file(tmp_path):
    with pytest.raises(restore_service.RestoreValidationError):
        restore_service.validate_backup_file(tmp_path / "does_not_exist.db")


def test_validate_backup_file_rejects_newer_schema(tmp_path):
    db_path = tmp_path / "newer.db"
    conn = _make_db(db_path)
    conn.execute("PRAGMA user_version = {0}".format(len(MIGRATIONS) + 1))
    conn.close()
    with pytest.raises(restore_service.RestoreValidationError):
        restore_service.validate_backup_file(db_path)


def test_validate_backup_file_rejects_missing_expected_tables(tmp_path):
    bare_path = tmp_path / "bare.db"
    conn = sqlite3.connect(str(bare_path))
    conn.execute("CREATE TABLE something (id INTEGER)")
    conn.commit()
    conn.close()
    with pytest.raises(restore_service.RestoreValidationError):
        restore_service.validate_backup_file(bare_path)


def test_staged_restore_round_trip(tmp_path):
    app_data_dir = tmp_path / "appdata" / "Derby"
    app_data_dir.mkdir(parents=True)
    backups_dir = tmp_path / "backups"
    live_db_path = app_data_dir / "derby.db"

    conn = _make_db(live_db_path)
    owner_id = users_repo.create_user(conn, "Owner Original", users_repo.ROLE_OWNER, "1111")
    conn.close()

    backup_path = tmp_path / "chosen_backup.db"
    backup_service.backup_to_file(live_db_path, backup_path)

    # Mutate the live DB after the backup was taken.
    conn = connect(live_db_path)
    users_repo.create_user(conn, "Cashier Added Later", users_repo.ROLE_CASHIER, "2222")
    conn.close()

    now = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
    marker_path = restore_service.stage_restore(backup_path, app_data_dir, backups_dir, now)
    assert marker_path.exists()

    safety_copies = list(backups_dir.glob("derby-before-restore-*.db"))
    assert len(safety_copies) == 1
    safety_conn = connect(safety_copies[0])
    assert len(users_repo.list_users(safety_conn)) == 2  # the mutated state, safely preserved
    safety_conn.close()

    # Simulate the relaunch.
    result = restore_service.apply_pending_restore(app_data_dir)
    assert result["status"] == "ok"
    assert not marker_path.exists()  # cleaned up

    restored_conn = connect(live_db_path)
    users = users_repo.list_users(restored_conn)
    assert len(users) == 1
    assert users[0]["id"] == owner_id
    assert users[0]["name"] == "Owner Original"
    restored_conn.close()


def test_apply_pending_restore_is_a_noop_without_a_marker(tmp_path):
    app_data_dir = tmp_path / "appdata"
    app_data_dir.mkdir()
    assert restore_service.apply_pending_restore(app_data_dir) is None


def test_apply_pending_restore_cleans_up_marker_for_a_corrupted_target(tmp_path):
    app_data_dir = tmp_path / "appdata"
    app_data_dir.mkdir()
    bogus_backup = tmp_path / "bogus.db"
    bogus_backup.write_bytes(b"not a database")
    marker_path = app_data_dir / restore_service.MARKER_FILE_NAME
    marker_path.write_text(str(bogus_backup), encoding="utf-8")

    result = restore_service.apply_pending_restore(app_data_dir)
    assert result["status"] == "failed"
    assert not marker_path.exists()


def test_stage_restore_rejects_corrupted_file_before_staging(tmp_path):
    app_data_dir = tmp_path / "appdata"
    app_data_dir.mkdir()
    bogus_backup = tmp_path / "bogus.db"
    bogus_backup.write_bytes(b"not a database")

    with pytest.raises(restore_service.RestoreValidationError):
        restore_service.stage_restore(bogus_backup, app_data_dir, tmp_path / "backups", datetime.now(timezone.utc))
    assert not (app_data_dir / restore_service.MARKER_FILE_NAME).exists()


def test_offer_mirror_restore_copies_missing_images_and_receipts(tmp_path):
    backup_file = tmp_path / "backups" / "derby-2026-01-10.db"
    backup_file.parent.mkdir(parents=True)
    backup_file.write_text("fake")
    mirror_root = backup_file.parent / "files"
    (mirror_root / "images").mkdir(parents=True)
    (mirror_root / "images" / "abc.jpg").write_bytes(b"IMG")
    (mirror_root / "receipts").mkdir(parents=True)
    (mirror_root / "receipts" / "def.jpg").write_bytes(b"RCPT")

    images_dir = tmp_path / "live_images"
    receipts_dir = tmp_path / "live_receipts"
    images_dir.mkdir()
    receipts_dir.mkdir()

    copied = restore_service.offer_mirror_restore(backup_file, images_dir, receipts_dir)
    assert copied == {"images": 1, "receipts": 1}
    assert (images_dir / "abc.jpg").read_bytes() == b"IMG"
    assert (receipts_dir / "def.jpg").read_bytes() == b"RCPT"


def test_offer_mirror_restore_handles_no_mirror_gracefully(tmp_path):
    backup_file = tmp_path / "backups" / "derby-2026-01-10.db"
    backup_file.parent.mkdir(parents=True)
    backup_file.write_text("fake")
    copied = restore_service.offer_mirror_restore(backup_file, tmp_path / "images", tmp_path / "receipts")
    assert copied == {"images": 0, "receipts": 0}
