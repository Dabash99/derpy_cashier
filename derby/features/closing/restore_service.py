"""Staged restore: validate a chosen backup file, stage the swap (marker
file + a safety copy of the current database), and apply it at the very
next startup, before the database is opened. If the relaunch never
happens or fails, nothing is lost -- the marker is harmless and the old
database file is untouched until apply_pending_restore actually runs.
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import Optional

from derby.core.db.migrations import MIGRATIONS
from derby.core.i18n import ar
from derby.features.closing import backup_service

MARKER_FILE_NAME = "restore_pending.marker"

EXPECTED_TABLES = {
    "users", "settings", "audit_log", "categories", "products", "orders", "order_items",
    "expenses", "day_closures", "backup_log",
}


class RestoreValidationError(Exception):
    pass


def validate_backup_file(path: Path) -> None:
    """Raises RestoreValidationError (Arabic message) if the file is
    corrupted, missing expected tables, or from a NEWER schema than this
    app understands."""
    if not path.exists():
        raise RestoreValidationError(ar.RESTORE_ERROR_CORRUPTED)
    try:
        conn = sqlite3.connect("file:{0}?mode=ro".format(path.resolve().as_posix()), uri=True)
    except sqlite3.Error:
        raise RestoreValidationError(ar.RESTORE_ERROR_CORRUPTED)
    try:
        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        except sqlite3.Error:
            raise RestoreValidationError(ar.RESTORE_ERROR_CORRUPTED)
        if integrity != "ok":
            raise RestoreValidationError(ar.RESTORE_ERROR_CORRUPTED)

        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
        if user_version > len(MIGRATIONS):
            raise RestoreValidationError(ar.RESTORE_ERROR_NEWER_SCHEMA)

        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if not EXPECTED_TABLES.issubset(tables):
            raise RestoreValidationError(ar.RESTORE_ERROR_CORRUPTED)
    finally:
        conn.close()


def stage_restore(chosen_backup_path: Path, app_data_dir: Path, primary_backup_dir: Path, now) -> Path:
    """Validates the file, makes a safety copy of the CURRENT database
    into the primary backup folder, and writes the marker the next
    startup looks for. Returns the marker path."""
    validate_backup_file(chosen_backup_path)

    current_db_path = app_data_dir / "derby.db"
    if current_db_path.exists():
        primary_backup_dir.mkdir(parents=True, exist_ok=True)
        safety_copy_name = "derby-before-restore-{0}.db".format(now.strftime("%Y%m%d-%H%M%S"))
        shutil.copy2(str(current_db_path), str(primary_backup_dir / safety_copy_name))

    marker_path = app_data_dir / MARKER_FILE_NAME
    marker_path.write_text(str(chosen_backup_path.resolve()), encoding="utf-8")
    return marker_path


def apply_pending_restore(app_data_dir: Path) -> Optional[dict]:
    """Called at the very next startup, BEFORE the database connection
    is opened. Returns None when there was nothing to do (the common
    case); otherwise a dict describing what happened, for the caller to
    audit-log once the (new) database connection is open."""
    marker_path = app_data_dir / MARKER_FILE_NAME
    if not marker_path.exists():
        return None

    chosen_backup_path = Path(marker_path.read_text(encoding="utf-8").strip())
    current_db_path = app_data_dir / "derby.db"

    try:
        validate_backup_file(chosen_backup_path)
    except RestoreValidationError as error:
        marker_path.unlink()
        return {"status": "failed", "backup_path": str(chosen_backup_path), "error": str(error)}

    for suffix in ("-wal", "-shm"):
        stale_path = Path(str(current_db_path) + suffix)
        if stale_path.exists():
            stale_path.unlink()

    shutil.copy2(str(chosen_backup_path), str(current_db_path))
    marker_path.unlink()
    return {"status": "ok", "backup_path": str(chosen_backup_path)}


def offer_mirror_restore(backup_file_path: Path, images_dir: Path, receipts_dir: Path) -> dict:
    """If an images/receipts mirror sits next to the chosen backup file
    (<folder>\\files\\images, \\files\\receipts), copies back whatever is
    missing locally. Copy-only-missing, same as the backup-time mirror."""
    mirror_root = backup_file_path.parent / "files"
    copied = {"images": 0, "receipts": 0}
    if (mirror_root / "images").exists():
        copied["images"] = backup_service.mirror_folder(mirror_root / "images", images_dir)
    if (mirror_root / "receipts").exists():
        copied["receipts"] = backup_service.mirror_folder(mirror_root / "receipts", receipts_dir)
    return copied
