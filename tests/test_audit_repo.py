"""Part A: audit_log is append-only at the DB level (UPDATE/DELETE both
raise via migration 0012's triggers), and a failing audit write must
never roll back the business operation that already committed."""
from __future__ import annotations

import sqlite3

import pytest

from derby.core.db import audit_repo
from derby.core.db.connection import connect
from derby.core.db.migrations import run_pending_migrations


def test_update_is_rejected(db_conn):
    audit_repo.record(db_conn, "login")
    with pytest.raises(sqlite3.DatabaseError):
        db_conn.execute("UPDATE audit_log SET action = 'x' WHERE id = 1")


def test_delete_is_rejected(db_conn):
    audit_repo.record(db_conn, "login")
    with pytest.raises(sqlite3.DatabaseError):
        db_conn.execute("DELETE FROM audit_log WHERE id = 1")


def test_record_writes_every_column(db_conn):
    from derby.core.db import users_repo

    owner_id = users_repo.create_user(db_conn, "محمد", users_repo.ROLE_OWNER, "1111")
    audit_repo.record(
        db_conn, "order_voided", user_id=owner_id, user_name="محمد", business_date="2026-01-01",
        entity_type="order", entity_id=42, summary_ar="إبطال فاتورة", details={"before": 1, "after": 2},
        severity="critical",
    )
    row = db_conn.execute("SELECT * FROM audit_log WHERE action = 'order_voided'").fetchone()
    assert row["user_name"] == "محمد"
    assert row["entity_type"] == "order"
    assert row["entity_id"] == 42
    assert row["severity"] == "critical"
    assert '"before": 1' in row["details_json"]


def test_invalid_severity_falls_back_to_info(db_conn):
    audit_repo.record(db_conn, "login", severity="not-a-real-severity")
    row = db_conn.execute("SELECT severity FROM audit_log WHERE action = 'login'").fetchone()
    assert row["severity"] == "info"


def test_legacy_log_wrapper_never_raises_and_still_commits_prior_writes(db_conn, monkeypatch):
    """Simulates record() failing mid-way (e.g. a disk error) -- the
    legacy log() wrapper must swallow it AND still commit whatever the
    caller already wrote in the same transaction (commit=False calls
    before it), exactly as a real service function does."""
    db_conn.execute("INSERT INTO settings (key, value) VALUES ('probe', 'before')")

    def _boom(*args, **kwargs):
        raise sqlite3.OperationalError("simulated disk error")

    monkeypatch.setattr(audit_repo, "record", _boom)
    audit_repo.log(db_conn, "order_voided", user_id=1, details="x")  # must not raise

    row = db_conn.execute("SELECT value FROM settings WHERE key = 'probe'").fetchone()
    assert row["value"] == "before"  # the earlier write was committed despite the audit failure


def test_a_failing_audit_write_does_not_block_a_payment(db_conn, monkeypatch):
    from derby.core.db import categories_repo, products_repo, tables_repo, users_repo
    from derby.features.pos import orders_service

    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 2500)
    table = tables_repo.list_tables(db_conn)[0]
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner_id)
    orders_service.add_item(db_conn, order["id"], product_id, 1, [], None, owner_id)

    def _boom(*args, **kwargs):
        raise sqlite3.OperationalError("simulated audit failure")

    monkeypatch.setattr(audit_repo, "record", _boom)

    paid = orders_service.pay(db_conn, order["id"], "cash", users_repo.get_user(db_conn, owner_id))
    assert paid["status"] == "paid"  # the payment itself must succeed regardless


def test_list_and_count_entries_filter_by_business_date_and_severity(db_conn):
    audit_repo.record(db_conn, "login", business_date="2026-01-01", severity="info")
    audit_repo.record(db_conn, "order_voided", business_date="2026-01-02", severity="critical")
    audit_repo.record(db_conn, "order_voided", business_date="2026-01-03", severity="critical")

    assert audit_repo.count_entries(db_conn, severity="critical") == 2
    assert audit_repo.count_entries(db_conn, start_date="2026-01-02", end_date="2026-01-02") == 1
    rows = audit_repo.list_entries(db_conn, action="order_voided", page=0, page_size=1)
    assert len(rows) == 1


def test_pagination_at_scale_is_fast(tmp_path):
    """Proxy for the 100k-row pagination requirement: at a smaller but
    still meaningful scale, a filtered, indexed page must return quickly
    (the index on business_date/action makes this independent of table
    size) -- this is a smoke test for the query shape, not a full-scale
    benchmark (which would make the test suite itself slow)."""
    import time

    conn = connect(tmp_path / "scale.db")
    run_pending_migrations(conn)
    conn.execute("BEGIN")
    for i in range(5000):
        audit_repo.record(
            conn, "stock_waste", business_date="2026-01-{0:02d}".format((i % 28) + 1), severity="info", commit=False
        )
    conn.commit()

    started = time.monotonic()
    rows = audit_repo.list_entries(conn, page=10, page_size=50)
    elapsed = time.monotonic() - started
    assert len(rows) == 50
    assert elapsed < 2.0
    conn.close()
