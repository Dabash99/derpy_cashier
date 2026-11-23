"""Data access for discount_presets (named percent/fixed discounts
selectable at checkout, owner-managed)."""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from derby.core.utils.time_utils import to_utc_iso, utc_now


def create_preset(conn: sqlite3.Connection, name: str, kind: str, amount: int) -> int:
    cursor = conn.execute(
        "INSERT INTO discount_presets (name, kind, amount, is_active, sort_order, created_at_utc) "
        "SELECT ?, ?, ?, 1, (SELECT COALESCE(MAX(sort_order), 0) + 1 FROM discount_presets), ?",
        (name, kind, amount, to_utc_iso(utc_now())),
    )
    conn.commit()
    return cursor.lastrowid


def get_preset(conn: sqlite3.Connection, preset_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM discount_presets WHERE id = ?", (preset_id,)).fetchone()


def list_presets(conn: sqlite3.Connection, active_only: bool = False) -> List[sqlite3.Row]:
    if active_only:
        return conn.execute("SELECT * FROM discount_presets WHERE is_active = 1 ORDER BY sort_order").fetchall()
    return conn.execute("SELECT * FROM discount_presets ORDER BY sort_order").fetchall()


def update_preset(conn: sqlite3.Connection, preset_id: int, name: str, kind: str, amount: int) -> None:
    conn.execute("UPDATE discount_presets SET name = ?, kind = ?, amount = ? WHERE id = ?", (name, kind, amount, preset_id))
    conn.commit()


def set_active(conn: sqlite3.Connection, preset_id: int, is_active: bool) -> None:
    conn.execute("UPDATE discount_presets SET is_active = ? WHERE id = ?", (1 if is_active else 0, preset_id))
    conn.commit()
