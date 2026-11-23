"""Part B: monthly retention tier, manual retention cleanup, and the
"آخر نسخة خارجية" dashboard status (green/amber/red)."""
from __future__ import annotations

from datetime import date, timedelta

from derby.core.db import backup_log_repo
from derby.core.db.connection import connect
from derby.core.db.migrations import run_pending_migrations
from derby.core.utils.time_utils import utc_now
from derby.features.closing import backup_service, closing_service


def _live_db(tmp_path):
    db_path = tmp_path / "derby.db"
    conn = connect(db_path)
    run_pending_migrations(conn)
    return db_path, conn


def test_first_closing_of_each_month_creates_a_monthly_snapshot(tmp_path):
    db_path, conn = _live_db(tmp_path)
    primary_dir = tmp_path / "primary"

    closing_service.close_or_rebuild_day(conn, db_path, date(2026, 1, 1), "auto", "ديربي", primary_dir, None, 30, date(2026, 1, 1))
    assert (primary_dir / "derby-monthly-2026-01.db").exists()

    # A later day in the SAME month must not create a second snapshot.
    first_snapshot_bytes = (primary_dir / "derby-monthly-2026-01.db").read_bytes()
    closing_service.close_or_rebuild_day(conn, db_path, date(2026, 1, 2), "auto", "ديربي", primary_dir, None, 30, date(2026, 1, 2))
    assert (primary_dir / "derby-monthly-2026-01.db").read_bytes() == first_snapshot_bytes

    closing_service.close_or_rebuild_day(conn, db_path, date(2026, 2, 1), "auto", "ديربي", primary_dir, None, 30, date(2026, 2, 1))
    assert (primary_dir / "derby-monthly-2026-02.db").exists()
    conn.close()


def test_monthly_snapshot_is_not_logged_as_a_fresh_backup_event(tmp_path):
    """Regression guard: a monthly archival copy must never be mistaken
    for "the most recent backup" by exit_backup_is_due/retry_secondary/
    the dashboard tile -- those all read backup_log, which only ever
    gets the real daily/manual backup row."""
    db_path, conn = _live_db(tmp_path)
    primary_dir = tmp_path / "primary"
    closing_service.close_or_rebuild_day(conn, db_path, date(2026, 1, 1), "auto", "ديربي", primary_dir, None, 30, date(2026, 1, 1))

    last = backup_log_repo.last_verified_backup(conn, "primary")
    assert last is not None
    assert "derby-2026-01-01.db" in last["path"]
    conn.close()


def test_apply_retention_policy_only_touches_matching_patterns(tmp_path):
    folder = tmp_path / "ext"
    folder.mkdir()
    for day in range(1, 10):
        (folder / "derby-2026-01-{0:02d}.db".format(day)).write_text("x")
    for month in range(1, 5):
        (folder / "derby-monthly-2026-{0:02d}.db".format(month)).write_text("x")
    (folder / "unrelated.txt").write_text("keep")

    deleted = backup_service.apply_retention_policy(folder, keep_daily=3, keep_monthly=2)
    remaining = {p.name for p in folder.iterdir()}
    assert deleted == (9 - 3) + (4 - 2)
    assert "unrelated.txt" in remaining
    assert len([n for n in remaining if backup_service.DAILY_FILENAME_PATTERN.match(n)]) == 3
    assert len([n for n in remaining if backup_service.MONTHLY_FILENAME_PATTERN.match(n)]) == 2


def test_apply_retention_policy_missing_folder_is_a_safe_no_op():
    assert backup_service.apply_retention_policy(None, 30, 12) == 0


def test_external_backup_status_missing_when_no_secondary_configured(tmp_path):
    db_path, conn = _live_db(tmp_path)
    assert backup_service.external_backup_status(conn, utc_now(), None, 2) == "missing"
    conn.close()


def test_external_backup_status_missing_when_never_succeeded(tmp_path):
    db_path, conn = _live_db(tmp_path)
    assert backup_service.external_backup_status(conn, utc_now(), tmp_path / "secondary", 2) == "missing"
    conn.close()


def test_external_backup_status_ok_then_warning_as_it_ages(tmp_path):
    db_path, conn = _live_db(tmp_path)
    primary_dir = tmp_path / "primary"
    secondary_dir = tmp_path / "secondary"
    now = utc_now()
    closing_service.run_manual_backup(conn, db_path, now, primary_dir, secondary_dir)

    assert backup_service.external_backup_status(conn, now, secondary_dir, 2) == "ok"
    assert backup_service.external_backup_status(conn, now + timedelta(days=5), secondary_dir, 2) == "warning"
    conn.close()
