"""Aggregate math on a synthetic dataset, hand-calculated in the comments
below (and shown again in the final Arabic report). Orders/expenses are
inserted directly via the repo layer (not through the full cashier/PS
flow, which Phases 3-4 already cover) so each number here is exact and
easy to verify by hand.
"""
from __future__ import annotations

from datetime import date

from derby.core.db import (
    categories_repo,
    expense_categories_repo,
    expenses_repo,
    orders_repo,
    products_repo,
    ps_devices_repo,
    tables_repo,
    users_repo,
)
from derby.features.reports import report_service


def _paid_order(conn, business_date, payment_method, items, device_item=None, discount_piasters=0, user_id=1):
    order_id = orders_repo.create_order(conn, None, user_id)
    subtotal = 0
    for name, product_id, qty, unit_price in items:
        line_total = qty * unit_price
        subtotal += line_total
        orders_repo.create_order_item(conn, order_id, "product", product_id, name, unit_price, qty, line_total)
    if device_item is not None:
        device_id, revenue, actual_minutes, mode = device_item
        session_id = conn.execute(
            """
            INSERT INTO ps_sessions (device_id, order_id, mode, started_at_utc, stopped_at_utc,
                rate_snapshot_piasters_per_hour, device_name_snapshot, actual_minutes, billed_minutes,
                price_piasters, is_final, started_by)
            VALUES (?, ?, ?, '2026-01-01T00:00:00+00:00', '2026-01-01T01:00:00+00:00', 4000,
                (SELECT name FROM ps_devices WHERE id = ?), ?, ?, ?, 1, ?)
            """,
            (device_id, order_id, mode, device_id, actual_minutes, actual_minutes, revenue, user_id),
        ).lastrowid
        name_snapshot = "{0} - {1}".format(conn.execute("SELECT name FROM ps_devices WHERE id=?", (device_id,)).fetchone()[0], mode)
        orders_repo.create_order_item(conn, order_id, "ps_time", None, name_snapshot, revenue, 1, revenue, ps_session_id=session_id)
        subtotal += revenue
    total = subtotal - discount_piasters
    orders_repo.update_order_totals(conn, order_id, subtotal, discount_piasters, total)
    orders_repo.mark_order_paid(conn, order_id, orders_repo.next_invoice_no(conn), user_id, business_date, payment_method)
    return orders_repo.get_order(conn, order_id)


def test_full_synthetic_dataset_matches_hand_calculation(db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    drinks = categories_repo.create_category(db_conn, "مشروبات")
    bakery = categories_repo.create_category(db_conn, "مخبوزات")
    coffee = products_repo.create_product(db_conn, drinks, "قهوة", "", 2500)
    croissant = products_repo.create_product(db_conn, bakery, "كرواسون", "", 1500)
    device = ps_devices_repo.list_devices(db_conn)[0]

    d1, d2 = "2026-01-10", "2026-01-11"

    # Order A (d1, cash): 2 coffees, no discount. total = 5000.
    _paid_order(db_conn, d1, "cash", [("قهوة", coffee, 2, 2500)], user_id=owner_id)
    # Order B (d1, instapay): 1 coffee + 3 croissants, fixed discount 1000. subtotal=7000, total=6000.
    _paid_order(db_conn, d1, "instapay", [("قهوة", coffee, 1, 2500), ("كرواسون", croissant, 3, 1500)], discount_piasters=1000, user_id=owner_id)
    # Order C (d2, cash): 1 croissant + a PS session (2500 piasters, 37 actual minutes). total=4000.
    _paid_order(db_conn, d2, "cash", [("كرواسون", croissant, 1, 1500)], device_item=(device["id"], 2500, 37, "single"), user_id=owner_id)

    # A void order and a cancelled order on d2 -- both must be fully excluded.
    void_order_id = orders_repo.create_order(db_conn, None, owner_id)
    orders_repo.update_order_totals(db_conn, void_order_id, 9999, 0, 9999)
    orders_repo.mark_order_paid(db_conn, void_order_id, orders_repo.next_invoice_no(db_conn), owner_id, d2, "cash")
    orders_repo.mark_order_void(db_conn, void_order_id, owner_id, "اختبار")
    cancelled_order_id = orders_repo.create_order(db_conn, None, owner_id)
    orders_repo.mark_order_cancelled(db_conn, cancelled_order_id)

    # Expenses: d1 كهرباء 2000 (active) + a voided 500 (must be excluded) + d2 مياه 300 (active).
    categories_by_name = {c["name"]: c["id"] for c in expense_categories_repo.list_categories(db_conn)}
    electricity_id = categories_by_name["كهرباء"]
    water_id = categories_by_name["مياه"]
    expenses_repo.create_expense(db_conn, electricity_id, 2000, d1, "فاتورة كهرباء", owner_id)
    voided_expense_id = expenses_repo.create_expense(db_conn, electricity_id, 500, d1, "غلط", owner_id)
    expenses_repo.void_expense(db_conn, voided_expense_id, owner_id, "مدخل بالغلط")
    expenses_repo.create_expense(db_conn, water_id, 300, d2, "فاتورة مياه", owner_id)

    report = report_service.build_report(db_conn, date(2026, 1, 10), date(2026, 1, 11), today=date(2026, 1, 11))

    assert report.invoice_count == 3
    assert report.net_sales_piasters == 15000
    assert report.discount_total_piasters == 1000
    assert report.average_invoice_piasters == 5000

    assert report.payment_methods["cash"].total_piasters == 9000
    assert report.payment_methods["cash"].count == 2
    assert report.payment_methods["instapay"].total_piasters == 6000
    assert report.payment_methods["instapay"].count == 1

    by_qty = {item.name: item.qty for item in report.top_items_by_qty}
    by_revenue = {item.name: item.revenue_piasters for item in report.top_items_by_revenue}
    assert by_qty == {"كرواسون": 4, "قهوة": 3}
    assert by_revenue == {"قهوة": 7500, "كرواسون": 6000}
    assert report.top_items_by_qty[0].name == "كرواسون"  # sorted desc by qty
    assert report.top_items_by_revenue[0].name == "قهوة"  # sorted desc by revenue

    categories = {c.category: c.total_piasters for c in report.sales_by_category}
    assert categories == {"مشروبات": 7500, "مخبوزات": 6000}

    assert len(report.ps_devices) == 1
    assert report.ps_devices[0].revenue_piasters == 2500
    assert report.ps_devices[0].minutes == 37
    assert report.ps_total_revenue_piasters == 2500

    assert report.expenses_total_piasters == 2300  # 2000 + 300, voided 500 excluded
    expense_categories = {c.category: c.total_piasters for c in report.expenses_by_category}
    assert expense_categories == {"كهرباء": 2000, "مياه": 300}

    assert report.profit_piasters == 15000 - 2300

    per_day_by_date = {d.day.isoformat(): d for d in report.per_day}
    assert per_day_by_date[d1].invoice_count == 2
    assert per_day_by_date[d1].net_sales_piasters == 11000
    assert per_day_by_date[d1].expenses_piasters == 2000
    assert per_day_by_date[d1].profit_piasters == 9000
    assert per_day_by_date[d2].invoice_count == 1
    assert per_day_by_date[d2].net_sales_piasters == 4000
    assert per_day_by_date[d2].expenses_piasters == 300
    assert per_day_by_date[d2].profit_piasters == 3700

    assert report.average_per_day_piasters == 15000 // 2  # full 2-day range, today == end_date


def test_close_time_0300_order_belongs_to_previous_business_day(db_conn, monkeypatch):
    from derby.core.db import settings_repo
    from derby.features.pos import orders_service

    settings_repo.set_value(db_conn, "business_close_time", "03:00")
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    table = tables_repo.list_tables(db_conn)[0]
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner_id)
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 2500)
    orders_service.add_item(db_conn, order["id"], product_id, 1, [], None, owner_id)

    # 2026-01-11 01:30 Cairo time == 2026-01-10 23:30 UTC (Cairo is UTC+2, no DST).
    from datetime import datetime, timezone

    utc_at_0130_cairo = datetime(2026, 1, 10, 23, 30, tzinfo=timezone.utc)
    monkeypatch.setattr("derby.features.pos.orders_service.utc_now", lambda: utc_at_0130_cairo)
    paid = orders_service.pay(db_conn, order["id"], "cash", users_repo.get_user(db_conn, owner_id))
    assert paid["business_date"] == "2026-01-10"  # previous day, not 01-11

    report = report_service.build_report(db_conn, date(2026, 1, 10), date(2026, 1, 10), today=date(2026, 1, 10))
    assert report.invoice_count == 1
    assert report.net_sales_piasters == 2500


def test_average_per_day_for_a_full_past_month_vs_ongoing_month(db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    coffee = products_repo.create_product(db_conn, category_id, "قهوة", "", 10000)

    _paid_order(db_conn, "2026-01-01", "cash", [("قهوة", coffee, 1, 10000)], user_id=owner_id)
    _paid_order(db_conn, "2026-01-31", "cash", [("قهوة", coffee, 1, 10000)], user_id=owner_id)

    # Past month: January is fully over by February -- average divides by all 31 days.
    past = report_service.build_report(db_conn, date(2026, 1, 1), date(2026, 1, 31), today=date(2026, 2, 5))
    assert len(past.per_day) == 31
    assert past.average_per_day_piasters == 20000 // 31

    # Ongoing month: "today" is the 15th, so the average divides by 15
    # elapsed days, not the full 31 (net sales itself is whatever the
    # queried range contains -- only the days_elapsed denominator changes).
    ongoing = report_service.build_report(db_conn, date(2026, 1, 1), date(2026, 1, 31), today=date(2026, 1, 15))
    assert ongoing.average_per_day_piasters == ongoing.net_sales_piasters // 15


def test_average_per_day_single_day_is_just_that_day(db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    coffee = products_repo.create_product(db_conn, category_id, "قهوة", "", 10000)
    _paid_order(db_conn, "2026-01-10", "cash", [("قهوة", coffee, 1, 10000)], user_id=owner_id)

    report = report_service.build_report(db_conn, date(2026, 1, 10), date(2026, 1, 10), today=date(2026, 1, 10))
    assert report.average_per_day_piasters == 10000


def test_info_counters_open_orders_and_running_sessions(db_conn):
    from derby.features.playstation import ps_service

    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    table = tables_repo.list_tables(db_conn)[0]

    from derby.features.pos import orders_service

    orders_service.get_or_create_table_order(db_conn, table["id"], owner_id)
    device = ps_devices_repo.list_devices(db_conn)[0]
    ps_devices_repo.set_rates(db_conn, device["id"], 4000, 6000)
    ps_service.start_session(db_conn, device["id"], "single", owner_id)

    report = report_service.build_report(db_conn, date(2026, 1, 1), date(2026, 1, 31), today=date(2026, 1, 15))
    assert report.open_orders_count == 2  # the table order + the device's own open order
    assert report.running_sessions_count == 1
    assert report.previous_day_open_orders_count == 0
    assert owner is not None  # sanity


def test_empty_period_does_not_crash(db_conn):
    report = report_service.build_report(db_conn, date(2026, 3, 1), date(2026, 3, 31), today=date(2026, 3, 31))
    assert report.invoice_count == 0
    assert report.net_sales_piasters == 0
    assert report.average_per_day_piasters == 0
    assert report.top_items_by_qty == []
    assert len(report.per_day) == 31
