"""Migration 0010: stock_movements.business_date backfill must match
business_date()+business_close_time exactly (the same rule orders and
expenses already use), and running the migration twice must never
change anything.
"""
from __future__ import annotations

from datetime import datetime, time, timezone

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
from derby.core.utils.business_date import business_date as compute_business_date
from derby.core.utils.time_utils import to_utc_iso


def _db_at_version_9(tmp_path, close_time_text="23:59"):
    db_path = tmp_path / "v9.db"
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
    _migration_0009_inventory(conn)
    conn.execute("PRAGMA user_version = 9")
    conn.commit()
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('business_close_time', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (close_time_text,),
    )
    conn.commit()
    return conn, db_path


def _insert_stock_item_and_movement(conn, created_at_utc: str) -> int:
    conn.execute(
        "INSERT INTO stock_items (name, unit, current_qty, min_qty, avg_cost_piasters, is_active, created_at_utc) "
        "VALUES ('دقيق', 'g', 0, 0, 0, 1, ?)",
        (created_at_utc,),
    )
    stock_item_id = conn.execute("SELECT id FROM stock_items WHERE name = 'دقيق'").fetchone()[0]
    cursor = conn.execute(
        "INSERT INTO stock_movements (stock_item_id, movement_type, qty_delta, unit_cost_snapshot_piasters, created_at_utc) "
        "VALUES (?, 'waste', -1, 10, ?)",
        (stock_item_id, created_at_utc),
    )
    conn.commit()
    return cursor.lastrowid


def test_backfill_matches_business_date_helper_with_early_close_time(tmp_path):
    from datetime import timedelta

    conn, _db_path = _db_at_version_9(tmp_path, close_time_text="03:00")

    # 01:30 Cairo local time (close_time 03:00) -> previous business day.
    # Cairo is UTC+2 (EET, no DST) in January.
    cairo_0130 = datetime(2026, 1, 10, 1, 30, 0)
    utc_at_0130 = (cairo_0130 - timedelta(hours=2)).replace(tzinfo=timezone.utc)
    movement_id = _insert_stock_item_and_movement(conn, to_utc_iso(utc_at_0130))

    run_pending_migrations(conn)

    row = conn.execute("SELECT business_date FROM stock_movements WHERE id = ?", (movement_id,)).fetchone()
    expected = compute_business_date(utc_at_0130, time(3, 0)).isoformat()
    assert row["business_date"] == expected
    assert row["business_date"] == "2026-01-09"
    conn.close()


def test_backfill_after_close_time_lands_on_new_business_day(tmp_path):
    conn, _db_path = _db_at_version_9(tmp_path, close_time_text="03:00")

    from datetime import timedelta

    cairo_0301 = datetime(2026, 1, 10, 3, 1, 0)
    utc_at_0301 = (cairo_0301 - timedelta(hours=2)).replace(tzinfo=timezone.utc)
    movement_id = _insert_stock_item_and_movement(conn, to_utc_iso(utc_at_0301))

    run_pending_migrations(conn)

    row = conn.execute("SELECT business_date FROM stock_movements WHERE id = ?", (movement_id,)).fetchone()
    assert row["business_date"] == "2026-01-10"
    conn.close()


def test_migration_0010_creates_index(tmp_path):
    conn, _db_path = _db_at_version_9(tmp_path)
    run_pending_migrations(conn)
    index_names = {
        row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
    }
    assert "idx_stock_movements_business_date" in index_names
    conn.close()


def test_migration_0010_is_idempotent_across_app_restarts(tmp_path):
    conn, db_path = _db_at_version_9(tmp_path)
    users_repo.create_user(conn, "Owner", users_repo.ROLE_OWNER, "1234")

    movement_id = _insert_stock_item_and_movement(conn, to_utc_iso(datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)))

    run_pending_migrations(conn)  # first launch after the upgrade
    conn.close()

    conn2 = connect(db_path)
    before = conn2.execute("SELECT business_date FROM stock_movements WHERE id = ?", (movement_id,)).fetchone()["business_date"]

    run_pending_migrations(conn2)  # second launch -- must be a pure no-op

    after = conn2.execute("SELECT business_date FROM stock_movements WHERE id = ?", (movement_id,)).fetchone()["business_date"]
    assert before == after
    assert conn2.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    conn2.close()


def test_backfill_survives_cairo_dst_transition(tmp_path):
    """Scan 2024 for the day Cairo's UTC offset changes, and confirm the
    backfill still lands on a sensible, non-crashing business date on
    both sides of it (same proof test_business_date.py already does for
    the pure helper -- here we check the migration's use of it)."""
    conn, _db_path = _db_at_version_9(tmp_path)
    from datetime import timedelta

    from derby.core.utils.time_utils import to_cairo

    start = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    previous_offset = to_cairo(start).utcoffset()
    transition = None
    for day_number in range(1, 366):
        current = start + timedelta(days=day_number)
        current_offset = to_cairo(current).utcoffset()
        if current_offset != previous_offset:
            transition = current
            break
        previous_offset = current_offset
    assert transition is not None, "expected a Cairo DST transition in 2024"

    before_id = _insert_stock_item_and_movement(conn, to_utc_iso(transition - timedelta(hours=12)))
    conn.execute(
        "INSERT INTO stock_movements (stock_item_id, movement_type, qty_delta, unit_cost_snapshot_piasters, created_at_utc) "
        "SELECT stock_item_id, 'waste', -1, 10, ? FROM stock_movements WHERE id = ?",
        (to_utc_iso(transition + timedelta(hours=12)), before_id),
    )
    conn.commit()

    run_pending_migrations(conn)

    rows = conn.execute("SELECT business_date FROM stock_movements ORDER BY id").fetchall()
    assert all(row["business_date"] is not None for row in rows)
    conn.close()
