"""Drives the real DailyStatsScreen widget -- owner/cashier visibility
of the profit/expenses row, and the 30s refresh timer starting/stopping
with show/hide (a hidden dashboard must never poll)."""
from __future__ import annotations

from derby.core.db import users_repo
from derby.features.dashboard.daily_stats_screen import DailyStatsScreen


def test_owner_sees_expenses_and_net_today_tiles(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    screen = DailyStatsScreen(db_conn, users_repo.get_user(db_conn, owner_id))
    assert not screen._tile_expenses.isHidden()
    assert not screen._tile_net_today.isHidden()


def test_cashier_does_not_see_expenses_and_net_today_tiles(qapp, db_conn):
    cashier_id = users_repo.create_user(db_conn, "Cashier", users_repo.ROLE_CASHIER, "2222")
    screen = DailyStatsScreen(db_conn, users_repo.get_user(db_conn, cashier_id))
    assert screen._tile_expenses.isHidden()
    assert screen._tile_net_today.isHidden()


def test_cashier_still_sees_sales_tiles(qapp, db_conn):
    cashier_id = users_repo.create_user(db_conn, "Cashier", users_repo.ROLE_CASHIER, "2222")
    screen = DailyStatsScreen(db_conn, users_repo.get_user(db_conn, cashier_id))
    assert not screen._tile_net_sales.isHidden()
    assert not screen._tile_invoice_count.isHidden()
    assert not screen._tile_cash.isHidden()
    assert not screen._tile_instapay.isHidden()


def test_timer_starts_on_show_and_stops_on_hide(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    screen = DailyStatsScreen(db_conn, users_repo.get_user(db_conn, owner_id))
    assert not screen._timer.isActive()  # never shown yet

    screen.show()
    qapp.processEvents()
    assert screen._timer.isActive()

    screen.hide()
    qapp.processEvents()
    assert not screen._timer.isActive()


def test_timer_interval_is_30_seconds(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    screen = DailyStatsScreen(db_conn, users_repo.get_user(db_conn, owner_id))
    assert screen._timer.interval() == 30_000


def test_date_switcher_disables_next_on_today_and_prev_past_the_limit(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    screen = DailyStatsScreen(db_conn, users_repo.get_user(db_conn, owner_id))
    assert screen._next_button.isEnabled() is False  # default is today

    for _ in range(10):  # far more than the 6-day limit
        screen._on_prev_day()
    from derby.features.dashboard import daily_stats_service
    from derby.features.reports import report_service

    today = report_service.today_business_date(db_conn)
    earliest = daily_stats_service.earliest_selectable_date(db_conn, today=today)
    assert screen._selected_date == earliest
    assert screen._prev_button.isEnabled() is False
