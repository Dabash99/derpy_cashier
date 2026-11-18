from __future__ import annotations

from derby.core.db import users_repo
from derby.core.db.connection import connect
from derby.core.db.migrations import MIGRATIONS, _migration_0001_initial, run_pending_migrations


def _table_names(conn):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row["name"] for row in rows}


def test_migrations_from_scratch_create_all_tables(tmp_path):
    conn = connect(tmp_path / "scratch.db")
    run_pending_migrations(conn)

    tables = _table_names(conn)
    assert {"users", "settings", "audit_log"}.issubset(tables)

    user_version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert user_version == len(MIGRATIONS)
    conn.close()


def test_migrations_are_idempotent(tmp_path):
    db_path = tmp_path / "idempotent.db"
    conn = connect(db_path)
    run_pending_migrations(conn)
    run_pending_migrations(conn)  # should be a no-op, not an error
    conn.close()

    # Reopening and running again (simulating a second app launch) must
    # also be a safe no-op.
    conn2 = connect(db_path)
    run_pending_migrations(conn2)
    user_version = conn2.execute("PRAGMA user_version").fetchone()[0]
    assert user_version == len(MIGRATIONS)
    conn2.close()


def test_migration_2_preserves_phase_1_data(tmp_path):
    """A cafe already running Phase 1 must keep its users/settings when it
    upgrades to Phase 2 -- migrations only ever add, never touch past data."""
    db_path = tmp_path / "upgrade.db"
    conn = connect(db_path)
    conn.execute("BEGIN")
    _migration_0001_initial(conn)
    conn.execute("PRAGMA user_version = 1")
    conn.commit()

    owner_id = users_repo.create_user(conn, "Owner", users_repo.ROLE_OWNER, "1234")

    run_pending_migrations(conn)  # applies migration 2 on top

    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    owner = users_repo.get_user(conn, owner_id)
    assert owner is not None
    assert owner["name"] == "Owner"

    tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"categories", "products", "addon_groups", "addons", "product_addon_groups"}.issubset(tables)
    conn.close()
