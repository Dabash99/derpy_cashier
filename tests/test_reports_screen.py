"""Drives the real ReportsScreen widget directly -- no screenshots."""
from __future__ import annotations

from derby.core.db import categories_repo, orders_repo, products_repo, users_repo
from derby.features.reports.reports_screen import ReportsScreen


def _paid_order(db_conn, business_date, product_id, qty, unit_price, user_id, name="قهوة"):
    order_id = orders_repo.create_order(db_conn, None, user_id)
    line_total = qty * unit_price
    orders_repo.create_order_item(db_conn, order_id, "product", product_id, name, unit_price, qty, line_total)
    orders_repo.update_order_totals(db_conn, order_id, line_total, 0, line_total)
    orders_repo.mark_order_paid(db_conn, order_id, orders_repo.next_invoice_no(db_conn), user_id, business_date, "cash")


def test_daily_tab_shows_hand_calculated_summary(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 2500)
    _paid_order(db_conn, "2026-01-10", product_id, 2, 2500, owner_id)

    screen = ReportsScreen(db_conn, users_repo.get_user(db_conn, owner_id))
    screen._tabs.setCurrentIndex(0)
    screen._daily_input.setText("2026-01-10")
    screen.reload()

    assert screen._report.net_sales_piasters == 5000
    assert "50.00" in screen._summary_label.text()
    assert screen._payment_table.rowCount() == 2  # cash + instapay rows always shown
    assert screen._top_items_table.rowCount() == 1


def test_monthly_tab_per_day_table_spans_the_month(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 10000)
    _paid_order(db_conn, "2026-01-01", product_id, 1, 10000, owner_id)

    screen = ReportsScreen(db_conn, users_repo.get_user(db_conn, owner_id))
    screen._tabs.setCurrentIndex(1)
    screen._monthly_input.setText("2026-01")
    screen.reload()

    assert screen._per_day_table.rowCount() == 31


def test_top_items_toggle_switches_sort_order(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    coffee = products_repo.create_product(db_conn, category_id, "قهوة", "", 2500)
    croissant = products_repo.create_product(db_conn, category_id, "كرواسون", "", 1000)
    # coffee: qty 3, revenue 7500 (wins by revenue). croissant: qty 5, revenue 5000 (wins by qty).
    _paid_order(db_conn, "2026-01-10", coffee, 3, 2500, owner_id, name="قهوة")
    _paid_order(db_conn, "2026-01-10", croissant, 5, 1000, owner_id, name="كرواسون")

    screen = ReportsScreen(db_conn, users_repo.get_user(db_conn, owner_id))
    screen._tabs.setCurrentIndex(0)
    screen._daily_input.setText("2026-01-10")
    screen.reload()

    index_qty = screen._top_items_toggle.findData("qty")
    screen._top_items_toggle.setCurrentIndex(index_qty)
    screen._render_top_items()
    assert screen._top_items_table.item(0, 0).text() == "كرواسون"

    index_revenue = screen._top_items_toggle.findData("revenue")
    screen._top_items_toggle.setCurrentIndex(index_revenue)
    screen._render_top_items()
    assert screen._top_items_table.item(0, 0).text() == "قهوة"


def test_warning_banner_shown_when_open_orders_exist(qapp, db_conn):
    from derby.core.db import tables_repo
    from derby.features.pos import orders_service

    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    table = tables_repo.list_tables(db_conn)[0]
    orders_service.get_or_create_table_order(db_conn, table["id"], owner_id)

    screen = ReportsScreen(db_conn, owner)
    screen.reload()
    assert screen._warning_label.text() != ""


def test_no_warning_banner_when_nothing_open(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    screen = ReportsScreen(db_conn, users_repo.get_user(db_conn, owner_id))
    screen.reload()
    assert screen._warning_label.text() == ""


def test_export_panel_wired_to_report(qapp, db_conn, tmp_path):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    screen = ReportsScreen(db_conn, users_repo.get_user(db_conn, owner_id))
    screen.reload()

    path = tmp_path / "out.csv"
    screen._export_csv(path)
    assert path.exists()
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
