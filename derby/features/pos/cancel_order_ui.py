"""Shared "إلغاء الطلب" confirmation + owner-approval-if-needed flow --
used by the Cashier screen's top bar and the Tables screen's
table/takeaway cards, kept in one place so the two can't drift apart.
"""
from __future__ import annotations

import sqlite3

from PySide2.QtWidgets import QMessageBox, QWidget

from derby.core.db import orders_repo, users_repo
from derby.core.i18n import ar
from derby.features.pos import orders_service
from derby.features.pos.exceptions import ApprovalLockedOutError, WrongApprovalPinError
from derby.features.pos.owner_pin_prompt import ask_for_owner_pin


def confirm_and_cancel_order(parent: QWidget, conn: sqlite3.Connection, order_id: int, user: sqlite3.Row) -> bool:
    """Asks for confirmation (and the owner's PIN if a cashier is
    cancelling a non-empty order), then cancels. Returns True only if
    the order was actually cancelled."""
    confirmed = QMessageBox.question(parent, ar.POS_CANCEL_CONFIRM_TITLE, ar.POS_CANCEL_CONFIRM_MESSAGE)
    if confirmed != QMessageBox.Yes:
        return False

    has_items = len(orders_repo.list_order_items(conn, order_id)) > 0
    approving_pin = None
    if has_items and user["role"] != users_repo.ROLE_OWNER:
        approving_pin = ask_for_owner_pin(parent)
        if approving_pin is None:
            return False

    try:
        orders_service.cancel(conn, order_id, user, approving_pin=approving_pin)
    except WrongApprovalPinError:
        QMessageBox.warning(parent, ar.GENERIC_ERROR_TITLE, ar.DISCOUNT_ERROR_WRONG_PIN)
        return False
    except ApprovalLockedOutError:
        QMessageBox.warning(parent, ar.GENERIC_ERROR_TITLE, ar.LOGIN_ERROR_LOCKED.format(minutes=0, seconds=0))
        return False
    return True
