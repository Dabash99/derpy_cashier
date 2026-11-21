from __future__ import annotations

from derby.core.db import stock_items_repo, suppliers_repo, users_repo
from derby.features.inventory import stock_service
from derby.features.inventory.inventory_screen import InventoryScreen


def _owner(db_conn):
    user_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1234")
    return users_repo.get_user(db_conn, user_id)


def test_inventory_screen_builds_and_lists_items(qapp, db_conn):
    owner = _owner(db_conn)
    flour_id = stock_items_repo.create_stock_item(db_conn, "دقيق", "g", min_qty=500)
    stock_service.record_purchase(
        db_conn, None, "2026-01-01", [{"stock_item_id": flour_id, "qty": 1000, "unit_cost_piasters": 10}], False, owner["id"]
    )
    screen = InventoryScreen(db_conn, owner)
    assert screen._stock_table.rowCount() == 1
    assert screen._stock_table.item(0, 0).text() == "دقيق"


def test_inventory_screen_shows_unpaid_purchase_mark_paid_button(qapp, db_conn):
    owner = _owner(db_conn)
    flour_id = stock_items_repo.create_stock_item(db_conn, "دقيق", "g")
    stock_service.record_purchase(
        db_conn, None, "2026-01-01", [{"stock_item_id": flour_id, "qty": 100, "unit_cost_piasters": 10}], False, owner["id"]
    )
    screen = InventoryScreen(db_conn, owner)
    assert screen._purchases_table.rowCount() == 1
    assert screen._purchases_table.cellWidget(0, 4) is not None


def test_inventory_screen_lists_suppliers_with_amount_owed(qapp, db_conn):
    owner = _owner(db_conn)
    supplier_id = suppliers_repo.create_supplier(db_conn, "مورد الدقيق", "0100", None)
    flour_id = stock_items_repo.create_stock_item(db_conn, "دقيق", "g")
    stock_service.record_purchase(
        db_conn, supplier_id, "2026-01-01", [{"stock_item_id": flour_id, "qty": 100, "unit_cost_piasters": 10}], False, owner["id"]
    )
    screen = InventoryScreen(db_conn, owner)
    assert screen._suppliers_table.rowCount() == 1
    from derby.core.utils.money import format_egp

    assert screen._suppliers_table.item(0, 2).text() == format_egp(1000)
