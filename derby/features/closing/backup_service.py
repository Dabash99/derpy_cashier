"""Backup, verification, rotation, and folder mirroring. Plain filesystem
and sqlite3 I/O only -- no Qt -- so it runs identically from the closing
worker thread. Uses SQLite's own backup API (Connection.backup) instead
of a raw file copy so a backup taken mid-write is never corrupted.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

from derby.core.db import backup_log_repo
from derby.core.i18n import ar

SNAPSHOT_TABLES = ("users", "orders", "order_items", "expenses", "ps_sessions")

DAILY_FILENAME_PATTERN = re.compile(r"^derby-\d{4}-\d{2}-\d{2}\.db$")
MANUAL_FILENAME_PATTERN = re.compile(r"^derby-manual-\d{8}-\d{6}\.db$")

MANUAL_KEEP_COUNT = 10


class BackupError(Exception):
    """A target being unavailable or a verification mismatch -- always
    caught by run_backup_to_target, never left to propagate."""


class TargetOutcome:
    def __init__(
        self,
        status: str,
        path: Optional[str] = None,
        size_bytes: Optional[int] = None,
        sha256: Optional[str] = None,
        verified: bool = False,
        error: Optional[str] = None,
    ) -> None:
        self.status = status  # 'ok' | 'failed' | 'skipped'
        self.path = path
        self.size_bytes = size_bytes
        self.sha256 = sha256
        self.verified = verified
        self.error = error


def daily_file_name(business_date_iso: str) -> str:
    return "derby-{0}.db".format(business_date_iso)


def manual_file_name(now) -> str:
    return "derby-manual-{0}.db".format(now.strftime("%Y%m%d-%H%M%S"))


def take_snapshot(conn: sqlite3.Connection) -> Dict:
    """Row counts + user_version read inside one read transaction, so
    they describe one consistent instant even while another connection
    writes concurrently (WAL permits that)."""
    conn.execute("BEGIN")
    try:
        counts = {
            table: conn.execute("SELECT COUNT(*) FROM {0}".format(table)).fetchone()[0]
            for table in SNAPSHOT_TABLES
        }
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.execute("COMMIT")
    return {"counts": counts, "user_version": user_version}


def backup_to_file(db_path: Path, dest_path: Path) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest_path.with_name(dest_path.name + ".tmp")
    source_conn = sqlite3.connect(str(db_path))
    try:
        dest_conn = sqlite3.connect(str(tmp_path))
        try:
            source_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        source_conn.close()
    os.replace(str(tmp_path), str(dest_path))


def compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(str(path), "rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_backup(path: Path, expected_snapshot: Dict) -> None:
    uri = "file:{0}?mode=ro".format(path.resolve().as_posix())
    conn = sqlite3.connect(uri, uri=True)
    try:
        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        except sqlite3.Error:
            raise BackupError(ar.BACKUP_ERROR_INTEGRITY)
        if integrity != "ok":
            raise BackupError(ar.BACKUP_ERROR_INTEGRITY)
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
        if user_version != expected_snapshot["user_version"]:
            raise BackupError(ar.BACKUP_ERROR_VERSION_MISMATCH)
        for table, expected_count in expected_snapshot["counts"].items():
            actual = conn.execute("SELECT COUNT(*) FROM {0}".format(table)).fetchone()[0]
            if actual != expected_count:
                raise BackupError(ar.BACKUP_ERROR_COUNT_MISMATCH)
    finally:
        conn.close()


def mirror_folder(source_dir: Path, dest_dir: Path) -> int:
    """Copies files missing from dest_dir (by relative path, recursively).
    Never deletes or overwrites -- image/receipt file names are immutable
    uuids, so "missing" is the only case that needs copying."""
    if not source_dir.exists():
        return 0
    copied = 0
    for source_file in source_dir.rglob("*"):
        if source_file.is_dir():
            continue
        relative = source_file.relative_to(source_dir)
        dest_file = dest_dir / relative
        if dest_file.exists():
            continue
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(source_file), str(dest_file))
        copied += 1
    return copied


def rotate_backups(folder: Path, pattern: "re.Pattern", keep_count: int) -> List[Path]:
    """Deletes the oldest files matching `pattern` beyond `keep_count`.
    Only ever touches files matching the exact pattern -- nothing else in
    the folder is ever looked at."""
    if not folder.exists():
        return []
    matching = sorted(
        (path for path in folder.iterdir() if path.is_file() and pattern.match(path.name)), key=lambda p: p.name
    )
    to_delete = matching[:-keep_count] if keep_count > 0 else matching
    deleted = []
    for path in to_delete:
        try:
            path.unlink()
            deleted.append(path)
        except OSError:
            pass
    return deleted


def test_folder_writable(folder: Path) -> bool:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".derby_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def same_drive(path_a: Path, path_b: Path) -> bool:
    drive_a = os.path.splitdrive(str(path_a))[0].upper()
    drive_b = os.path.splitdrive(str(path_b))[0].upper()
    return bool(drive_a) and drive_a == drive_b


def run_backup_to_target(
    db_path: Path,
    target_dir: Path,
    file_name: str,
    expected_snapshot: Dict,
    rotation_pattern: "re.Pattern",
    keep_count: int,
    source_file_to_copy: Optional[Path] = None,
) -> TargetOutcome:
    """If source_file_to_copy is given, COPY that already-verified file
    (used for a secondary target once the primary produced one) instead
    of running a fresh SQLite backup; otherwise backs up + verifies here.
    Never raises -- any failure becomes a 'failed' TargetOutcome."""
    dest_path = target_dir / file_name
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        if source_file_to_copy is not None:
            shutil.copy2(str(source_file_to_copy), str(dest_path))
            if compute_sha256(dest_path) != compute_sha256(source_file_to_copy):
                raise BackupError(ar.BACKUP_ERROR_COPY_MISMATCH)
        else:
            backup_to_file(db_path, dest_path)
            verify_backup(dest_path, expected_snapshot)
        sha256 = compute_sha256(dest_path)
        size_bytes = dest_path.stat().st_size
        rotate_backups(target_dir, rotation_pattern, keep_count)
        return TargetOutcome(status="ok", path=str(dest_path), size_bytes=size_bytes, sha256=sha256, verified=True)
    except Exception as error:  # noqa: BLE001 -- recorded, never propagated past one target
        return TargetOutcome(status="failed", path=str(dest_path), error=str(error))


def run_backup_pair(
    conn: sqlite3.Connection,
    db_path: Path,
    kind: str,
    file_name: str,
    primary_dir: Optional[Path],
    secondary_dir: Optional[Path],
    keep_count: int,
) -> "tuple[TargetOutcome, TargetOutcome]":
    """Backs up to the primary target, then mirrors that exact verified
    file to the secondary (comparing SHA-256) -- or, if the primary is
    unavailable, attempts an independent backup straight to the
    secondary so one missing drive never also skips the other. Every
    attempt (including a skipped one) is recorded in backup_log."""
    rotation_pattern = MANUAL_FILENAME_PATTERN if kind == "manual" else DAILY_FILENAME_PATTERN
    snapshot = take_snapshot(conn)

    if primary_dir is not None:
        primary = run_backup_to_target(db_path, primary_dir, file_name, snapshot, rotation_pattern, keep_count)
    else:
        primary = TargetOutcome(status="skipped")
    _log(conn, kind, "primary", primary)

    if secondary_dir is None:
        secondary = TargetOutcome(status="skipped")
    elif primary.status == "ok":
        secondary = run_backup_to_target(
            db_path, secondary_dir, file_name, snapshot, rotation_pattern, keep_count,
            source_file_to_copy=Path(primary.path),
        )
    else:
        secondary = run_backup_to_target(db_path, secondary_dir, file_name, snapshot, rotation_pattern, keep_count)
    _log(conn, kind, "secondary", secondary)

    return primary, secondary


def _log(conn: sqlite3.Connection, kind: str, target: str, outcome: TargetOutcome) -> None:
    backup_log_repo.log_backup(
        conn, kind, target, outcome.status, path=outcome.path, size_bytes=outcome.size_bytes,
        sha256=outcome.sha256, verified=outcome.verified, error=outcome.error,
    )
