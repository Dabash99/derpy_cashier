"""Orchestrates the daily closing: which business dates are due, building
each closure's report + backup, staleness detection, and the exit/manual
backup safety nets. No Qt here -- the worker thread (closing_worker.py)
just calls into this module with its own sqlite3 connection.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone
from datetime import time as time_of_day
from pathlib import Path
from typing import List, Optional

from derby.core.db import (
    audit_repo,
    backup_log_repo,
    day_closures_repo,
    orders_repo,
    ps_devices_repo,
    settings_repo,
    tables_repo,
)
from derby.core.i18n import ar
from derby.core.utils.business_date import business_date as compute_business_date
from derby.core.utils.time_utils import CAIRO_TZ, parse_utc_iso, to_utc_iso
from derby.features.closing import backup_service, closing_text
from derby.features.reports import report_service

_NOON = time_of_day(12, 0)
CATCHUP_CAP_DAYS = 60
STALENESS_CHECK_WINDOW_DAYS = 14
EXIT_BACKUP_MAX_AGE_HOURS = 6
STARTUP_BACKUP_WARNING_DAYS = 2


def _close_time_setting(conn: sqlite3.Connection) -> time_of_day:
    text = settings_repo.get(conn, "business_close_time", "23:59") or "23:59"
    hour_str, minute_str = text.split(":")
    return time_of_day(int(hour_str), int(minute_str))


def closure_due_at(business_date_value: date, close_time: time_of_day) -> datetime:
    """The moment a business date's closure becomes due, in UTC. An
    evening close time (>= noon) is due that same calendar date; an
    early-morning one (e.g. 03:00) is due the NEXT calendar day, since
    the business day itself doesn't end until then."""
    if close_time >= _NOON:
        due_date = business_date_value
    else:
        due_date = business_date_value + timedelta(days=1)
    due_naive = datetime.combine(due_date, close_time)
    due_cairo = due_naive.replace(tzinfo=CAIRO_TZ)
    return due_cairo.astimezone(timezone.utc)


def ensure_first_run_date(conn: sqlite3.Connection, now: datetime) -> None:
    """Anchors due_business_dates when there is no closure history yet.
    Called once at app startup; a no-op once the setting is already set."""
    existing = settings_repo.get(conn, "app_first_run_date", "") or ""
    if existing:
        return
    today = compute_business_date(now, _close_time_setting(conn))
    settings_repo.set_value(conn, "app_first_run_date", today.isoformat())


def due_business_dates(conn: sqlite3.Connection, now: datetime) -> List[date]:
    """Every business date whose due time has passed and that has no
    day_closures row yet, in order, capped to the most recent 60."""
    close_time = _close_time_setting(conn)
    last_closure = day_closures_repo.get_last_closure(conn)
    if last_closure is not None:
        start = date.fromisoformat(last_closure["business_date"]) + timedelta(days=1)
    else:
        first_run_text = settings_repo.get(conn, "app_first_run_date", "") or ""
        if not first_run_text:
            return []
        start = date.fromisoformat(first_run_text)

    due = []
    current = start
    iterations = 0
    while closure_due_at(current, close_time) <= now and iterations < 3650:
        due.append(current)
        current += timedelta(days=1)
        iterations += 1
    if len(due) > CATCHUP_CAP_DAYS:
        due = due[-CATCHUP_CAP_DAYS:]
    return due


def _open_order_location_names(conn: sqlite3.Connection, limit: int = 5) -> List[str]:
    names = []
    for order in orders_repo.list_orders(conn, status="open"):
        if len(names) >= limit:
            break
        if order["table_id"]:
            table = tables_repo.get_table(conn, order["table_id"])
            if table is not None:
                names.append(table["name"])
        elif order["device_id"]:
            device = ps_devices_repo.get_device(conn, order["device_id"])
            if device is not None:
                names.append(device["name"])
        else:
            names.append(ar.TABLES_TAKEAWAY_SECTION)
    return names


def _backup_status_line(primary, secondary, has_secondary: bool) -> str:
    if primary.status == "ok" and (not has_secondary or secondary.status == "ok"):
        return ar.CLOSING_BACKUP_STATUS_LINE_OK
    if primary.status != "ok":
        return ar.CLOSING_BACKUP_STATUS_LINE_PRIMARY_FAILED
    return ar.CLOSING_BACKUP_STATUS_LINE_SECONDARY_FAILED


def close_or_rebuild_day(
    conn: sqlite3.Connection,
    db_path: Path,
    business_date_value: date,
    trigger: str,
    cafe_name: str,
    primary_dir: Optional[Path],
    secondary_dir: Optional[Path],
    keep_count: int,
    today: date,
) -> sqlite3.Row:
    """Builds (or rebuilds) one day's closure: the report, the backup
    pair, and the day_closures row. Creating vs rebuilding is decided by
    whether a closure for this date already exists -- the "إقفال اليوم
    الآن" button and "إعادة بناء التقرير" both call this; only the
    target date and the existing-row check differ."""
    day_report = report_service.build_report(conn, business_date_value, business_date_value, today=today)
    month_start = business_date_value.replace(day=1)
    month_report = report_service.build_report(conn, month_start, business_date_value, today=today)
    previous_day_names = _open_order_location_names(conn)

    file_name = backup_service.daily_file_name(business_date_value.isoformat())
    primary, secondary = backup_service.run_backup_pair(
        conn, db_path, "daily", file_name, primary_dir, secondary_dir, keep_count
    )
    backup_status_line = _backup_status_line(primary, secondary, secondary_dir is not None)

    text = closing_text.build_closing_text(
        cafe_name,
        business_date_value,
        day_report,
        month_report,
        open_orders_count=day_report.open_orders_count,
        running_sessions_count=day_report.running_sessions_count,
        previous_day_names=previous_day_names,
        backup_status_line=backup_status_line,
    )
    profit = day_report.net_sales_piasters - day_report.expenses_total_piasters

    existing = day_closures_repo.get_closure_by_date(conn, business_date_value.isoformat())
    if existing is None:
        closure_id = day_closures_repo.create_closure(
            conn, business_date_value.isoformat(), trigger, text, day_report.invoice_count,
            day_report.net_sales_piasters, day_report.expenses_total_piasters, profit,
            day_report.open_orders_count, day_report.running_sessions_count,
        )
    else:
        day_closures_repo.rebuild_closure(
            conn, existing["id"], text, day_report.invoice_count, day_report.net_sales_piasters,
            day_report.expenses_total_piasters, profit, day_report.open_orders_count, day_report.running_sessions_count,
        )
        closure_id = existing["id"]

    day_closures_repo.set_backup_status(
        conn, closure_id, file_name, primary.status, secondary.status if secondary_dir is not None else None,
        backup_status_line,
    )
    audit_repo.log(
        conn, "day_closed", details="business_date={0} trigger={1}".format(business_date_value.isoformat(), trigger)
    )
    return day_closures_repo.get_closure(conn, closure_id)


def run_due_closures(
    conn: sqlite3.Connection,
    db_path: Path,
    now: datetime,
    trigger: str,
    cafe_name: str,
    primary_dir: Optional[Path],
    secondary_dir: Optional[Path],
    keep_count: int,
) -> List[sqlite3.Row]:
    close_time = _close_time_setting(conn)
    today = compute_business_date(now, close_time)
    results = [
        close_or_rebuild_day(conn, db_path, business_date_value, trigger, cafe_name, primary_dir, secondary_dir, keep_count, today)
        for business_date_value in due_business_dates(conn, now)
    ]
    recompute_staleness(conn, today)
    return results


def recompute_staleness(conn: sqlite3.Connection, today: date) -> None:
    since = (today - timedelta(days=STALENESS_CHECK_WINDOW_DAYS)).isoformat()
    for closure in day_closures_repo.list_recent_closures(conn, since):
        if closure["stale"]:
            continue
        business_date_value = date.fromisoformat(closure["business_date"])
        live = report_service.build_report(conn, business_date_value, business_date_value, today=today)
        live_profit = live.net_sales_piasters - live.expenses_total_piasters
        if (
            live.invoice_count != closure["invoice_count"]
            or live.net_sales_piasters != closure["net_sales_piasters"]
            or live.expenses_total_piasters != closure["expenses_piasters"]
            or live_profit != closure["profit_piasters"]
        ):
            day_closures_repo.mark_stale(conn, closure["id"])


def close_today_manually(
    conn: sqlite3.Connection,
    db_path: Path,
    now: datetime,
    cafe_name: str,
    primary_dir: Optional[Path],
    secondary_dir: Optional[Path],
    keep_count: int,
) -> "tuple[sqlite3.Row, bool]":
    close_time = _close_time_setting(conn)
    today = compute_business_date(now, close_time)
    already_existed = day_closures_repo.get_closure_by_date(conn, today.isoformat()) is not None
    closure = close_or_rebuild_day(conn, db_path, today, "manual", cafe_name, primary_dir, secondary_dir, keep_count, today)
    return closure, already_existed


# --- backup safety nets (independent of day closures) -----------------------


def exit_backup_is_due(conn: sqlite3.Connection, now: datetime) -> bool:
    last = backup_log_repo.last_verified_backup(conn, "primary")
    if last is None:
        return True
    return (now - parse_utc_iso(last["at_utc"])) > timedelta(hours=EXIT_BACKUP_MAX_AGE_HOURS)


def run_exit_backup(
    conn: sqlite3.Connection, db_path: Path, now: datetime, primary_dir: Optional[Path], secondary_dir: Optional[Path], keep_count: int
) -> "tuple":
    close_time = _close_time_setting(conn)
    today = compute_business_date(now, close_time)
    file_name = backup_service.daily_file_name(today.isoformat())
    primary, secondary = backup_service.run_backup_pair(conn, db_path, "exit", file_name, primary_dir, secondary_dir, keep_count)
    settings_repo.set_value(conn, "last_exit_backup_utc", to_utc_iso(now))
    return primary, secondary


def run_manual_backup(
    conn: sqlite3.Connection, db_path: Path, now: datetime, primary_dir: Optional[Path], secondary_dir: Optional[Path]
) -> "tuple":
    file_name = backup_service.manual_file_name(now)
    return backup_service.run_backup_pair(
        conn, db_path, "manual", file_name, primary_dir, secondary_dir, backup_service.MANUAL_KEEP_COUNT
    )


def is_backup_stale_for_banner(conn: sqlite3.Connection, now: datetime) -> bool:
    last = backup_log_repo.last_verified_backup(conn, "primary")
    if last is None:
        return True
    return (now - parse_utc_iso(last["at_utc"])) > timedelta(days=STARTUP_BACKUP_WARNING_DAYS)


def retry_secondary_backup(conn: sqlite3.Connection, db_path: Path, secondary_dir: Path, keep_count: int):
    """"إعادة المحاولة للمجلد الثاني": copies the last verified PRIMARY
    backup file to the secondary target (no need to re-run the SQLite
    backup API) and updates the matching day_closures row, if any, so
    its secondary status is no longer stale."""
    last_primary = backup_log_repo.last_verified_backup(conn, "primary")
    if last_primary is None:
        return backup_service.TargetOutcome(status="failed", error=ar.BACKUP_ERROR_FOLDER_UNAVAILABLE)

    source_path = Path(last_primary["path"])
    file_name = source_path.name
    rotation_pattern = (
        backup_service.MANUAL_FILENAME_PATTERN
        if backup_service.MANUAL_FILENAME_PATTERN.match(file_name)
        else backup_service.DAILY_FILENAME_PATTERN
    )
    outcome = backup_service.run_backup_to_target(
        db_path, secondary_dir, file_name, {}, rotation_pattern, keep_count, source_file_to_copy=source_path
    )
    backup_log_repo.log_backup(
        conn, "daily", "secondary", outcome.status, path=outcome.path, size_bytes=outcome.size_bytes,
        sha256=outcome.sha256, verified=outcome.verified, error=outcome.error,
    )

    business_date_text = file_name[len("derby-"):-len(".db")] if file_name.startswith("derby-") else None
    if business_date_text:
        closure = day_closures_repo.get_closure_by_date(conn, business_date_text)
        if closure is not None:
            day_closures_repo.set_backup_status(
                conn, closure["id"], closure["backup_file_name"], closure["backup_primary_status"],
                outcome.status, closure["backup_message"],
            )
    return outcome
