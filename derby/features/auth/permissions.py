"""Who can see/do what. Deliberately tiny and explicit (no roles-as-bitmask
cleverness) so a non-programmer reading this file can see the whole rule.
"""
from __future__ import annotations

from derby.core.db.users_repo import ROLE_CASHIER, ROLE_OWNER


def can_access_menu(role: str) -> bool:
    return role in (ROLE_OWNER, ROLE_CASHIER)


def can_access_pos(role: str) -> bool:
    return role in (ROLE_OWNER, ROLE_CASHIER)


def can_access_tables(role: str) -> bool:
    return role in (ROLE_OWNER, ROLE_CASHIER)


def can_access_playstation(role: str) -> bool:
    return role in (ROLE_OWNER, ROLE_CASHIER)


def can_access_expenses(role: str) -> bool:
    return role == ROLE_OWNER


def can_access_reports(role: str) -> bool:
    return role == ROLE_OWNER


def can_access_settings(role: str) -> bool:
    return role == ROLE_OWNER
