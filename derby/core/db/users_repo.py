"""Data access for the users table.

PINs identify a user (there's no username at login), so this module is
also where "is this PIN already in use by another active user" is
decided — one query, one place.
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from derby.core.utils import pin_hash
from derby.core.utils.time_utils import to_utc_iso, utc_now

ROLE_OWNER = "owner"
ROLE_CASHIER = "cashier"


def create_user(conn: sqlite3.Connection, name: str, role: str, pin: str) -> int:
    salt = pin_hash.generate_salt()
    hashed = pin_hash.hash_pin(pin, salt)
    cursor = conn.execute(
        """
        INSERT INTO users (name, role, pin_hash, pin_salt, is_active, failed_attempts, created_at_utc)
        VALUES (?, ?, ?, ?, 1, 0, ?)
        """,
        (name, role, hashed, salt, to_utc_iso(utc_now())),
    )
    conn.commit()
    return cursor.lastrowid


def get_user(conn: sqlite3.Connection, user_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def list_users(conn: sqlite3.Connection, active_only: bool = False) -> List[sqlite3.Row]:
    if active_only:
        return conn.execute("SELECT * FROM users WHERE is_active = 1 ORDER BY id").fetchall()
    return conn.execute("SELECT * FROM users ORDER BY id").fetchall()


def has_any_users(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
    return row["n"] > 0


def find_active_user_by_pin(conn: sqlite3.Connection, pin: str) -> Optional[sqlite3.Row]:
    for user in list_users(conn, active_only=True):
        if pin_hash.verify_pin(pin, user["pin_salt"], user["pin_hash"]):
            return user
    return None


def is_pin_in_use(conn: sqlite3.Connection, pin: str, exclude_user_id: Optional[int] = None) -> bool:
    for user in list_users(conn, active_only=True):
        if exclude_user_id is not None and user["id"] == exclude_user_id:
            continue
        if pin_hash.verify_pin(pin, user["pin_salt"], user["pin_hash"]):
            return True
    return False


def rename_user(conn: sqlite3.Connection, user_id: int, new_name: str) -> None:
    conn.execute("UPDATE users SET name = ? WHERE id = ?", (new_name, user_id))
    conn.commit()


def change_pin(conn: sqlite3.Connection, user_id: int, new_pin: str) -> None:
    salt = pin_hash.generate_salt()
    hashed = pin_hash.hash_pin(new_pin, salt)
    conn.execute(
        "UPDATE users SET pin_hash = ?, pin_salt = ? WHERE id = ?",
        (hashed, salt, user_id),
    )
    conn.commit()


def set_active(conn: sqlite3.Connection, user_id: int, is_active: bool) -> None:
    conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if is_active else 0, user_id))
    conn.commit()


def count_active_owners(conn: sqlite3.Connection, exclude_user_id: Optional[int] = None) -> int:
    rows = conn.execute(
        "SELECT id FROM users WHERE role = ? AND is_active = 1", (ROLE_OWNER,)
    ).fetchall()
    return len([row for row in rows if row["id"] != exclude_user_id])
