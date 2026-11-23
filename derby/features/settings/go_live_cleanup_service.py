"""Owner-only go-live cleanup ("تصفية بيانات التجربة"): wipes every row
of OPERATIONAL/test data -- orders and everything billed off them
(order items, add-on lines, PlayStation sessions), expenses, supplies,
day closures, and the backup log -- while keeping users, settings, the
menu (categories/products/add-ons/images), PlayStation devices and
their rates, tables, and expense categories/recurring templates.
Resets the invoice counter back to 1.

audit_log is Phase 11 append-only (DB triggers reject any UPDATE/DELETE
on it, see migrations.py's migration 0012) and is deliberately NOT
wiped here anymore, even though every release before Phase 11 did wipe
it -- "no automatic deletion, ever" applies to this cleanup too, not
only to ordinary business operations. A cafe running this before go-live
keeps whatever test-period audit trail it already produced; this is a
one-time, owner-approved action, not routine operation, so that is an
acceptable (and arguably more honest) trade-off.

Safeguards, checked in this order (nothing is deleted unless all three
pass): the owner's PIN, a typed confirmation word, and a verified
backup -- if the backup cannot be taken or does not verify, the whole
call raises and the database is untouched.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict

from derby.core.db import audit_repo, settings_repo
from derby.features.closing import backup_service
from derby.features.pos import owner_approval
from derby.features.settings.exceptions import ConfirmationWordMismatchError

CONFIRMATION_WORD = "تصفية"

# Children before parents, so a single pass works even with
# foreign_keys=ON -- see the FK graph in derby/core/db/migrations.py
# (order_item_addons -> order_items; ps_sessions -> orders & order_items;
# order_items -> orders; supplies -> expenses; expenses.replaced_by_id is
# self-referential, which is why PRAGMA defer_foreign_keys is also used
# below rather than relying on ordering alone).
_TABLES_IN_DELETE_ORDER = (
    "order_item_addons",
    "ps_sessions",
    "order_items",
    "orders",
    "supplies",
    "expenses",
    "day_closures",
    "backup_log",
)


def run_cleanup(
    conn: sqlite3.Connection,
    db_path: Path,
    backup_dir: Path,
    now,
    requesting_user: sqlite3.Row,
    pin: str,
    typed_word: str,
) -> Dict:
    """Raises (in order checked, before anything is touched):
    ApprovalLockedOutError / WrongApprovalPinError (derby.features.pos.exceptions)
    for the PIN, ConfirmationWordMismatchError for the typed word, or
    backup_service.BackupError if the safety backup fails."""
    owner_approval.verify_owner_pin(conn, pin)
    if (typed_word or "").strip() != CONFIRMATION_WORD:
        raise ConfirmationWordMismatchError("confirmation word did not match")

    backup_path = backup_service.verified_pre_cleanup_backup(conn, db_path, backup_dir, now)

    counts = {}
    try:
        conn.execute("PRAGMA defer_foreign_keys = ON")
        for table in _TABLES_IN_DELETE_ORDER:
            counts[table] = conn.execute("SELECT COUNT(*) FROM {0}".format(table)).fetchone()[0]
            conn.execute("DELETE FROM {0}".format(table))
        # audit_log is append-only (Phase 11) -- never wiped here. Its
        # pre-cleanup row count is still reported for the owner's record.
        counts["audit_log_before_cleanup"] = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        settings_repo.set_value(conn, "next_invoice_no", "1")
        audit_repo.log(
            conn, "go_live_cleanup", user_id=requesting_user["id"],
            details="backup={0} counts={1}".format(backup_path, counts),
        )
    except Exception:
        conn.rollback()
        raise
    return {"backup_path": backup_path, "counts": counts}
