from __future__ import annotations

from derby.core.db import stock_items_repo, suppliers_repo, users_repo
from derby.features.inventory import reorder_service, stock_service


def _owner(db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    return users_repo.get_user(db_conn, owner_id)


def test_reorder_list_groups_by_last_supplier(db_conn):
    owner = _owner(db_conn)
    supplier_id = suppliers_repo.create_supplier(db_conn, "مورد الألبان", None, None)
    item_id = stock_items_repo.create_stock_item(db_conn, "حليب", "l", min_qty=50)  # still low stock after the purchase below

    stock_service.record_purchase(
        db_conn, supplier_id, "2026-01-01", [{"stock_item_id": item_id, "qty": 20, "unit_cost_piasters": 2000}],
        False, owner["id"],
    )

    grouped = reorder_service.build_reorder_list(db_conn)
    assert "مورد الألبان" in grouped
    line = grouped["مورد الألبان"][0]
    assert line.stock_item["id"] == item_id


def test_no_purchase_history_groups_under_no_supplier(db_conn):
    stock_items_repo.create_stock_item(db_conn, "سكر", "kg", min_qty=5)
    grouped = reorder_service.build_reorder_list(db_conn)
    assert "بدون مورد" in grouped


def test_suggested_qty_uses_target_when_set(db_conn):
    owner = _owner(db_conn)
    item_id = stock_items_repo.create_stock_item(db_conn, "سكر", "kg", min_qty=5)
    reorder_service.set_target_qty(db_conn, item_id, 30, owner)

    grouped = reorder_service.build_reorder_list(db_conn)
    line = grouped["بدون مورد"][0]
    assert line.target_qty == 30
    assert line.suggested_qty == 30  # current_qty is 0

    row = db_conn.execute("SELECT * FROM audit_log WHERE action = 'reorder_target_changed'").fetchone()
    assert row is not None


def test_suggested_qty_falls_back_to_double_min_qty_when_no_target(db_conn):
    stock_items_repo.create_stock_item(db_conn, "سكر", "kg", min_qty=5)
    grouped = reorder_service.build_reorder_list(db_conn)
    line = grouped["بدون مورد"][0]
    assert line.target_qty == 10  # 5 * 2


def test_items_above_min_qty_never_appear(db_conn):
    item_id = stock_items_repo.create_stock_item(db_conn, "سكر", "kg", min_qty=5)
    stock_items_repo.set_qty_and_cost(db_conn, item_id, 100, 0)
    grouped = reorder_service.build_reorder_list(db_conn)
    assert grouped == {}


def test_build_plain_text_is_copyable_and_readable(db_conn):
    stock_items_repo.create_stock_item(db_conn, "سكر", "kg", min_qty=5)
    text = reorder_service.build_plain_text(db_conn, "ديربي")
    assert "ديربي" in text
    assert "سكر" in text
