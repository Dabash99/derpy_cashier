"""Data access for the audit_log table.

Append-only at the DB level since migration 0012 (UPDATE/DELETE both
raise via triggers) -- this module only ever INSERTs. `record()` is the
full write (every Phase 11 Part A column); `log()` is the original
Phase 1-10 convenience wrapper, kept so the ~25 existing call sites
across the services layer need no change, but now resilient: a failure
here is caught, reported to the local error log, and never re-raised --
the business operation that already wrote its own rows must never be
rolled back just because the audit write itself failed. New call sites
should prefer `derby.core.audit_service.log`, which adds user-name
snapshotting and severity validation on top of `record()`.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from derby.core.utils.business_date import DEFAULT_CLOSE_TIME
from derby.core.utils.business_date import business_date as compute_business_date
from derby.core.utils.time_utils import to_utc_iso, utc_now

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"
VALID_SEVERITIES = (SEVERITY_INFO, SEVERITY_WARNING, SEVERITY_CRITICAL)

PAGE_SIZE = 50


def _report_failure(action: str, exc: Exception) -> None:
    # Imported lazily -- error_log pulls in logging.handlers, no need to
    # pay for that at every ordinary successful audit write.
    from derby.core.utils import error_log

    try:
        error_log.log_exception(type(exc), exc, exc.__traceback__)
    except Exception:
        pass  # the error log itself must never crash the caller either


def record(
    conn: sqlite3.Connection,
    action: str,
    user_id: Optional[int] = None,
    user_name: Optional[str] = None,
    business_date: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    summary_ar: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    details_text: Optional[str] = None,
    severity: str = SEVERITY_INFO,
    commit: bool = True,
) -> int:
    """The raw INSERT -- can raise (a disk-full write, the append-only
    triggers refusing something that is a bug elsewhere, etc). Callers
    that must never block the surrounding business operation go through
    `log()` or `derby.core.audit_service.log` instead, not this directly,
    except in tests that specifically want to see a failure propagate.
    """
    if severity not in VALID_SEVERITIES:
        severity = SEVERITY_INFO
    if business_date is None:
        business_date = compute_business_date(utc_now(), DEFAULT_CLOSE_TIME).isoformat()
    details_json = None
    if details is not None:
        details_json = json.dumps(details, ensure_ascii=False, default=str)
    legacy_details = details_text if details_text is not None else (summary_ar or "")
    cursor = conn.execute(
        """
        INSERT INTO audit_log (
            at_utc, user_id, action, details, business_date, user_name,
            entity_type, entity_id, summary_ar, details_json, severity
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            to_utc_iso(utc_now()), user_id, action, legacy_details, business_date, user_name,
            entity_type, entity_id, summary_ar, details_json, severity,
        ),
    )
    if commit:
        conn.commit()
    return cursor.lastrowid


def log(conn: sqlite3.Connection, action: str, user_id: Optional[int] = None, details: str = "", commit: bool = True) -> None:
    """Legacy convenience wrapper used throughout Phase 1-10 code. Never
    raises: a failure is swallowed (and reported to the local error log)
    so an audit write can never undo the business change that already
    happened in the same transaction, commit=False writes included --
    on failure this still commits whatever the caller already staged.
    """
    try:
        record(conn, action, user_id=user_id, details_text=details, commit=commit)
    except Exception as exc:  # noqa: BLE001 -- see module docstring
        if commit:
            try:
                conn.commit()
            except Exception:
                pass
        _report_failure(action, exc)


def list_entries(
    conn: sqlite3.Connection,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    severity: Optional[str] = None,
    search_text: Optional[str] = None,
    page: int = 0,
    page_size: int = PAGE_SIZE,
) -> List[sqlite3.Row]:
    clauses = []
    params: list = []
    if start_date is not None:
        clauses.append("business_date >= ?")
        params.append(start_date)
    if end_date is not None:
        clauses.append("business_date <= ?")
        params.append(end_date)
    if user_id is not None:
        clauses.append("user_id = ?")
        params.append(user_id)
    if action is not None:
        clauses.append("action = ?")
        params.append(action)
    if entity_type is not None:
        clauses.append("entity_type = ?")
        params.append(entity_type)
    if severity is not None:
        clauses.append("severity = ?")
        params.append(severity)
    if search_text:
        clauses.append("(summary_ar LIKE ? OR details LIKE ? OR action LIKE ? OR user_name LIKE ?)")
        like = "%{0}%".format(search_text)
        params.extend([like, like, like, like])
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    query = (
        "SELECT * FROM audit_log" + where + " ORDER BY id DESC LIMIT ? OFFSET ?"
    )
    params.extend([page_size, page * page_size])
    return conn.execute(query, tuple(params)).fetchall()


def count_entries(
    conn: sqlite3.Connection,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_id: Optional[int] = None,
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    severity: Optional[str] = None,
    search_text: Optional[str] = None,
) -> int:
    clauses = []
    params: list = []
    if start_date is not None:
        clauses.append("business_date >= ?")
        params.append(start_date)
    if end_date is not None:
        clauses.append("business_date <= ?")
        params.append(end_date)
    if user_id is not None:
        clauses.append("user_id = ?")
        params.append(user_id)
    if action is not None:
        clauses.append("action = ?")
        params.append(action)
    if entity_type is not None:
        clauses.append("entity_type = ?")
        params.append(entity_type)
    if severity is not None:
        clauses.append("severity = ?")
        params.append(severity)
    if search_text:
        clauses.append("(summary_ar LIKE ? OR details LIKE ? OR action LIKE ? OR user_name LIKE ?)")
        like = "%{0}%".format(search_text)
        params.extend([like, like, like, like])
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    row = conn.execute("SELECT COUNT(*) AS n FROM audit_log" + where, tuple(params)).fetchone()
    return row["n"]


def distinct_actions(conn: sqlite3.Connection) -> List[str]:
    return [row["action"] for row in conn.execute("SELECT DISTINCT action FROM audit_log ORDER BY action").fetchall()]


def get_entry(conn: sqlite3.Connection, entry_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM audit_log WHERE id = ?", (entry_id,)).fetchone()
