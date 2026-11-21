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


def view_supplies(role: str) -> bool:
    return role in (ROLE_OWNER, ROLE_CASHIER)


def view_daily_stats(role: str) -> bool:
    """إحصائيات اليوم is visible to both roles; profit/expenses/net
    figures within it are gated separately by view_reports (owner only),
    same privacy class as the Reports screen's own numbers."""
    return role in (ROLE_OWNER, ROLE_CASHIER)


def manage_supplies_costs(role: str) -> bool:
    """Entering a real cost and converting a bought item into an expense
    is a money decision -- owner only. Adding/editing/marking an item
    bought is open to a cashier (view_supplies)."""
    return role == ROLE_OWNER


# --- Phase 9: inventory, drawer, profit ---------------------------------


def manage_inventory(role: str) -> bool:
    """Stock items, recipes, purchases, suppliers, waste, stocktake --
    all a cost/money decision, owner only (see CLAUDE.md hard constraint
    6: inventory/profit screens and cost data are owner-only)."""
    return role == ROLE_OWNER


def view_drawer(role: str) -> bool:
    """Both roles can open الخزنة, but a cashier's view is cash-only --
    no costs, no stock value (see view_goods_review)."""
    return role in (ROLE_OWNER, ROLE_CASHIER)


def manage_drawer(role: str) -> bool:
    """Opening balance, deposits/withdrawals, and drawer counts are cash
    handling -- open to both roles, same as the drawer being a shared
    till a cashier works from day to day."""
    return role in (ROLE_OWNER, ROLE_CASHIER)


def view_goods_review(role: str) -> bool:
    """Stock value, unpaid supplier balances -- owner only, same privacy
    class as view_reports."""
    return role == ROLE_OWNER


def view_profit_report(role: str) -> bool:
    return role == ROLE_OWNER


def view_cost_data(role: str) -> bool:
    """cost_at_sale_piasters / recipe cost+margin, anywhere it would show
    in the UI (invoice line, recipe editor) -- owner only."""
    return role == ROLE_OWNER
