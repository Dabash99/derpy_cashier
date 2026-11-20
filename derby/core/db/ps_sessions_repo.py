"""Data access for the `ps_sessions` table (timed PlayStation sessions).

Pure CRUD/queries only -- the pricing/minimum-visit rules and the
start/switch/stop orchestration live in derby/features/playstation/ps_service.py.
A session is never deleted: removing its order line marks it voided
(voided_at_utc/voided_by) instead, per the spec.
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from derby.core.utils.time_utils import to_utc_iso, utc_now


def create_session(
    conn: sqlite3.Connection,
    device_id: int,
    order_id: int,
    mode: str,
    started_at_utc: str,
    rate_snapshot_piasters_per_hour: int,
    device_name_snapshot: str,
    started_by: int,
    commit: bool = True,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO ps_sessions (
            device_id, order_id, mode, started_at_utc, rate_snapshot_piasters_per_hour,
            device_name_snapshot, is_final, started_by
        ) VALUES (?, ?, ?, ?, ?, ?, 0, ?)
        """,
        (device_id, order_id, mode, started_at_utc, rate_snapshot_piasters_per_hour, device_name_snapshot, started_by),
    )
    if commit:
        conn.commit()
    return cursor.lastrowid


def get_session(conn: sqlite3.Connection, session_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM ps_sessions WHERE id = ?", (session_id,)).fetchone()


def get_running_session(conn: sqlite3.Connection, device_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM ps_sessions WHERE device_id = ? AND stopped_at_utc IS NULL", (device_id,)
    ).fetchone()


def list_sessions_for_order(conn: sqlite3.Connection, order_id: int) -> List[sqlite3.Row]:
    return conn.execute("SELECT * FROM ps_sessions WHERE order_id = ? ORDER BY id", (order_id,)).fetchall()


def sum_billed_minutes_for_order(conn: sqlite3.Connection, order_id: int) -> int:
    """Total billed minutes of this visit's already-stopped, non-voided
    sessions -- used to apply the per-visit minimum only once."""
    row = conn.execute(
        "SELECT COALESCE(SUM(billed_minutes), 0) AS total FROM ps_sessions "
        "WHERE order_id = ? AND stopped_at_utc IS NOT NULL AND voided_at_utc IS NULL",
        (order_id,),
    ).fetchone()
    return row["total"]


def stop_session(
    conn: sqlite3.Connection,
    session_id: int,
    stopped_at_utc: str,
    actual_minutes: int,
    billed_minutes: int,
    price_piasters: int,
    order_item_id: int,
    is_final: bool,
    stopped_by: int,
    commit: bool = True,
) -> None:
    conn.execute(
        """
        UPDATE ps_sessions
        SET stopped_at_utc = ?, actual_minutes = ?, billed_minutes = ?, price_piasters = ?,
            order_item_id = ?, is_final = ?, stopped_by = ?
        WHERE id = ?
        """,
        (stopped_at_utc, actual_minutes, billed_minutes, price_piasters, order_item_id, 1 if is_final else 0, stopped_by, session_id),
    )
    if commit:
        conn.commit()


def link_order_item(conn: sqlite3.Connection, session_id: int, order_item_id: int, commit: bool = True) -> None:
    """Startup-repair path only: attaches the order line to a session that
    was stopped but never got one (e.g. a crash right after stop)."""
    conn.execute("UPDATE ps_sessions SET order_item_id = ? WHERE id = ?", (order_item_id, session_id))
    if commit:
        conn.commit()


def mark_voided(conn: sqlite3.Connection, session_id: int, voided_by: int, commit: bool = True) -> None:
    # order_item_id is cleared too: the line it pointed to is about to be
    # deleted, and a dangling FK would block that delete.
    conn.execute(
        "UPDATE ps_sessions SET voided_at_utc = ?, voided_by = ?, order_item_id = NULL WHERE id = ?",
        (to_utc_iso(utc_now()), voided_by, session_id),
    )
    if commit:
        conn.commit()


def update_start_time(conn: sqlite3.Connection, session_id: int, new_started_at_utc: str, commit: bool = True) -> None:
    conn.execute("UPDATE ps_sessions SET started_at_utc = ? WHERE id = ?", (new_started_at_utc, session_id))
    if commit:
        conn.commit()


def count_running_sessions(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM ps_sessions WHERE stopped_at_utc IS NULL").fetchone()
    return row["n"]


def list_stopped_sessions_without_order_item(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM ps_sessions WHERE stopped_at_utc IS NOT NULL AND order_item_id IS NULL ORDER BY id"
    ).fetchall()
