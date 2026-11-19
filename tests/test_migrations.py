from __future__ import annotations

from derby.core.db import orders_repo, tables_repo, users_repo
from derby.core.db.connection import connect
from derby.core.db.migrations import (
    MIGRATIONS,
    _migration_0001_initial,
    _migration_0002_menu,
    _migration_0003_cashier,
    _migration_0004_playstation,
    _migration_0005_expenses,
    _migration_0006_closing,
    run_pending_migrations,
)


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


def test_migration_4_preserves_phase_3_data(tmp_path):
    """A cafe already running Phase 3 (tables/orders) must keep its data
    when it upgrades to Phase 4 (PlayStation)."""
    db_path = tmp_path / "upgrade34.db"
    conn = connect(db_path)
    conn.execute("BEGIN")
    _migration_0001_initial(conn)
    _migration_0002_menu(conn)
    _migration_0003_cashier(conn)
    conn.execute("PRAGMA user_version = 3")
    conn.commit()

    owner_id = users_repo.create_user(conn, "Owner", users_repo.ROLE_OWNER, "1234")
    table = tables_repo.list_tables(conn)[0]
    order_id = orders_repo.create_order(conn, table["id"], owner_id)

    run_pending_migrations(conn)  # applies migration 4 on top

    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    order = orders_repo.get_order(conn, order_id)
    assert order is not None
    assert order["table_id"] == table["id"]

    tables_in_db = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"ps_devices", "ps_sessions"}.issubset(tables_in_db)
    devices = conn.execute("SELECT * FROM ps_devices ORDER BY sort_order").fetchall()
    assert len(devices) == 2
    assert all(row["single_rate_piasters_per_hour"] == 0 for row in devices)
    conn.close()


def test_migration_5_preserves_phase_4_data(tmp_path):
    """A cafe already running Phase 4 (PlayStation) must keep its data
    when it upgrades to Phase 6 (expenses/reports)."""
    db_path = tmp_path / "upgrade45.db"
    conn = connect(db_path)
    conn.execute("BEGIN")
    _migration_0001_initial(conn)
    _migration_0002_menu(conn)
    _migration_0003_cashier(conn)
    _migration_0004_playstation(conn)
    conn.execute("PRAGMA user_version = 4")
    conn.commit()

    owner_id = users_repo.create_user(conn, "Owner", users_repo.ROLE_OWNER, "1234")
    table = tables_repo.list_tables(conn)[0]
    order_id = orders_repo.create_order(conn, table["id"], owner_id)

    run_pending_migrations(conn)  # applies migration 5 on top

    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    order = orders_repo.get_order(conn, order_id)
    assert order is not None
    assert order["table_id"] == table["id"]

    tables_in_db = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"expense_categories", "recurring_expenses", "expenses"}.issubset(tables_in_db)
    categories = conn.execute("SELECT name FROM expense_categories ORDER BY sort_order").fetchall()
    assert [row["name"] for row in categories] == ["إيجار", "كهرباء", "مياه", "صيانة", "أدوات شغل", "أخرى"]
    conn.close()


def test_migration_6_preserves_phase_5_data(tmp_path):
    """A cafe already running Phase 6 (expenses/reports) must keep its data
    when it upgrades to Phase 7 (closing/backup/WhatsApp)."""
    db_path = tmp_path / "upgrade56.db"
    conn = connect(db_path)
    conn.execute("BEGIN")
    _migration_0001_initial(conn)
    _migration_0002_menu(conn)
    _migration_0003_cashier(conn)
    _migration_0004_playstation(conn)
    _migration_0005_expenses(conn)
    conn.execute("PRAGMA user_version = 5")
    conn.commit()

    owner_id = users_repo.create_user(conn, "Owner", users_repo.ROLE_OWNER, "1234")
    table = tables_repo.list_tables(conn)[0]
    order_id = orders_repo.create_order(conn, table["id"], owner_id)

    run_pending_migrations(conn)  # applies migration 6 on top

    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    order = orders_repo.get_order(conn, order_id)
    assert order is not None
    assert order["table_id"] == table["id"]

    tables_in_db = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"day_closures", "backup_log"}.issubset(tables_in_db)
    settings = {
        row["key"]: row["value"]
        for row in conn.execute("SELECT key, value FROM settings WHERE key IN ('closing_enabled', 'backup_keep_count')")
    }
    assert settings == {"closing_enabled": "1", "backup_keep_count": "30"}
    conn.close()


def test_migration_7_preserves_phase_6_data(tmp_path):
    """A cafe already running Phase 7 (closing/backup) must keep its data
    when it upgrades to the supplies list."""
    db_path = tmp_path / "upgrade67.db"
    conn = connect(db_path)
    conn.execute("BEGIN")
    _migration_0001_initial(conn)
    _migration_0002_menu(conn)
    _migration_0003_cashier(conn)
    _migration_0004_playstation(conn)
    _migration_0005_expenses(conn)
    _migration_0006_closing(conn)
    conn.execute("PRAGMA user_version = 6")
    conn.commit()

    owner_id = users_repo.create_user(conn, "Owner", users_repo.ROLE_OWNER, "1234")
    table = tables_repo.list_tables(conn)[0]
    order_id = orders_repo.create_order(conn, table["id"], owner_id)

    run_pending_migrations(conn)  # applies migration 7 on top

    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    order = orders_repo.get_order(conn, order_id)
    assert order is not None
    assert order["table_id"] == table["id"]

    tables_in_db = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "supplies" in tables_in_db
    conn.close()
