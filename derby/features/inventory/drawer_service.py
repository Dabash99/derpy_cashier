"""Cash drawer ledger business logic: opening the drawer, deposits,
withdrawals, refunds, and physical counts. No UI code here, same split
as orders_service.py / stock_service.py.

The ledger is append-only (drawer_entries rows are never updated or
deleted -- see drawer_repo.py); every correction here is a new row.
The *live* expected-cash balance only ever sums non-historical rows
from the most recent live 'opening' entry onward -- a backfilled
historical row (see migrations.py's Phase 9 backfill) never counts
toward it, so upgrading from an earlier phase does not suddenly claim
the whole cafe's lifetime cash sales are "in the drawer right now".
"""
from __future__ import annotations

import json
import sqlite3
from typing import Dict, List, Optional

from derby.core.db import audit_repo, drawer_repo
from derby.features.inventory.exceptions import InventoryError, NoteRequiredError, OpeningBalanceRequiredError


def has_open_drawer(conn: sqlite3.Connection) -> bool:
    return drawer_repo.get_last_opening_entry(conn) is not None


def expected_cash_piasters(conn: sqlite3.Connection) -> Optional[int]:
    """None means the drawer was never opened (or only historical/
    backfilled data exists) -- the caller (the الخزنة screen) must
    prompt for an opening balance instead of showing a number.

    Sums BOTH drawer_entries (by id, from the opening entry onward --
    unchanged since Phase 9) AND extra_drawer_entries (Part D's parallel
    ledger for entry types drawer_entries' CHECK constraint does not
    allow, e.g. a cash customer-payment) -- by timestamp, since ids
    across the two tables are not comparable. A customer-payment entry
    can only ever be created after some real opening entry already
    exists (the drawer must already be open for there to BE an
    expected-cash concept at all), so this is safe.
    """
    opening = drawer_repo.get_last_opening_entry(conn)
    if opening is None:
        return None
    live_total = drawer_repo.sum_live_entries_from_id(conn, opening["id"])
    extra_total = drawer_repo.sum_extra_entries_since(conn, opening["created_at_utc"])
    return live_total + extra_total


def open_drawer(conn: sqlite3.Connection, opening_amount_piasters: int, user_id: int) -> sqlite3.Row:
    if opening_amount_piasters < 0:
        raise InventoryError("opening amount cannot be negative")
    try:
        entry_id = drawer_repo.create_entry(
            conn, drawer_repo.TYPE_OPENING, opening_amount_piasters, user_id=user_id, commit=False
        )
        audit_repo.log(conn, "drawer_opened", user_id=user_id, details="amount={0}".format(opening_amount_piasters))
    except Exception:
        conn.rollback()
        raise
    return conn.execute("SELECT * FROM drawer_entries WHERE id = ?", (entry_id,)).fetchone()


def _require_note(note: Optional[str]) -> str:
    note = (note or "").strip()
    if not note:
        raise NoteRequiredError("a note is required")
    return note


def record_deposit(conn: sqlite3.Connection, amount_piasters: int, note: str, user_id: int) -> sqlite3.Row:
    if amount_piasters <= 0:
        raise InventoryError("amount must be positive")
    note = _require_note(note)
    try:
        entry_id = drawer_repo.create_entry(
            conn, drawer_repo.TYPE_DEPOSIT, amount_piasters, user_id=user_id, note=note, commit=False
        )
        audit_repo.log(conn, "drawer_deposit", user_id=user_id, details="amount={0} note={1}".format(amount_piasters, note))
    except Exception:
        conn.rollback()
        raise
    return conn.execute("SELECT * FROM drawer_entries WHERE id = ?", (entry_id,)).fetchone()


def record_withdrawal(conn: sqlite3.Connection, amount_piasters: int, note: str, user_id: int) -> sqlite3.Row:
    if amount_piasters <= 0:
        raise InventoryError("amount must be positive")
    note = _require_note(note)
    try:
        entry_id = drawer_repo.create_entry(
            conn, drawer_repo.TYPE_WITHDRAWAL, -amount_piasters, user_id=user_id, note=note, commit=False
        )
        audit_repo.log(conn, "drawer_withdrawal", user_id=user_id, details="amount={0} note={1}".format(amount_piasters, note))
    except Exception:
        conn.rollback()
        raise
    return conn.execute("SELECT * FROM drawer_entries WHERE id = ?", (entry_id,)).fetchone()


def record_cash_refund(
    conn: sqlite3.Connection, amount_piasters: int, note: str, user_id: int, order_id: Optional[int] = None
) -> sqlite3.Row:
    if amount_piasters <= 0:
        raise InventoryError("amount must be positive")
    note = _require_note(note)
    try:
        entry_id = drawer_repo.create_entry(
            conn, drawer_repo.TYPE_REFUND, -amount_piasters, ref_type="order" if order_id else None, ref_id=order_id,
            user_id=user_id, note=note, commit=False,
        )
        audit_repo.log(conn, "drawer_refund", user_id=user_id, details="amount={0} order={1} note={2}".format(amount_piasters, order_id, note))
    except Exception:
        conn.rollback()
        raise
    return conn.execute("SELECT * FROM drawer_entries WHERE id = ?", (entry_id,)).fetchone()


def record_count(
    conn: sqlite3.Connection,
    counted_piasters: int,
    user_id: int,
    denominations: Optional[Dict[str, int]] = None,
    record_adjustment: bool = True,
) -> sqlite3.Row:
    """Compares the counted amount to the live expected cash, stores the
    count + difference, and (if the owner/cashier opts in, the default)
    files a count_adjustment entry so the drawer's running balance
    reflects reality going forward -- the count itself never edits or
    removes anything, per the immutable-ledger rule."""
    expected = expected_cash_piasters(conn)
    if expected is None:
        raise OpeningBalanceRequiredError("the drawer has no opening balance yet")
    denominations_json = json.dumps(denominations) if denominations else None
    try:
        count_id = drawer_repo.create_count(conn, expected, counted_piasters, user_id, denominations_json, commit=False)
        difference = counted_piasters - expected
        if record_adjustment and difference != 0:
            drawer_repo.create_entry(
                conn, drawer_repo.TYPE_COUNT_ADJUSTMENT, difference, ref_type="drawer_count", ref_id=count_id,
                user_id=user_id, note="تسوية جرد الدرج", commit=False,
            )
        audit_repo.log(
            conn, "drawer_count", user_id=user_id,
            details="expected={0} counted={1} difference={2}".format(expected, counted_piasters, difference),
        )
    except Exception:
        conn.rollback()
        raise
    return conn.execute("SELECT * FROM drawer_counts WHERE id = ?", (count_id,)).fetchone()


def count_history(conn: sqlite3.Connection, user_id: Optional[int] = None) -> List[sqlite3.Row]:
    return drawer_repo.list_counts(conn, user_id=user_id)


def recompute_balance_piasters(conn: sqlite3.Connection) -> Optional[int]:
    """The drawer balance must always be recomputable from the ledger
    alone -- this is exactly what expected_cash_piasters already does,
    exposed under the name the spec uses for the repair/verification
    path."""
    return expected_cash_piasters(conn)
