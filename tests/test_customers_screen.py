from __future__ import annotations

from derby.core.db import users_repo
from derby.features.customers import customer_service
from derby.features.customers.customers_screen import CustomersScreen


def test_screen_lists_customers_and_balances(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    customer_service.create_customer(db_conn, "محمد", "0100000000", None, None, owner)

    screen = CustomersScreen(db_conn, owner)
    assert screen._table.rowCount() == 1


def test_add_customer_through_the_screen(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    screen = CustomersScreen(db_conn, owner)

    screen._name_input.setText("أحمد")
    screen._on_add()
    assert screen._table.rowCount() == 1
    assert screen._message_label.text() == "تم الحفظ"


def test_cashier_can_view_customers_screen(qapp, db_conn):
    cashier_id = users_repo.create_user(db_conn, "Cashier", users_repo.ROLE_CASHIER, "2222")
    cashier = users_repo.get_user(db_conn, cashier_id)
    screen = CustomersScreen(db_conn, cashier)
    assert screen is not None
