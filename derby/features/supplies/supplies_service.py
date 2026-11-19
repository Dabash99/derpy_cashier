"""Supplies (shopping list) business logic -- not a stock/inventory
system, just a running "things to buy" list. No UI code here, same split
as derby/features/expenses/expenses_service.py.

Converting a bought item into an expense is owner-only (entering a real
cost and creating a row in the expenses table is a money decision), but
adding/editing/marking bought is open to any cashier.
"""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from derby.core.db import audit_repo, supplies_repo
from derby.features.expenses import expenses_service
from derby.features.supplies.exceptions import InvalidCostError, SupplyNameRequiredError, SupplyNotBoughtError

PRIORITY_NORMAL = supplies_repo.PRIORITY_NORMAL
PRIORITY_URGENT = supplies_repo.PRIORITY_URGENT
STATUS_NEEDED = supplies_repo.STATUS_NEEDED
STATUS_BOUGHT = supplies_repo.STATUS_BOUGHT
STATUS_DROPPED = supplies_repo.STATUS_DROPPED


def _clean(text: Optional[str]) -> Optional[str]:
    text = (text or "").strip()
    return text or None


def add_supply(
    conn: sqlite3.Connection,
    name: str,
    quantity_note: Optional[str],
    priority: str,
    note: Optional[str],
    user_id: int,
) -> sqlite3.Row:
    name = (name or "").strip()
    if not name:
        raise SupplyNameRequiredError("a name is required")
    try:
        supply_id = supplies_repo.create_supply(conn, name, _clean(quantity_note), priority, _clean(note), user_id, commit=False)
        audit_repo.log(conn, "supply_added", user_id=user_id, details="supply={0} name={1}".format(supply_id, name))
    except Exception:
        conn.rollback()
        raise
    return supplies_repo.get_supply(conn, supply_id)


def update_supply(
    conn: sqlite3.Connection,
    supply_id: int,
    name: str,
    quantity_note: Optional[str],
    priority: str,
    note: Optional[str],
    user_id: int,
) -> sqlite3.Row:
    name = (name or "").strip()
    if not name:
        raise SupplyNameRequiredError("a name is required")
    try:
        supplies_repo.update_supply(conn, supply_id, name, _clean(quantity_note), priority, _clean(note), commit=False)
        audit_repo.log(conn, "supply_updated", user_id=user_id, details="supply={0}".format(supply_id))
    except Exception:
        conn.rollback()
        raise
    return supplies_repo.get_supply(conn, supply_id)


def mark_bought(conn: sqlite3.Connection, supply_id: int, user_id: int) -> sqlite3.Row:
    try:
        supplies_repo.mark_bought(conn, supply_id, user_id, commit=False)
        audit_repo.log(conn, "supply_bought", user_id=user_id, details="supply={0}".format(supply_id))
    except Exception:
        conn.rollback()
        raise
    return supplies_repo.get_supply(conn, supply_id)


def cancel_supply(conn: sqlite3.Connection, supply_id: int, user_id: int) -> sqlite3.Row:
    """"إلغاء" -- the item is no longer needed (status 'dropped'), not a
    delete, so it stays in the audit trail and history."""
    try:
        supplies_repo.mark_dropped(conn, supply_id, commit=False)
        audit_repo.log(conn, "supply_dropped", user_id=user_id, details="supply={0}".format(supply_id))
    except Exception:
        conn.rollback()
        raise
    return supplies_repo.get_supply(conn, supply_id)


def convert_to_expense(
    conn: sqlite3.Connection,
    supply_id: int,
    category_id: int,
    cost_piasters: int,
    requesting_user: sqlite3.Row,
) -> sqlite3.Row:
    """Owner-only: creates a real expense row from a bought supply and
    links the two. The caller's UI must already restrict this action to
    the owner (view_supplies vs manage_supplies_costs), this is the
    service-level safety net."""
    from derby.features.auth import permissions

    if not permissions.manage_supplies_costs(requesting_user["role"]):
        from derby.features.pos.exceptions import PermissionDeniedError

        raise PermissionDeniedError("only the owner can convert a supply into an expense")

    supply = supplies_repo.get_supply(conn, supply_id)
    if supply is None or supply["status"] != STATUS_BOUGHT:
        raise SupplyNotBoughtError("only a bought supply can be converted into an expense")
    if cost_piasters <= 0:
        raise InvalidCostError("cost must be greater than zero")

    expense = expenses_service.create_expense(
        conn, category_id, cost_piasters, expenses_service.today_business_date(conn),
        description=supply["name"], user_id=requesting_user["id"],
    )
    try:
        supplies_repo.set_cost_and_expense(conn, supply_id, cost_piasters, expense["id"], commit=False)
        audit_repo.log(
            conn, "supply_converted_to_expense", user_id=requesting_user["id"],
            details="supply={0} expense={1} cost={2}".format(supply_id, expense["id"], cost_piasters),
        )
    except Exception:
        conn.rollback()
        raise
    return supplies_repo.get_supply(conn, supply_id)


def list_for_display(conn: sqlite3.Connection, status: Optional[str] = None) -> List[sqlite3.Row]:
    return supplies_repo.list_supplies(conn, status=status)


def copy_list_as_text(conn: sqlite3.Connection) -> str:
    """Plain Arabic text of every still-needed item (urgent first), for
    "نسخ القائمة" / the WhatsApp hand-off."""
    needed = supplies_repo.list_supplies(conn, status=STATUS_NEEDED)
    lines = []
    for supply in needed:
        line = supply["name"]
        if supply["quantity_note"]:
            line = "{0} ({1})".format(line, supply["quantity_note"])
        if supply["priority"] == PRIORITY_URGENT:
            line = "{0} - {1}".format(line, PRIORITY_URGENT)
        lines.append("- {0}".format(line))
    return "\n".join(lines)
