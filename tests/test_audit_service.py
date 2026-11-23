from __future__ import annotations

import sqlite3

from derby.core import audit_service
from derby.core.db import audit_repo, users_repo


def test_log_snapshots_user_name_from_row(db_conn):
    owner_id = users_repo.create_user(db_conn, "محمد", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    audit_service.log(db_conn, "login", user=owner, entity_type="user", entity_id=owner_id)
    row = db_conn.execute("SELECT * FROM audit_log WHERE action = 'login'").fetchone()
    assert row["user_name"] == "محمد"
    assert row["user_id"] == owner_id


def test_log_never_raises_even_if_record_fails(db_conn, monkeypatch):
    def _boom(*args, **kwargs):
        raise sqlite3.OperationalError("simulated")

    monkeypatch.setattr(audit_repo, "record", _boom)
    audit_service.log(db_conn, "login")  # must not raise


def test_invalid_severity_normalizes_to_info(db_conn):
    audit_service.log(db_conn, "login", severity="nonsense")
    row = db_conn.execute("SELECT severity FROM audit_log WHERE action = 'login'").fetchone()
    assert row["severity"] == "info"
