"""Clock in/out (PIN-confirmed in the UI, not here) and manual
corrections (owner only, reason required -- audited)."""
from __future__ import annotations

import sqlite3
from datetime import time as time_of_day
from typing import List, Optional

from derby.core import audit_service
from derby.core.db import attendance_repo, settings_repo
from derby.core.utils.business_date import business_date as compute_business_date
from derby.core.utils.time_utils import parse_utc_iso, utc_now
from derby.features.employees.exceptions import (
    AlreadyClockedInError,
    CorrectionReasonRequiredError,
    NotClockedInError,
)


def _today_business_date(conn: sqlite3.Connection) -> str:
    text = settings_repo.get(conn, "business_close_time", "23:59") or "23:59"
    hour_str, minute_str = text.split(":")
    close_time = time_of_day(int(hour_str), int(minute_str))
    return compute_business_date(utc_now(), close_time).isoformat()


def clock_in(conn: sqlite3.Connection, employee_id: int, acting_user: sqlite3.Row) -> sqlite3.Row:
    if attendance_repo.get_open_attendance(conn, employee_id) is not None:
        raise AlreadyClockedInError("employee {0} is already clocked in".format(employee_id))
    business_date = _today_business_date(conn)
    attendance_id = attendance_repo.clock_in(conn, employee_id, business_date)
    audit_service.log(
        conn, "attendance_clock_in", user=acting_user, entity_type="employee", entity_id=employee_id,
        summary_ar="تسجيل حضور", business_date=business_date,
    )
    return attendance_repo.get_attendance(conn, attendance_id)


def clock_out(conn: sqlite3.Connection, employee_id: int, acting_user: sqlite3.Row) -> sqlite3.Row:
    open_row = attendance_repo.get_open_attendance(conn, employee_id)
    if open_row is None:
        raise NotClockedInError("employee {0} is not clocked in".format(employee_id))
    attendance_repo.clock_out(conn, open_row["id"])
    audit_service.log(
        conn, "attendance_clock_out", user=acting_user, entity_type="employee", entity_id=employee_id,
        summary_ar="تسجيل انصراف", business_date=open_row["business_date"],
    )
    return attendance_repo.get_attendance(conn, open_row["id"])


def correct(
    conn: sqlite3.Connection,
    attendance_id: int,
    clock_in_utc: Optional[str],
    clock_out_utc: Optional[str],
    reason: str,
    requesting_user: sqlite3.Row,
) -> sqlite3.Row:
    reason = (reason or "").strip()
    if not reason:
        raise CorrectionReasonRequiredError("a reason is required")
    before = attendance_repo.get_attendance(conn, attendance_id)
    attendance_repo.correct(conn, attendance_id, clock_in_utc, clock_out_utc, reason, requesting_user["id"])
    audit_service.log(
        conn, "attendance_corrected", user=requesting_user, entity_type="attendance", entity_id=attendance_id,
        summary_ar="تعديل حضور/انصراف: {0}".format(reason),
        details={
            "before": {"clock_in_utc": before["clock_in_utc"], "clock_out_utc": before["clock_out_utc"]},
            "after": {"clock_in_utc": clock_in_utc, "clock_out_utc": clock_out_utc},
            "reason": reason,
        },
        severity=audit_service.SEVERITY_WARNING,
    )
    return attendance_repo.get_attendance(conn, attendance_id)


def hours_for_period(conn: sqlite3.Connection, employee_id: int, start_date: str, end_date: str) -> float:
    total_seconds = 0.0
    for row in attendance_repo.list_for_employee(conn, employee_id, start_date, end_date):
        if not row["clock_in_utc"]:
            continue
        clock_out = row["clock_out_utc"] or utc_now().isoformat()
        start = parse_utc_iso(row["clock_in_utc"])
        end = parse_utc_iso(clock_out) if isinstance(clock_out, str) else clock_out
        total_seconds += (end - start).total_seconds()
    return round(total_seconds / 3600.0, 2)


def list_for_employee(conn: sqlite3.Connection, employee_id: int, start_date: str, end_date: str) -> List[sqlite3.Row]:
    return attendance_repo.list_for_employee(conn, employee_id, start_date, end_date)
