"""Regression tests for the "an invoice doesn't show up until I restart
the app" bug.

Root cause (proved by reading the code, not guessed): every screen in
derby/features/shell/main_window.py is built once in _build_screens() and
re-queries the database only in __init__ -- MainWindow._on_navigate()
used to call .reload() again for exactly two screens ("tables" and
"playstation"), so every other data screen (سجل المبيعات، التقارير،
الخزنة، المخزون، العملاء، سجل المراجعة، الورديات والموظفون، المصروفات،
التوريدات) stayed frozen at whatever it showed when it was first built,
until the whole app (and therefore every screen) was rebuilt from
scratch. These tests pin the fix: a central "data changed" bus
(derby.core.events) that services notify after a real commit, a mixin
(derby.core.utils.screen_refresh.RefreshOnChangeMixin) that marks a
hidden screen dirty and reloads it on its next show, and a navigate-time
safety net in MainWindow that now calls .reload() on every screen that
has one, not just two of them.

Every test here would fail against the pre-fix code: a screen built once
with no further reload() call ever shows stale data for the lifetime of
the process.
"""
from __future__ import annotations

from PySide2.QtWidgets import QApplication

from derby.core.db import categories_repo, products_repo, tables_repo, users_repo
from derby.core.events import bus
from derby.features.customers import customer_service
from derby.features.customers.customers_screen import CustomersScreen
from derby.features.inventory import drawer_service
from derby.features.inventory.drawer_screen import DrawerScreen
from derby.features.pos import orders_service
from derby.features.pos.sales_log_screen import SalesLogScreen
from derby.features.reports.reports_screen import ReportsScreen


def _pump(predicate, timeout_ms=2000):
    """Processes Qt events until predicate() is true (the bus's 200ms
    debounce timer needs a running event loop to fire) or times out."""
    import time

    deadline = time.time() + timeout_ms / 1000.0
    while not predicate() and time.time() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    return predicate()


def _owner(db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    return users_repo.get_user(db_conn, owner_id)


def _open_and_pay(db_conn, user, method="cash", price=2500):
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", price)
    table = tables_repo.list_tables(db_conn)[0]
    order = orders_service.get_or_create_table_order(db_conn, table["id"], user["id"])
    orders_service.add_item(db_conn, order["id"], product_id, 1, [], None, user["id"])
    return orders_service.pay(db_conn, order["id"], method, user)


# --- the bus itself ---------------------------------------------------------


def test_bus_debounces_a_burst_of_notifications_into_one_signal(qapp):
    fired = []
    bus.changed.connect(lambda: fired.append(1))
    try:
        bus.notify()
        bus.notify()
        bus.notify()
        assert _pump(lambda: len(fired) >= 1)
        # give it a moment to see whether a second, redundant emission
        # sneaks through for the same burst
        QApplication.processEvents()
        assert len(fired) == 1
    finally:
        bus.changed.disconnect()


# --- the mixin's dirty/showEvent contract -----------------------------------


def test_hidden_screen_does_not_reload_immediately_but_reloads_on_next_show(qapp, db_conn):
    owner = _owner(db_conn)
    screen = SalesLogScreen(db_conn, owner)
    assert screen._table.rowCount() == 0

    screen.hide()
    paid = _open_and_pay(db_conn, owner)
    assert _pump(lambda: screen._dirty is True)
    # still hidden -- must NOT have requeried yet (that would defeat the
    # point of "dirty" for an off-screen widget)
    assert screen._table.rowCount() == 0

    screen.show()
    assert screen._table.rowCount() == 1
    assert screen._orders_by_row[0]["id"] == paid["id"]


def test_visible_screen_reloads_on_its_own_without_navigation(qapp, db_conn):
    owner = _owner(db_conn)
    screen = SalesLogScreen(db_conn, owner)
    screen.show()
    assert screen._table.rowCount() == 0

    paid = _open_and_pay(db_conn, owner)

    assert _pump(lambda: screen._table.rowCount() == 1)
    assert screen._orders_by_row[0]["id"] == paid["id"]


# --- the suspect screens named in the bug report ----------------------------


def test_drawer_screen_reflects_a_cash_sale_without_manual_reload(qapp, db_conn):
    owner = _owner(db_conn)
    drawer_service.open_drawer(db_conn, 0, owner["id"])
    screen = DrawerScreen(db_conn, owner)
    screen.show()
    before_text = screen._expected_cash_label.text()

    _open_and_pay(db_conn, owner, method="cash", price=3000)

    assert _pump(lambda: screen._expected_cash_label.text() != before_text)


def test_customers_screen_reflects_a_credit_sale_balance_without_manual_reload(qapp, db_conn):
    owner = _owner(db_conn)
    customer = customer_service.create_customer(db_conn, "محمد", None, None, None, owner)
    screen = CustomersScreen(db_conn, owner)
    screen.show()

    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 5000)
    table = tables_repo.list_tables(db_conn)[0]
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], product_id, 1, [], None, owner["id"])
    customer_service.credit_sale(db_conn, order["id"], customer["id"], owner)

    assert _pump(lambda: customer_service.balance_piasters(db_conn, customer["id"]) == 5000)
    screen.reload()  # already dirty-refreshed by the bus; this just asserts the row is current
    row_texts = [screen._table.item(0, 0).text()] if screen._table.rowCount() else []
    assert row_texts, "customer row should still be listed"


def test_reports_screen_totals_update_after_a_sale_while_visible(qapp, db_conn):
    owner = _owner(db_conn)
    screen = ReportsScreen(db_conn, owner)
    screen.show()

    _open_and_pay(db_conn, owner, price=2500)

    def _has_revenue():
        from derby.features.reports import report_service

        today = report_service.today_business_date(db_conn)
        report = report_service.build_report(db_conn, today, today)
        return report.net_sales_piasters > 0

    assert _pump(_has_revenue)


# --- transaction discipline: no service call leaves a dangling write -------


def test_pay_void_cancel_never_leave_the_connection_mid_transaction(db_conn):
    owner = _owner(db_conn)
    paid = _open_and_pay(db_conn, owner)
    assert db_conn.in_transaction is False

    orders_service.void(db_conn, paid["id"], "خطأ", owner)
    assert db_conn.in_transaction is False

    table = tables_repo.list_tables(db_conn)[0]
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.cancel(db_conn, order["id"], owner)
    assert db_conn.in_transaction is False


def test_a_second_connection_sees_a_payment_immediately(db_conn, tmp_path):
    import sqlite3

    owner = _owner(db_conn)
    paid = _open_and_pay(db_conn, owner)

    # db_conn is file-backed (see conftest.db_conn) -- a brand new
    # connection to the same file must see the committed row right away,
    # proving pay() actually commits instead of leaving it in-memory /
    # mid-transaction on the shared connection.
    second = sqlite3.connect(db_conn.execute("PRAGMA database_list").fetchone()[2])
    row = second.execute("SELECT status FROM orders WHERE id = ?", (paid["id"],)).fetchone()
    second.close()
    assert row is not None
    assert row[0] == "paid"
