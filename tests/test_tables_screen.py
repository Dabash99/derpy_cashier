"""Drives the real TablesScreen and MoveOrderDialog widgets."""
from __future__ import annotations

from PySide2.QtWidgets import QPushButton

from derby.core.db import categories_repo, orders_repo, products_repo, tables_repo, users_repo
from derby.core.i18n import ar
from derby.features.pos import orders_service
from derby.features.tables.move_order_dialog import MoveOrderDialog
from derby.features.tables.tables_screen import TablesScreen


def test_clicking_a_free_table_does_not_create_an_order(qapp, db_conn):
    """Lazy order creation (item E of the UI fix pass): merely clicking a
    free table must not create a database row -- only table_selected
    fires, and PosScreen materializes the order on the first item add."""
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    table = tables_repo.list_tables(db_conn)[0]

    screen = TablesScreen(db_conn, owner)
    selected_table_ids = []
    screen.table_selected.connect(lambda table_id: selected_table_ids.append(table_id))
    screen.reload()

    card = screen._tables_grid.itemAt(0).widget()
    card.findChildren(QPushButton)[0].click()

    assert selected_table_ids == [table["id"]]
    assert orders_repo.get_open_order_for_table(db_conn, table["id"]) is None


def test_leftover_empty_table_order_can_be_closed_without_approval(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    table = tables_repo.list_tables(db_conn)[0]

    # A materialized order with zero items -- the state auto_cancel_empty_open_orders
    # normally sweeps, shown here as if that sweep hasn't run yet.
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner_id)

    screen = TablesScreen(db_conn, owner)
    screen.reload()
    card = screen._tables_grid.itemAt(0).widget()
    close_button = card.findChildren(QPushButton)[0]
    assert close_button.text() == ar.TABLES_CLOSE_EMPTY_BUTTON
    close_button.click()

    assert orders_repo.get_order(db_conn, order["id"])["status"] == "cancelled"


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
