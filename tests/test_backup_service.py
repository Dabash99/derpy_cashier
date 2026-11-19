from __future__ import annotations

import sqlite3
import threading
import time

import pytest

from derby.core.db.connection import connect
from derby.core.db.migrations import run_pending_migrations
from derby.features.closing import backup_service


@pytest.fixture()
def live_db(tmp_path):
    db_path = tmp_path / "derby.db"
    conn = connect(db_path)
    run_pending_migrations(conn)
    yield db_path, conn
    conn.close()


def test_backup_to_file_and_verify_roundtrip(tmp_path, live_db):
    db_path, conn = live_db
    snapshot = backup_service.take_snapshot(conn)
    dest = tmp_path / "out" / "derby-2026-01-10.db"
    backup_service.backup_to_file(db_path, dest)
    assert dest.exists()
    backup_service.verify_backup(dest, snapshot)  # must not raise


def test_verify_backup_catches_corrupted_file(tmp_path, live_db):
    db_path, conn = live_db
    snapshot = backup_service.take_snapshot(conn)
    dest = tmp_path / "derby-2026-01-10.db"
    backup_service.backup_to_file(db_path, dest)

    dest.write_bytes(b"not a real sqlite file at all")
    with pytest.raises(backup_service.BackupError):
        backup_service.verify_backup(dest, snapshot)


def test_verify_backup_catches_truncated_file(tmp_path, live_db):
    db_path, conn = live_db
    snapshot = backup_service.take_snapshot(conn)
    dest = tmp_path / "derby-2026-01-10.db"
    backup_service.backup_to_file(db_path, dest)

    original = dest.read_bytes()
    dest.write_bytes(original[: len(original) // 2])
    with pytest.raises(backup_service.BackupError):
        backup_service.verify_backup(dest, snapshot)


def test_backup_while_another_connection_writes_concurrently(tmp_path, live_db):
    db_path, conn = live_db

    stop = threading.Event()
    errors = []

    def _writer():
        writer_conn = sqlite3.connect(str(db_path))
        writer_conn.execute("PRAGMA journal_mode=WAL")
        try:
            i = 0
            while not stop.is_set():
                writer_conn.execute(
                    "INSERT INTO audit_log (at_utc, action, details) VALUES ('2026-01-01T00:00:00+00:00', 'noise', ?)",
                    (str(i),),
                )
                writer_conn.commit()
                i += 1
                time.sleep(0.001)
        except Exception as error:  # noqa: BLE001
            errors.append(error)
        finally:
            writer_conn.close()

    thread = threading.Thread(target=_writer)
    thread.start()
    try:
        snapshot = backup_service.take_snapshot(conn)
        dest = tmp_path / "derby-2026-01-10.db"
        backup_service.backup_to_file(db_path, dest)
        backup_service.verify_backup(dest, snapshot)  # must not raise despite concurrent writes
    finally:
        stop.set()
        thread.join(timeout=5)
    assert errors == []


def test_rotation_keeps_exact_count_and_only_touches_matching_pattern(tmp_path):
    folder = tmp_path
    for day in range(1, 36):
        (folder / "derby-2026-01-{0:02d}.db".format(day)).write_text("x")
    (folder / "unrelated-file.db").write_text("keep me")
    (folder / "notes.txt").write_text("keep me too")

    backup_service.rotate_backups(folder, backup_service.DAILY_FILENAME_PATTERN, keep_count=30)

    remaining = sorted(p.name for p in folder.iterdir())
    daily_remaining = [n for n in remaining if backup_service.DAILY_FILENAME_PATTERN.match(n)]
    assert len(daily_remaining) == 30
    assert daily_remaining[0] == "derby-2026-01-06.db"  # oldest 5 deleted
    assert "unrelated-file.db" in remaining
    assert "notes.txt" in remaining


def test_rotation_does_not_run_when_verification_failed(tmp_path, live_db, monkeypatch):
    db_path, conn = live_db
    snapshot = backup_service.take_snapshot(conn)
    target_dir = tmp_path / "backups"
    target_dir.mkdir()
    for day in range(1, 32):
        (target_dir / "derby-2026-01-{0:02d}.db".format(day)).write_text("old")

    original_names = {p.name for p in target_dir.iterdir()}
    monkeypatch.setattr(backup_service, "verify_backup", lambda *a, **k: (_ for _ in ()).throw(backup_service.BackupError("x")))
    outcome = backup_service.run_backup_to_target(
        db_path, target_dir, "derby-2026-02-01.db", snapshot, backup_service.DAILY_FILENAME_PATTERN, 30
    )
    assert outcome.status == "failed"
    # Rotation never ran -- every pre-existing backup is still there untouched
    # (the fresh, unverified file this attempt wrote is irrelevant here).
    remaining_names = {p.name for p in target_dir.iterdir()}
    assert original_names.issubset(remaining_names)


def test_mirror_folder_copies_only_missing_files(tmp_path):
    source = tmp_path / "source"
    dest = tmp_path / "dest"
    source.mkdir()
    (source / "a.jpg").write_bytes(b"AAA")
    (source / "thumbs").mkdir()
    (source / "thumbs" / "a.jpg").write_bytes(b"thumb")
    dest.mkdir()
    (dest / "b.jpg").write_bytes(b"existing, must survive")

    copied = backup_service.mirror_folder(source, dest)
    assert copied == 2
    assert (dest / "a.jpg").read_bytes() == b"AAA"
    assert (dest / "thumbs" / "a.jpg").read_bytes() == b"thumb"
    assert (dest / "b.jpg").read_bytes() == b"existing, must survive"  # never touched

    # Running again copies nothing new (already present).
    copied_again = backup_service.mirror_folder(source, dest)
    assert copied_again == 0


def test_mirror_folder_never_deletes_extra_files_in_dest(tmp_path):
    source = tmp_path / "source"
    dest = tmp_path / "dest"
    source.mkdir()
    dest.mkdir()
    (dest / "old_backup_only_file.jpg").write_bytes(b"keep")

    backup_service.mirror_folder(source, dest)
    assert (dest / "old_backup_only_file.jpg").exists()


def test_secondary_target_unavailable_primary_still_succeeds(tmp_path, live_db):
    db_path, conn = live_db
    primary_dir = tmp_path / "primary"
    unavailable_secondary = tmp_path / "not_a_real_drive" / "secondary"
    # Make the parent a FILE so mkdir() for the secondary target raises.
    (tmp_path / "not_a_real_drive").write_text("i am a file, not a directory")

    primary, secondary = backup_service.run_backup_pair(
        conn, db_path, "daily", "derby-2026-01-10.db", primary_dir, unavailable_secondary, 30
    )
    assert primary.status == "ok"
    assert secondary.status == "failed"


def test_retry_after_secondary_becomes_available_succeeds(tmp_path, live_db):
    db_path, conn = live_db
    primary_dir = tmp_path / "primary"
    blocked_path = tmp_path / "blocked"
    blocked_path.write_text("blocking file")

    primary, secondary = backup_service.run_backup_pair(
        conn, db_path, "daily", "derby-2026-01-10.db", primary_dir, blocked_path / "secondary", 30
    )
    assert secondary.status == "failed"

    blocked_path.unlink()
    real_secondary = tmp_path / "blocked"  # now a real folder path once the blocking file is gone
    primary2, secondary2 = backup_service.run_backup_pair(
        conn, db_path, "daily", "derby-2026-01-10.db", primary_dir, real_secondary / "secondary", 30
    )
    assert secondary2.status == "ok"


def test_test_folder_writable(tmp_path):
    assert backup_service.test_folder_writable(tmp_path / "new_folder") is True


def test_same_drive_detection(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    assert backup_service.same_drive(a, b) is True  # same tmp_path drive


def test_sha256_copy_mismatch_is_caught(tmp_path, live_db, monkeypatch):
    db_path, conn = live_db
    primary_dir = tmp_path / "primary"
    secondary_dir = tmp_path / "secondary"

    primary, secondary = backup_service.run_backup_pair(
        conn, db_path, "daily", "derby-2026-01-10.db", primary_dir, secondary_dir, 30
    )
    assert primary.status == "ok"
    assert secondary.status == "ok"

    # Corrupt the secondary copy after the fact and confirm a mismatch would be detected.
    secondary_file = secondary_dir / "derby-2026-01-10.db"
    original_bytes = secondary_file.read_bytes()
    secondary_file.write_bytes(original_bytes + b"corruption")
    assert backup_service.compute_sha256(secondary_file) != backup_service.compute_sha256(
        primary_dir / "derby-2026-01-10.db"
    )
