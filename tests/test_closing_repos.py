from __future__ import annotations

from derby.core.db import backup_log_repo, day_closures_repo, users_repo


def test_create_and_get_closure(db_conn):
    closure_id = day_closures_repo.create_closure(
        db_conn, "2026-01-10", "auto", "نص التقرير", 5, 10000, 2000, 8000, 0, 0
    )
    closure = day_closures_repo.get_closure(db_conn, closure_id)
    assert closure["business_date"] == "2026-01-10"
    assert closure["revision"] == 1
    assert closure["stale"] == 0
    assert day_closures_repo.get_closure_by_date(db_conn, "2026-01-10")["id"] == closure_id


def test_rebuild_increments_revision_and_clears_sent(db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    closure_id = day_closures_repo.create_closure(db_conn, "2026-01-10", "auto", "نص", 5, 10000, 2000, 8000, 0, 0)
    day_closures_repo.mark_sent(db_conn, closure_id, owner_id)
    day_closures_repo.mark_stale(db_conn, closure_id)

    day_closures_repo.rebuild_closure(db_conn, closure_id, "نص جديد", 6, 11000, 2000, 9000, 0, 0)
    closure = day_closures_repo.get_closure(db_conn, closure_id)
    assert closure["revision"] == 2
    assert closure["report_text"] == "نص جديد"
    assert closure["sent_at_utc"] is None
    assert closure["stale"] == 0


def test_list_unsent_closures(db_conn):
    day_closures_repo.create_closure(db_conn, "2026-01-10", "auto", "نص", 1, 1000, 0, 1000, 0, 0)
    closure_id = day_closures_repo.create_closure(db_conn, "2026-01-11", "auto", "نص", 1, 1000, 0, 1000, 0, 0)
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    day_closures_repo.mark_sent(db_conn, closure_id, owner_id)

    unsent = day_closures_repo.list_unsent_closures(db_conn)
    assert [c["business_date"] for c in unsent] == ["2026-01-10"]


def test_backup_log_last_verified(db_conn):
    backup_log_repo.log_backup(db_conn, "daily", "primary", "ok", path="a.db", verified=True)
    backup_log_repo.log_backup(db_conn, "daily", "primary", "failed", error="no folder", verified=False)
    last = backup_log_repo.last_verified_backup(db_conn, "primary")
    assert last["path"] == "a.db"
    assert backup_log_repo.last_verified_backup(db_conn, "secondary") is None
