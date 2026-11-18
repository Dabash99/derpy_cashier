"""Drives the real SalesLogScreen widget."""
from __future__ import annotations

from derby.core.db import categories_repo, products_repo, tables_repo, users_repo
from derby.features.pos import orders_service
from derby.features.pos.sales_log_screen import SalesLogScreen


def _paid_order(db_conn, user_id, method="cash", price=2500):
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", price)
    table = tables_repo.list_tables(db_conn)[0]
    order = orders_service.get_or_create_table_order(db_conn, table["id"], user_id)
    orders_service.add_item(db_conn, order["id"], product_id, 1, [], None, user_id)
    return orders_service.pay(db_conn, order["id"], method, users_repo.get_user(db_conn, user_id))


def test_cashier_date_field_is_locked(qapp, db_conn):
    cashier_id = users_repo.create_user(db_conn, "Cashier", users_repo.ROLE_CASHIER, "2222")
    screen = SalesLogScreen(db_conn, users_repo.get_user(db_conn, cashier_id))
    assert screen._date_input.isEnabled() is False


def test_owner_date_field_is_editable(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    screen = SalesLogScreen(db_conn, users_repo.get_user(db_conn, owner_id))
    assert screen._date_input.isEnabled() is True


def test_paid_order_shows_up_in_todays_log(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    paid = _paid_order(db_conn, owner_id)

    screen = SalesLogScreen(db_conn, users_repo.get_user(db_conn, owner_id))
    assert screen._table.rowCount() == 1
    assert screen._orders_by_row[0]["id"] == paid["id"]


def test_cancelled_order_never_appears(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    table = tables_repo.list_tables(db_conn)[0]
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner_id)
    orders_service.cancel(db_conn, order["id"], owner)

    screen = SalesLogScreen(db_conn, owner)
    assert screen._table.rowCount() == 0


def test_void_button_hidden_for_cashier(qapp, db_conn):
    cashier_id = users_repo.create_user(db_conn, "Cashier", users_repo.ROLE_CASHIER, "2222")
    screen = SalesLogScreen(db_conn, users_repo.get_user(db_conn, cashier_id))
    assert screen._void_button.isVisible() is False


def test_void_updates_status_and_excludes_from_totals(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    paid = _paid_order(db_conn, owner_id)

    screen = SalesLogScreen(db_conn, owner)
    screen._table.selectRow(0)

    from derby.features.pos import orders_service as service

    service.void(db_conn, paid["id"], "طلب العميل", owner)
    screen.reload()

    assert "عدد الفواتير: 0" in screen._totals_label.text()


def test_method_filter(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    _paid_order(db_conn, owner_id, method="cash")

    screen = SalesLogScreen(db_conn, users_repo.get_user(db_conn, owner_id))
    index = screen._method_filter.findData("instapay")
    screen._method_filter.setCurrentIndex(index)
    assert screen._table.rowCount() == 0
