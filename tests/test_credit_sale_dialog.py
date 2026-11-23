from __future__ import annotations

from derby.core.db import categories_repo, products_repo, tables_repo, users_repo
from derby.features.customers.credit_sale_dialog import CreditSaleDialog
from derby.features.pos import orders_service


def test_dialog_lists_customers_and_confirms_sale(qapp, db_conn):
    from derby.features.customers import customer_service

    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    customer_service.create_customer(db_conn, "محمد", None, None, None, owner)

    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 2500)
    table = tables_repo.list_tables(db_conn)[0]
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], product_id, 1, [], None, owner["id"])

    dialog = CreditSaleDialog(db_conn, order, owner)
    assert dialog._customer_input.count() == 1
    dialog._on_confirm()
    assert dialog.paid_order is not None
    assert dialog.paid_order["status"] == "paid"


def test_dialog_can_create_a_new_customer_inline(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 2500)
    table = tables_repo.list_tables(db_conn)[0]
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], product_id, 1, [], None, owner["id"])

    dialog = CreditSaleDialog(db_conn, order, owner)
    dialog._new_name_input.setText("عميل جديد")
    dialog._on_add_customer()
    assert dialog._customer_input.count() == 1
