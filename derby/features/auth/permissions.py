"""Who can see/do what. Deliberately tiny and explicit (no roles-as-bitmask
cleverness) so a non-programmer reading this file can see the whole rule.
"""
from __future__ import annotations

from derby.core.db.users_repo import ROLE_CASHIER, ROLE_OWNER


def can_manage_menu(role: str) -> bool:
    """Menu management (Phase 2) is owner-only: cashiers will use the menu
    through the cashier screen itself in Phase 3, not this editor."""
    return role == ROLE_OWNER


def use_pos(role: str) -> bool:
    return role in (ROLE_OWNER, ROLE_CASHIER)


def view_tables(role: str) -> bool:
    return role in (ROLE_OWNER, ROLE_CASHIER)


def manage_tables(role: str) -> bool:
    """Add/rename/reorder/disable tables -- owner only."""
    return role == ROLE_OWNER


def apply_discount_direct(role: str) -> bool:
    """Owner can apply a discount directly; a cashier always needs an
    owner's PIN approval (see orders_service.apply_discount)."""
    return role == ROLE_OWNER


def void_paid_order(role: str) -> bool:
    return role == ROLE_OWNER


def view_sales_today(role: str) -> bool:
    """Both roles can open the sales log; a cashier is restricted to the
    current business date inside the screen itself."""
    return role in (ROLE_OWNER, ROLE_CASHIER)


def view_sales_all_dates(role: str) -> bool:
    return role == ROLE_OWNER


def use_ps(role: str) -> bool:
    return role in (ROLE_OWNER, ROLE_CASHIER)


def manage_ps_devices(role: str) -> bool:
    """Add/rename/set rates/reorder/disable devices -- owner only."""
    return role == ROLE_OWNER


def can_access_expenses(role: str) -> bool:
    return role == ROLE_OWNER


def manage_expenses(role: str) -> bool:
    """Create/void/replace expenses and manage recurring templates and
    expense categories -- same owner-only gate as can_access_expenses,
    kept as a separate name since the spec calls for it explicitly."""
    return role == ROLE_OWNER


def can_access_reports(role: str) -> bool:
    return role == ROLE_OWNER


def view_reports(role: str) -> bool:
    return role == ROLE_OWNER


def export_data(role: str) -> bool:
    return role == ROLE_OWNER


def can_access_settings(role: str) -> bool:
    return role == ROLE_OWNER
