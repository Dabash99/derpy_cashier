"""Settings must survive a full close + reopen of the database file,
exactly like a real app restart would."""
from __future__ import annotations

from derby.core.db import settings_repo
from derby.core.db.connection import connect
from derby.core.db.migrations import run_pending_migrations


def test_settings_persist_across_reconnect(tmp_path):
    db_path = tmp_path / "persist.db"

    conn = connect(db_path)
    run_pending_migrations(conn)
    settings_repo.ensure_defaults(conn)
    settings_repo.set_value(conn, "cafe_name", "Derby Menoufia")
    settings_repo.set_value(conn, "auto_lock_minutes", "15")
    conn.close()

    reconnected = connect(db_path)
    assert settings_repo.get(reconnected, "cafe_name") == "Derby Menoufia"
    assert settings_repo.get(reconnected, "auto_lock_minutes") == "15"
    reconnected.close()
