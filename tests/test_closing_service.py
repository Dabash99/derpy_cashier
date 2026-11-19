from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from derby.core.db import (
    backup_log_repo,
    categories_repo,
    day_closures_repo,
    orders_repo,
    products_repo,
    settings_repo,
    tables_repo,
    users_repo,
)
from derby.core.db.connection import connect
from derby.core.db.migrations import run_pending_migrations
from derby.features.closing import closing_service


def _utc(year, month, day, hour, minute):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


# --- closure_due_at ----------------------------------------------------


def test_closure_due_at_evening_close_time_is_same_day():
    due = closing_service.closure_due_at(date(2026, 1, 10), time(23, 59))
    # 23:59 Cairo (UTC+2) on 2026-01-10 == 21:59 UTC same day.
    assert due == _utc(2026, 1, 10, 21, 59)


def test_closure_due_at_early_morning_close_time_is_next_day():
    due = closing_service.closure_due_at(date(2026, 1, 10), time(3, 0))
    # 03:00 Cairo on 2026-01-11 (the NEXT day) == 01:00 UTC on 2026-01-11.
    assert due == _utc(2026, 1, 11, 1, 0)


def test_closure_due_at_across_a_dst_style_date_still_correct():
    # Egypt reinstated summer time in 2023 (UTC+3 roughly April-October,
    # UTC+2 otherwise) -- the zoneinfo-based conversion must pick up the
    # correct offset for the date, not a fixed one.
    due = closing_service.closure_due_at(date(2026, 7, 1), time(23, 59))
    assert due == _utc(2026, 7, 1, 20, 59)  # UTC+3 in July


# --- due_business_dates --------------------------------------------------


def test_due_business_dates_empty_with_no_anchor(db_conn):
    assert closing_service.due_business_dates(db_conn, _utc(2026, 1, 10, 12, 0)) == []


def test_due_business_dates_uses_first_run_date_as_anchor(db_conn):
    closing_service.ensure_first_run_date(db_conn, _utc(2026, 1, 10, 12, 0))
    # Close time defaults to 23:59 -> due at 21:59 UTC the same day.
    due = closing_service.due_business_dates(db_conn, _utc(2026, 1, 10, 22, 0))
    assert due == [date(2026, 1, 10)]


def test_due_business_dates_catches_up_several_missed_days(db_conn):
    closing_service.ensure_first_run_date(db_conn, _utc(2026, 1, 1, 12, 0))
    due = closing_service.due_business_dates(db_conn, _utc(2026, 1, 6, 0, 0))
    assert due == [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3), date(2026, 1, 4), date(2026, 1, 5)]


def test_due_business_dates_capped_at_sixty():
    db_conn = connect(":memory:")
    run_pending_migrations(db_conn)
    settings_repo.ensure_defaults(db_conn)
    closing_service.ensure_first_run_date(db_conn, _utc(2025, 1, 1, 12, 0))
    now = _utc(2026, 6, 1, 12, 0)  # over a year later -- far more than 60 days pending
    due = closing_service.due_business_dates(db_conn, now)
    assert len(due) == 60
    assert due == sorted(due)  # still chronological
    db_conn.close()


def test_due_business_dates_no_duplicates_after_closing(db_conn):
    closing_service.ensure_first_run_date(db_conn, _utc(2026, 1, 1, 12, 0))
    now = _utc(2026, 1, 3, 0, 0)
    due = closing_service.due_business_dates(db_conn, now)
    assert due == [date(2026, 1, 1), date(2026, 1, 2)]

    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    assert owner_id  # sanity
    for business_date in due:
        day_closures_repo.create_closure(db_conn, business_date.isoformat(), "catchup", "نص", 0, 0, 0, 0, 0, 0)

    assert closing_service.due_business_dates(db_conn, now) == []  # nothing left to do


def test_due_business_dates_quiet_days_still_get_closed(db_conn, tmp_path):
    closing_service.ensure_first_run_date(db_conn, _utc(2026, 1, 1, 12, 0))
    db_path = tmp_path / "test_derby.db"
    now = _utc(2026, 1, 2, 0, 0)

    results = closing_service.run_due_closures(
        db_conn, db_path, now, "catchup", "ديربي", tmp_path / "primary", None, 30
    )
    assert len(results) == 1
    assert results[0]["invoice_count"] == 0
    assert results[0]["business_date"] == "2026-01-01"


# --- run_due_closures / close_or_rebuild_day end to end ---------------------


def test_run_due_closures_builds_report_and_backup(db_conn, tmp_path):
    db_path = tmp_path / "test_derby.db"  # the exact file db_conn is backed by
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 2500)
    table = tables_repo.list_tables(db_conn)[0]
    order_id = orders_repo.create_order(db_conn, table["id"], owner_id)
    orders_repo.create_order_item(db_conn, order_id, "product", product_id, "قهوة", 2500, 1, 2500)
    orders_repo.update_order_totals(db_conn, order_id, 2500, 0, 2500)
    orders_repo.mark_order_paid(db_conn, order_id, orders_repo.next_invoice_no(db_conn), owner_id, "2026-01-01", "cash")

    closing_service.ensure_first_run_date(db_conn, _utc(2026, 1, 1, 12, 0))
    results = closing_service.run_due_closures(
        db_conn, db_path, _utc(2026, 1, 2, 0, 0), "catchup", "ديربي", tmp_path / "primary", None, 30
    )
    assert len(results) == 1
    closure = results[0]
    assert closure["net_sales_piasters"] == 2500
    assert "قهوة" in closure["report_text"] or "مبيعات اليوم" in closure["report_text"]
    assert closure["backup_primary_status"] == "ok"

    backups = backup_log_repo.list_backups(db_conn, target="primary")
    assert len(backups) == 1
    assert backups[0]["verified"] == 1


def test_rebuild_via_close_or_rebuild_day_increments_revision_and_clears_sent(db_conn, tmp_path):
    db_path = tmp_path / "test_derby.db"
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")

    closure = closing_service.close_or_rebuild_day(
        db_conn, db_path, date(2026, 1, 1), "manual", "ديربي", tmp_path / "primary", None, 30, date(2026, 1, 1)
    )
    day_closures_repo.mark_sent(db_conn, closure["id"], owner_id)

    rebuilt = closing_service.close_or_rebuild_day(
        db_conn, db_path, date(2026, 1, 1), "manual", "ديربي", tmp_path / "primary", None, 30, date(2026, 1, 1)
    )
    assert rebuilt["revision"] == 2
    assert rebuilt["sent_at_utc"] is None


def test_close_today_manually_reports_whether_it_already_existed(db_conn, tmp_path):
    db_path = tmp_path / "test_derby.db"
    now = _utc(2026, 1, 1, 10, 0)

    closure1, already1 = closing_service.close_today_manually(
        db_conn, db_path, now, "ديربي", tmp_path / "primary", None, 30
    )
    assert already1 is False

    closure2, already2 = closing_service.close_today_manually(
        db_conn, db_path, now, "ديربي", tmp_path / "primary", None, 30
    )
    assert already2 is True
    assert closure2["revision"] == 2


# --- staleness ---------------------------------------------------------


def test_staleness_detected_after_a_late_payment(db_conn, tmp_path):
    db_path = tmp_path / "test_derby.db"
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 2500)

    closure = closing_service.close_or_rebuild_day(
        db_conn, db_path, date(2026, 1, 1), "auto", "ديربي", tmp_path / "primary", None, 30, date(2026, 1, 1)
    )
    assert closure["stale"] == 0
    assert closure["net_sales_piasters"] == 0

    # A late-arriving payment for the same business_date, after closing.
    order_id = orders_repo.create_order(db_conn, None, owner_id)
    orders_repo.create_order_item(db_conn, order_id, "product", product_id, "قهوة", 2500, 1, 2500)
    orders_repo.update_order_totals(db_conn, order_id, 2500, 0, 2500)
    orders_repo.mark_order_paid(db_conn, order_id, orders_repo.next_invoice_no(db_conn), owner_id, "2026-01-01", "cash")

    closing_service.recompute_staleness(db_conn, date(2026, 1, 1))
    reloaded = day_closures_repo.get_closure(db_conn, closure["id"])
    assert reloaded["stale"] == 1


def test_staleness_not_flagged_when_nothing_changed(db_conn, tmp_path):
    db_path = tmp_path / "test_derby.db"
    closure = closing_service.close_or_rebuild_day(
        db_conn, db_path, date(2026, 1, 1), "auto", "ديربي", tmp_path / "primary", None, 30, date(2026, 1, 1)
    )
    closing_service.recompute_staleness(db_conn, date(2026, 1, 1))
    reloaded = day_closures_repo.get_closure(db_conn, closure["id"])
    assert reloaded["stale"] == 0


# --- exit backup rule ----------------------------------------------------


def test_exit_backup_is_due_when_no_backup_yet(db_conn):
    assert closing_service.exit_backup_is_due(db_conn, _utc(2026, 1, 1, 12, 0)) is True


def test_exit_backup_not_due_within_six_hours(db_conn):
    backup_log_repo.log_backup(db_conn, "exit", "primary", "ok", verified=True)
    # log_backup uses the real clock for at_utc; simulate "now" as right after.
    from derby.core.utils.time_utils import utc_now

    assert closing_service.exit_backup_is_due(db_conn, utc_now() + timedelta(hours=1)) is False


def test_exit_backup_due_after_six_hours(db_conn):
    from derby.core.utils.time_utils import utc_now

    backup_log_repo.log_backup(db_conn, "exit", "primary", "ok", verified=True)
    assert closing_service.exit_backup_is_due(db_conn, utc_now() + timedelta(hours=7)) is True


def test_run_exit_backup_updates_last_exit_backup_setting(db_conn, tmp_path):
    db_path = tmp_path / "test_derby.db"
    now = _utc(2026, 1, 1, 10, 0)
    closing_service.run_exit_backup(db_conn, db_path, now, tmp_path / "primary", None, 30)
    assert settings_repo.get(db_conn, "last_exit_backup_utc") != ""


def test_is_backup_stale_for_banner(db_conn):
    assert closing_service.is_backup_stale_for_banner(db_conn, _utc(2026, 1, 1, 12, 0)) is True
    backup_log_repo.log_backup(db_conn, "daily", "primary", "ok", verified=True)
    from derby.core.utils.time_utils import utc_now

    assert closing_service.is_backup_stale_for_banner(db_conn, utc_now() + timedelta(days=1)) is False
    assert closing_service.is_backup_stale_for_banner(db_conn, utc_now() + timedelta(days=3)) is True


# --- manual standalone backup ------------------------------------------


def test_run_manual_backup_uses_manual_filename_pattern(db_conn, tmp_path):
    db_path = tmp_path / "test_derby.db"
    now = datetime(2026, 1, 1, 10, 30, 0, tzinfo=timezone.utc)
    primary, _secondary = closing_service.run_manual_backup(db_conn, db_path, now, tmp_path / "primary", None)
    assert primary.status == "ok"
    assert "derby-manual-20260101-103000.db" in primary.path
