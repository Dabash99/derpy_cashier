"""PIN-based owner approval for cashier-restricted actions (discount,
cancelling a non-empty order). Deliberately reuses the Phase 1 global
login lockout (derby/features/auth/lockout.py) instead of a separate
counter, exactly as specified: a wrong PIN here counts the same as a
wrong PIN at the login screen.
"""
from __future__ import annotations

import sqlite3

from derby.core.db import users_repo
from derby.core.utils.pin_hash import verify_pin
from derby.features.auth import lockout
from derby.features.pos.exceptions import ApprovalLockedOutError, WrongApprovalPinError


def verify_owner_pin(conn: sqlite3.Connection, pin: str) -> sqlite3.Row:
    """Returns the matching active owner's row, or raises.

    Only active OWNER users are searched -- since PINs are unique across
    active users (enforced at creation), a cashier's own PIN can never
    match here, with no extra special-casing needed.
    """
    remaining = lockout.get_lock_remaining(conn)
    if remaining is not None:
        raise ApprovalLockedOutError("login is locked: {0} seconds remaining".format(int(remaining.total_seconds())))

    for user in users_repo.list_users(conn, active_only=True):
        if user["role"] != users_repo.ROLE_OWNER:
            continue
        if verify_pin(pin, user["pin_salt"], user["pin_hash"]):
            lockout.reset_failed_attempts(conn)
            return user

    lockout.record_failed_attempt(conn)
    raise WrongApprovalPinError("no active owner matches the given PIN")
