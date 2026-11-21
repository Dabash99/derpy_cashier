"""Regression coverage for a real production crash: the الرئيسية
dashboard raised sqlite3.OperationalError right after PIN login because
drawer_entries.is_historical was added by editing migration 0009 in
place (a violation of "never edit a past migration" -- see migration
0011's docstring and docs/FIX_TZ_CACHE_REPORT.md). These tests build
the dashboard directly against each of the database states the real
bug report named, for both roles, and must never raise.
"""
from __future__ import annotations

from derby.core.db import users_repo
from derby.core.db.connection import connect
from derby.core.db.migrations import (
    MIGRATIONS,
    _migration_0001_initial,
    _migration_0002_menu,
    _migration_0003_cashier,
    _migration_0004_playstation,
    _migration_0005_expenses,
    _migration_0006_closing,
    _migration_0007_supplies,
    _migration_0008_order_label,
    _migration_0009_inventory,
    run_pending_migrations,
)
from derby.features.dashboard.daily_stats_screen import DailyStatsScreen


def _owner_and_cashier(conn):
    owner_id = users_repo.create_user(conn, "Owner", users_repo.ROLE_OWNER, "1111")
    cashier_id = users_repo.create_user(conn, "Cashier", users_repo.ROLE_CASHIER, "2222")
    return users_repo.get_user(conn, owner_id), users_repo.get_user(conn, cashier_id)


def _assert_dashboard_builds_for_both_roles(conn, owner, cashier):
    for user in (owner, cashier):
        screen = DailyStatsScreen(conn, user)  # must not raise
        screen.reload()  # the timer-driven path -- must also not raise


def test_dashboard_builds_on_a_fresh_database(qapp, db_conn):
    owner, cashier = _owner_and_cashier(db_conn)
    _assert_dashboard_builds_for_both_roles(db_conn, owner, cashier)


def _drop_drawer_entries_is_historical_column(conn) -> None:
    """Simulates the real-world drift: a drawer_entries table built by
    the ORIGINAL (pre-fix) migration 0009, which had no is_historical
    column at all."""
    conn.execute("ALTER TABLE drawer_entries RENAME TO drawer_entries_old")
    conn.execute(
        """
        CREATE TABLE drawer_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_type TEXT NOT NULL CHECK (
                entry_type IN ('opening', 'sale_cash', 'expense', 'purchase', 'deposit', 'withdrawal', 'refund', 'count_adjustment')
            ),
            amount_delta_piasters INTEGER NOT NULL,
            ref_type TEXT,
            ref_id INTEGER,
            user_id INTEGER,
            note TEXT,
            created_at_utc TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    conn.execute(
        "INSERT INTO drawer_entries (id, entry_type, amount_delta_piasters, ref_type, ref_id, user_id, note, created_at_utc) "
        "SELECT id, entry_type, amount_delta_piasters, ref_type, ref_id, user_id, note, created_at_utc FROM drawer_entries_old"
    )
    conn.execute("DROP TABLE drawer_entries_old")
    conn.commit()


def test_dashboard_builds_on_a_migrated_phase8_db_with_the_real_schema_drift(qapp, tmp_path):
    """The exact scenario from the bug report: a database that went
    through the ORIGINAL migration 0009 (so drawer_entries never got
    is_historical), with some historical cash sales already backfilled,
    and no live opening entry yet."""
    db_path = tmp_path / "drifted.db"
    conn = connect(db_path)
    conn.execute("BEGIN")
    _migration_0001_initial(conn)
    _migration_0002_menu(conn)
    _migration_0003_cashier(conn)
    _migration_0004_playstation(conn)
    _migration_0005_expenses(conn)
    _migration_0006_closing(conn)
    _migration_0007_supplies(conn)
    _migration_0008_order_label(conn)
    _migration_0009_inventory(conn)  # current code -- includes is_historical
    conn.execute("PRAGMA user_version = 9")
    conn.commit()

    _drop_drawer_entries_is_historical_column(conn)  # simulate the real drift

    owner, cashier = _owner_and_cashier(conn)
    # A historical cash sale row, in the shape migration 0009's own
    # backfill would have produced (no is_historical column at all).
    conn.execute(
        "INSERT INTO drawer_entries (entry_type, amount_delta_piasters, ref_type, ref_id, user_id, note, created_at_utc) "
        "VALUES ('sale_cash', 1000, 'order', 1, ?, NULL, '2026-01-01T10:00:00+00:00')",
        (owner["id"],),
    )
    conn.commit()

    run_pending_migrations(conn)  # applies 0010 + 0011 -- must repair the column
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)

    columns = {row["name"] for row in conn.execute("PRAGMA table_info(drawer_entries)").fetchall()}
    assert "is_historical" in columns
    # The pre-existing row must be marked historical (it predates any
    # column that could have distinguished it).
    row = conn.execute("SELECT is_historical FROM drawer_entries WHERE entry_type = 'sale_cash'").fetchone()
    assert row["is_historical"] == 1

    _assert_dashboard_builds_for_both_roles(conn, owner, cashier)
    conn.close()


def test_dashboard_builds_with_an_opening_entry_and_some_sales(qapp, db_conn):
    from derby.core.db import categories_repo, products_repo, tables_repo
    from derby.features.inventory import drawer_service
    from derby.features.pos import orders_service

    owner, cashier = _owner_and_cashier(db_conn)
    drawer_service.open_drawer(db_conn, 10000, owner["id"])

    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "Coffee", 2500)
    table = tables_repo.list_tables(db_conn)[0]
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], product_id, 1, [], None, owner["id"])
    orders_service.pay(db_conn, order["id"], "cash", owner)

    _assert_dashboard_builds_for_both_roles(db_conn, owner, cashier)


def test_cash_in_drawer_tile_shows_placeholder_without_crashing_when_drawer_never_opened(qapp, db_conn):
    owner, _cashier = _owner_and_cashier(db_conn)
    from derby.core.i18n import ar

    screen = DailyStatsScreen(db_conn, owner)
    assert screen._tile_cash_in_drawer._value_label.text() == ar.DASHBOARD_DRAWER_NOT_OPENED


def test_safe_tile_helper_recovers_from_a_failing_lookup_without_raising(qapp, db_conn, monkeypatch):
    owner, _cashier = _owner_and_cashier(db_conn)

    def _boom(conn):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(
        "derby.features.dashboard.daily_stats_screen.drawer_service.expected_cash_piasters", _boom
    )
    screen = DailyStatsScreen(db_conn, owner)  # must not raise despite the simulated failure
    screen.reload()
    assert screen._tile_cash_in_drawer._value_label.text() in ("—", "افتح الدرج")
