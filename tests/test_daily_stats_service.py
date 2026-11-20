"""Item 3: every figure on the إحصائيات اليوم dashboard must come from
report_service.build_report() (same function التقارير uses) -- no
duplicated sales math -- plus the "now" figures and comparison chips.
"""
from __future__ import annotations

from datetime import timedelta

from derby.core.db import (
    categories_repo,
    orders_repo,
    products_repo,
    ps_devices_repo,
    tables_repo,
    users_repo,
)
from derby.features.dashboard import daily_stats_service
from derby.features.playstation import ps_service
from derby.features.pos import orders_service
from derby.features.reports import report_service


def _owner(db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    return users_repo.get_user(db_conn, owner_id)


def _paid_order(db_conn, business_date_iso, product_id, owner_id):
    order_id = orders_repo.create_order(db_conn, None, owner_id)
    orders_repo.create_order_item(db_conn, order_id, "product", product_id, "قهوة", 2500, 1, 2500)
    orders_repo.update_order_totals(db_conn, order_id, 2500, 0, 2500)
    orders_repo.mark_order_paid(db_conn, order_id, orders_repo.next_invoice_no(db_conn), owner_id, business_date_iso, "cash")


def test_dashboard_report_matches_build_report_exactly(db_conn):
    owner = _owner(db_conn)
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 2500)
    today = report_service.today_business_date(db_conn)
    _paid_order(db_conn, today.isoformat(), product_id, owner["id"])

    stats = daily_stats_service.build_daily_stats(db_conn, today, today=today)
    direct_report = report_service.build_report(db_conn, today, today, today=today)

    assert stats.report == direct_report
    assert stats.report.net_sales_piasters == 2500


def test_hourly_sales_sum_equals_net_sales_when_no_discounts(db_conn):
    owner = _owner(db_conn)
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 2500)
    today = report_service.today_business_date(db_conn)
    _paid_order(db_conn, today.isoformat(), product_id, owner["id"])
    _paid_order(db_conn, today.isoformat(), product_id, owner["id"])

    stats = daily_stats_service.build_daily_stats(db_conn, today, today=today)

    assert sum(stats.hourly_sales_piasters) == stats.report.net_sales_piasters == 5000
    assert len(stats.hourly_sales_piasters) == 24


def test_empty_day_has_zeroed_report_and_no_comparison_data(db_conn):
    owner = _owner(db_conn)
    today = report_service.today_business_date(db_conn)

    stats = daily_stats_service.build_daily_stats(db_conn, today, today=today)

    assert stats.report.invoice_count == 0
    assert stats.report.net_sales_piasters == 0
    assert sum(stats.hourly_sales_piasters) == 0
    assert stats.vs_yesterday.has_data is False
    assert stats.vs_last_week_same_weekday.has_data is False
    assert owner  # fixture used only to seed a user table row for realism


def test_now_section_reflects_open_orders_running_sessions_and_tables(db_conn):
    owner = _owner(db_conn)
    table = tables_repo.list_tables(db_conn)[0]
    orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    device = ps_devices_repo.list_devices(db_conn)[0]
    ps_devices_repo.set_rates(db_conn, device["id"], 4000, 6000)
    ps_service.start_session(db_conn, device["id"], "single", owner["id"])

    today = report_service.today_business_date(db_conn)
    stats = daily_stats_service.build_daily_stats(db_conn, today, today=today)

    assert stats.open_orders_count == 2  # the empty table order + the running PS session's own order
    assert len(stats.running_sessions) == 1
    assert stats.running_sessions[0].device_name == device["name"]
    assert stats.running_sessions[0].mode == "single"
    assert stats.tables_busy_count == 0  # the table order was only opened, no item added yet -- busy means has items
    assert stats.tables_free_count == len(tables_repo.list_tables(db_conn))


def test_comparison_vs_yesterday_computes_percent_change(db_conn):
    owner = _owner(db_conn)
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 2500)
    today = report_service.today_business_date(db_conn)
    yesterday = today - timedelta(days=1)
    _paid_order(db_conn, yesterday.isoformat(), product_id, owner["id"])  # 2500
    _paid_order(db_conn, today.isoformat(), product_id, owner["id"])
    _paid_order(db_conn, today.isoformat(), product_id, owner["id"])  # 5000 today -> +100%

    stats = daily_stats_service.build_daily_stats(db_conn, today, today=today)

    assert stats.vs_yesterday.has_data is True
    assert stats.vs_yesterday.percent_change == 100.0


def test_comparison_with_missing_day_reports_no_data(db_conn):
    owner = _owner(db_conn)
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 2500)
    today = report_service.today_business_date(db_conn)
    _paid_order(db_conn, today.isoformat(), product_id, owner["id"])

    stats = daily_stats_service.build_daily_stats(db_conn, today, today=today)

    assert stats.vs_yesterday.has_data is False
    assert stats.vs_yesterday.percent_change is None


def test_earliest_selectable_date_is_six_days_back(db_conn):
    today = report_service.today_business_date(db_conn)
    assert daily_stats_service.earliest_selectable_date(db_conn, today=today) == today - timedelta(days=6)
