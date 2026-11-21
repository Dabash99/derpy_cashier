"""Drives the real MainWindow wiring for the Phase 9 "فاتورة بيع جديدة"
flow from the home (DailyStatsScreen) screen: تيك أواي hands off to the
Cashier screen exactly like the Tables screen's own takeaway button;
ترابيزة/بلايستيشن navigate to the Tables/PlayStation screens, which
attach to an existing open bill or create a new one -- this test proves
that wiring end to end rather than re-testing tables_screen/playstation_screen's
own internal logic (covered elsewhere).
"""
from __future__ import annotations

from derby.core.db import orders_repo, tables_repo, users_repo
from derby.features.shell.idle_filter import IdleTimer
from derby.features.shell.main_window import MainWindow


def _owner(db_conn):
    user_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    return users_repo.get_user(db_conn, user_id)


def test_takeaway_from_dashboard_opens_pos_with_pending_takeaway(qapp, db_conn, tmp_path):
    owner = _owner(db_conn)
    window = MainWindow(db_conn, owner, IdleTimer(), tmp_path / "test_derby.db")
    home = window._screens["daily_stats"]

    home.takeaway_requested.emit("")

    pos_screen = window._screens["pos"]
    assert window._content_stack.currentWidget() is pos_screen
    assert pos_screen._pending_is_takeaway is True


def test_table_choice_from_dashboard_navigates_to_tables_screen(qapp, db_conn, tmp_path):
    owner = _owner(db_conn)
    window = MainWindow(db_conn, owner, IdleTimer(), tmp_path / "test_derby.db")
    home = window._screens["daily_stats"]

    home.navigate_requested.emit("tables")

    assert window._content_stack.currentWidget() is window._screens["tables"]


def test_picking_a_busy_table_from_tables_screen_attaches_to_existing_bill(qapp, db_conn, tmp_path):
    owner = _owner(db_conn)
    window = MainWindow(db_conn, owner, IdleTimer(), tmp_path / "test_derby.db")
    table = tables_repo.list_tables(db_conn)[0]

    # Simulate the table already having an open bill (started elsewhere).
    existing_order_id = orders_repo.create_order(db_conn, table["id"], owner["id"])

    tables_screen = window._screens["tables"]
    tables_screen.order_opened.emit(existing_order_id)

    pos_screen = window._screens["pos"]
    assert window._content_stack.currentWidget() is pos_screen
    assert pos_screen._current_order_id == existing_order_id
    # No second order was created for the same table.
    assert len(orders_repo.list_open_orders(db_conn)) == 1


def test_picking_a_free_table_from_tables_screen_starts_a_new_bill(qapp, db_conn, tmp_path):
    owner = _owner(db_conn)
    window = MainWindow(db_conn, owner, IdleTimer(), tmp_path / "test_derby.db")
    table = tables_repo.list_tables(db_conn)[0]
    assert orders_repo.get_open_order_for_table(db_conn, table["id"]) is None

    tables_screen = window._screens["tables"]
    tables_screen.table_selected.emit(table["id"])

    pos_screen = window._screens["pos"]
    assert window._content_stack.currentWidget() is pos_screen
    assert pos_screen._pending_table_id == table["id"]
