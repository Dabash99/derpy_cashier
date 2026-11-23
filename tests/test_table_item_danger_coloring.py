"""Regression guard: QTableWidgetItem is not a QObject/QWidget -- it has
no setProperty()/stylesheet [role=...] support, unlike every QLabel
elsewhere in this app. A critical audit-log row and an overdue customer
row both render through mark_as_danger() instead (see table_style.py);
this exercises the real rendering path end-to-end so the AttributeError
that pattern used to raise (caught by tools/render_phase11_previews.py,
never by a unit test) cannot silently come back.
"""
from __future__ import annotations

from derby.core import audit_service
from derby.core.db import users_repo
from derby.features.audit.audit_log_screen import AuditLogScreen
from derby.features.customers import customer_service
from derby.features.customers.customers_screen import CustomersScreen


def test_critical_audit_row_renders_without_crashing(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    audit_service.log(db_conn, "order_voided", user=owner, summary_ar="إبطال", severity=audit_service.SEVERITY_CRITICAL)

    screen = AuditLogScreen(db_conn, owner)  # must not raise
    assert screen._table.rowCount() == 1


def test_overdue_customer_row_renders_without_crashing(qapp, db_conn):
    from datetime import date, timedelta

    from derby.core.db import customer_ledger_repo, settings_repo

    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    settings_repo.set_value(db_conn, "customer_overdue_days", "1")
    customer = customer_service.create_customer(db_conn, "محمد", None, None, None, owner)
    old_date = (date.today() - timedelta(days=30)).isoformat()
    customer_ledger_repo.add_entry(db_conn, customer["id"], old_date, "charge", 1000)

    screen = CustomersScreen(db_conn, owner)  # must not raise
    assert screen._table.rowCount() == 1
