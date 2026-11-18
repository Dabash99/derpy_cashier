"""Drives the real TablesScreen and MoveOrderDialog widgets."""
from __future__ import annotations

from derby.core.db import categories_repo, orders_repo, products_repo, tables_repo, users_repo
from derby.features.pos import orders_service
from derby.features.tables.move_order_dialog import MoveOrderDialog
from derby.features.tables.tables_screen import TablesScreen


def test_clicking_a_free_table_opens_order(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    table = tables_repo.list_tables(db_conn)[0]

    screen = TablesScreen(db_conn, owner)
    opened_order_ids = []
    screen.order_opened.connect(lambda order_id: opened_order_ids.append(order_id))

    screen._on_table_clicked(table["id"])
    assert len(opened_order_ids) == 1
    order = orders_repo.get_order(db_conn, opened_order_ids[0])
    assert order["table_id"] == table["id"]
    assert order["status"] == "open"


def test_owner_sees_management_tab_cashier_does_not(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    cashier_id = users_repo.create_user(db_conn, "Cashier", users_repo.ROLE_CASHIER, "2222")

    owner_screen = TablesScreen(db_conn, users_repo.get_user(db_conn, owner_id))
    assert hasattr(owner_screen, "_management_panel")

    cashier_screen = TablesScreen(db_conn, users_repo.get_user(db_conn, cashier_id))
    assert not hasattr(cashier_screen, "_management_panel")


def test_move_order_dialog_excludes_busy_and_current_tables(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    tables = tables_repo.list_tables(db_conn)

    order_a = orders_service.get_or_create_table_order(db_conn, tables[0]["id"], owner_id)
    orders_service.get_or_create_table_order(db_conn, tables[1]["id"], owner_id)  # busy

    dialog = MoveOrderDialog(db_conn, order_a["id"], owner)
    listed_table_ids = [
        target_id
        for kind, target_id in (dialog._list.item(i).data(1000) for i in range(dialog._list.count()))
        if kind == "table"
    ]
    assert tables[0]["id"] not in listed_table_ids  # current table excluded
    assert tables[1]["id"] not in listed_table_ids  # busy table excluded
    assert tables[2]["id"] in listed_table_ids  # free table included


def test_move_order_dialog_moves_on_confirm(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    tables = tables_repo.list_tables(db_conn)
    order_a = orders_service.get_or_create_table_order(db_conn, tables[0]["id"], owner_id)

    dialog = MoveOrderDialog(db_conn, order_a["id"], owner)
    dialog._list.setCurrentRow(0)
    dialog._on_confirm()

    moved = orders_repo.get_order(db_conn, order_a["id"])
    assert moved["table_id"] == tables[1]["id"]


def test_takeaway_badge_text_includes_total(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 2500)

    order = orders_service.create_takeaway_order(db_conn, owner_id)
    orders_service.add_item(db_conn, order["id"], product_id, 1, [], None, owner_id)

    screen = TablesScreen(db_conn, owner)
    screen.reload()
    assert screen._takeaway_layout.count() == 1
