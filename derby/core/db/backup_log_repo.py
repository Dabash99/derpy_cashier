"""Data access for the backup_log table -- one row per attempted backup
write (primary or secondary), kept forever as an audit trail of what was
backed up, when, and whether it verified correctly.
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from derby.core.utils.time_utils import to_utc_iso, utc_now


def log_backup(
    conn: sqlite3.Connection,
    kind: str,
    target: str,
    status: str,
    path: Optional[str] = None,
    size_bytes: Optional[int] = None,
    sha256: Optional[str] = None,
    verified: bool = False,
    error: Optional[str] = None,
    app_version: Optional[str] = None,
    schema_version: Optional[int] = None,
    commit: bool = True,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO backup_log (at_utc, kind, target, path, size_bytes, sha256, verified, status, error, app_version, schema_version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            to_utc_iso(utc_now()), kind, target, path, size_bytes, sha256, 1 if verified else 0, status, error,
            app_version, schema_version,
        ),
    )
    if commit:
        conn.commit()
    return cursor.lastrowid


def last_verified_backup(conn: sqlite3.Connection, target: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM backup_log WHERE target = ? AND verified = 1 ORDER BY at_utc DESC LIMIT 1", (target,)
    ).fetchone()


def list_backups(conn: sqlite3.Connection, target: Optional[str] = None, limit: Optional[int] = None) -> List[sqlite3.Row]:
    query = "SELECT * FROM backup_log"
    params: tuple = ()
    if target is not None:
        query += " WHERE target = ?"
        params = (target,)
    query += " ORDER BY at_utc DESC"
    if limit is not None:
        query += " LIMIT {0}".format(int(limit))
    return conn.execute(query, params).fetchall()
