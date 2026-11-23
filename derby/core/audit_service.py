"""The single entry point every SERVICE module (not UI code) calls to
append a row to سجل العمليات (audit_log). Builds on audit_repo.record,
adding: a user-name snapshot read straight off the sqlite3.Row the
caller already has (so the service doesn't have to pass both an id and
a name), severity validation, and the same "never raises" guarantee as
audit_repo.log -- a failure here must never block the business
operation a service already committed.

UI widgets must not call this directly; they call into a service, which
already has the entity ids and before/after values this module needs.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, Optional

from derby.core.db import audit_repo

SEVERITY_INFO = audit_repo.SEVERITY_INFO
SEVERITY_WARNING = audit_repo.SEVERITY_WARNING
SEVERITY_CRITICAL = audit_repo.SEVERITY_CRITICAL


def log(
    conn: sqlite3.Connection,
    action: str,
    user: Optional[sqlite3.Row] = None,
    user_id: Optional[int] = None,
    business_date: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    summary_ar: str = "",
    details: Optional[Dict[str, Any]] = None,
    severity: str = SEVERITY_INFO,
) -> None:
    resolved_user_id = user_id
    resolved_user_name = None
    if user is not None:
        if resolved_user_id is None:
            resolved_user_id = user["id"]
        resolved_user_name = user["name"]
    try:
        audit_repo.record(
            conn,
            action,
            user_id=resolved_user_id,
            user_name=resolved_user_name,
            business_date=business_date,
            entity_type=entity_type,
            entity_id=entity_id,
            summary_ar=summary_ar,
            details=details,
            severity=severity,
            commit=True,
        )
    except Exception as exc:  # noqa: BLE001 -- see module docstring
        try:
            conn.commit()  # persist whatever the business operation already staged
        except Exception:
            pass
        audit_repo._report_failure(action, exc)  # noqa: SLF001 -- same module family, shared helper
