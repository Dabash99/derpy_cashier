"""Offscreen widget smoke test for سجل العمليات."""
from __future__ import annotations

from derby.core.db import users_repo
from derby.core.db.connection import connect  # noqa: F401 -- ensures PySide2 import order matches other tests
from derby.features.audit.audit_log_screen import AuditLogScreen


def test_screen_builds_and_lists_entries(qapp, db_conn):
    from derby.core import audit_service

    owner_id = users_repo.create_user(db_conn, "محمد", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    audit_service.log(db_conn, "login", user=owner, entity_type="user", entity_id=owner_id, summary_ar="تسجيل دخول")

    screen = AuditLogScreen(db_conn, owner)
    assert screen._table.rowCount() == 1
    assert screen._result_count_label.text()


def test_pagination_controls_disable_correctly_on_single_page(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "محمد", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    screen = AuditLogScreen(db_conn, owner)
    assert screen._prev_button.isEnabled() is False
    assert screen._next_button.isEnabled() is False


def test_detail_dialog_opens_without_crashing(qapp, db_conn):
    from derby.core import audit_service
    from derby.features.audit.audit_detail_dialog import AuditDetailDialog

    owner_id = users_repo.create_user(db_conn, "محمد", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    audit_service.log(
        db_conn, "order_voided", user=owner, entity_type="order", entity_id=1,
        summary_ar="إبطال فاتورة", details={"before": "paid", "after": "void"}, severity="critical",
    )
    from derby.core.db import audit_repo
    entry = audit_repo.list_entries(db_conn)[0]
    dialog = AuditDetailDialog(entry)
    assert dialog is not None
