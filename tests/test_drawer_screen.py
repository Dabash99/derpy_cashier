from __future__ import annotations

from derby.core.db import stock_items_repo, suppliers_repo, users_repo
from derby.features.inventory import drawer_service, stock_service
from derby.features.inventory.drawer_screen import DrawerScreen


def _owner(db_conn):
    user_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1234")
    return users_repo.get_user(db_conn, user_id)


def _cashier(db_conn):
    user_id = users_repo.create_user(db_conn, "Cashier", users_repo.ROLE_CASHIER, "5678")
    return users_repo.get_user(db_conn, user_id)


def test_drawer_screen_prompts_for_opening_balance_before_any_opening(qapp, db_conn):
    owner = _owner(db_conn)
    screen = DrawerScreen(db_conn, owner)
    assert screen._no_opening_label.isHidden() is False
    assert screen._expected_cash_label.isHidden() is True
    assert screen._deposit_button.isEnabled() is False


def test_drawer_screen_shows_expected_cash_after_opening(qapp, db_conn):
    owner = _owner(db_conn)
    drawer_service.open_drawer(db_conn, 5000, owner["id"])
    screen = DrawerScreen(db_conn, owner)
    assert screen._no_opening_label.isHidden() is True
    assert "50.00" in screen._expected_cash_label.text()


def test_drawer_screen_hides_goods_review_for_cashier(qapp, db_conn):
    cashier = _cashier(db_conn)
    screen = DrawerScreen(db_conn, cashier)
    assert screen._goods_review_title.isHidden() is True
    assert screen._stock_value_label.isHidden() is True


def test_drawer_screen_shows_goods_review_for_owner(qapp, db_conn):
    owner = _owner(db_conn)
    supplier_id = suppliers_repo.create_supplier(db_conn, "مورد", None, None)
    flour_id = stock_items_repo.create_stock_item(db_conn, "دقيق", "g", min_qty=500)
    stock_service.record_purchase(
        db_conn, supplier_id, "2026-01-01", [{"stock_item_id": flour_id, "qty": 100, "unit_cost_piasters": 10}], False, owner["id"]
    )
    screen = DrawerScreen(db_conn, owner)
    assert screen._goods_review_title.isHidden() is False
    assert "10.00" in screen._stock_value_label.text()
    assert screen.low_stock_count() == 1
