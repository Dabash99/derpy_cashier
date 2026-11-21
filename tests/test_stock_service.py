from __future__ import annotations

import pytest

from derby.core.db import (
    addons_repo,
    categories_repo,
    orders_repo,
    products_repo,
    recipes_repo,
    stock_items_repo,
    stock_movements_repo,
    tables_repo,
    users_repo,
)
from derby.features.expenses import expenses_service
from derby.features.inventory import stock_service
from derby.features.inventory.exceptions import InvalidQuantityError, WasteReasonRequiredError
from derby.features.pos import orders_service


@pytest.fixture()
def owner(db_conn):
    user_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    return users_repo.get_user(db_conn, user_id)


@pytest.fixture()
def flour(db_conn):
    item_id = stock_items_repo.create_stock_item(db_conn, "دقيق", "g", min_qty=500)
    return stock_items_repo.get_stock_item(db_conn, item_id)


@pytest.fixture()
def chocolate(db_conn):
    item_id = stock_items_repo.create_stock_item(db_conn, "شوكولاتة", "g", min_qty=100)
    return stock_items_repo.get_stock_item(db_conn, item_id)


@pytest.fixture()
def waffle(db_conn):
    category_id = categories_repo.create_category(db_conn, "وافل")
    product_id = products_repo.create_product(db_conn, category_id, "وافل", "Waffle", 5000)
    return products_repo.get_product(db_conn, product_id)


@pytest.fixture()
def table(db_conn):
    return tables_repo.list_tables(db_conn)[0]


# --- weighted average cost ---------------------------------------------


def test_record_purchase_sets_initial_avg_cost(db_conn, owner, flour):
    stock_service.record_purchase(
        db_conn, None, "2026-01-01", [{"stock_item_id": flour["id"], "qty": 1000, "unit_cost_piasters": 10}], False, owner["id"]
    )
    item = stock_items_repo.get_stock_item(db_conn, flour["id"])
    assert item["current_qty"] == 1000
    assert item["avg_cost_piasters"] == 10


def test_record_purchase_computes_weighted_average(db_conn, owner, flour):
    stock_service.record_purchase(
        db_conn, None, "2026-01-01", [{"stock_item_id": flour["id"], "qty": 1000, "unit_cost_piasters": 10}], False, owner["id"]
    )
    # 1000g @ 10 + 1000g @ 20 -> 2000g @ avg 15
    stock_service.record_purchase(
        db_conn, None, "2026-01-02", [{"stock_item_id": flour["id"], "qty": 1000, "unit_cost_piasters": 20}], False, owner["id"]
    )
    item = stock_items_repo.get_stock_item(db_conn, flour["id"])
    assert item["current_qty"] == 2000
    assert item["avg_cost_piasters"] == 15


def test_record_purchase_paid_files_expense_not_double_counted(db_conn, owner, flour):
    before = expenses_service.today_business_date  # sanity import check
    assert before is not None
    stock_service.record_purchase(
        db_conn, None, "2026-01-01", [{"stock_item_id": flour["id"], "qty": 1000, "unit_cost_piasters": 10}], True, owner["id"]
    )
    rows = db_conn.execute("SELECT * FROM expenses").fetchall()
    assert len(rows) == 1
    assert rows[0]["amount_piasters"] == 10000
    category = db_conn.execute("SELECT name FROM expense_categories WHERE id = ?", (rows[0]["category_id"],)).fetchone()
    assert category["name"] == "مشتريات"
    drawer_rows = db_conn.execute("SELECT * FROM drawer_entries WHERE entry_type = 'purchase'").fetchall()
    assert len(drawer_rows) == 1
    assert drawer_rows[0]["amount_delta_piasters"] == -10000


def test_mark_purchase_paid_later_files_expense_once(db_conn, owner, flour):
    purchase = stock_service.record_purchase(
        db_conn, None, "2026-01-01", [{"stock_item_id": flour["id"], "qty": 1000, "unit_cost_piasters": 10}], False, owner["id"]
    )
    assert db_conn.execute("SELECT COUNT(*) AS c FROM expenses").fetchone()["c"] == 0
    stock_service.mark_purchase_paid(db_conn, purchase["id"], owner["id"])
    assert db_conn.execute("SELECT COUNT(*) AS c FROM expenses").fetchone()["c"] == 1


def test_purchase_rejects_non_positive_qty(db_conn, owner, flour):
    with pytest.raises(InvalidQuantityError):
        stock_service.record_purchase(
            db_conn, None, "2026-01-01", [{"stock_item_id": flour["id"], "qty": 0, "unit_cost_piasters": 10}], False, owner["id"]
        )


# --- stock deduction with add-ons, at checkout --------------------------


def test_checkout_deducts_recipe_stock_including_addons(db_conn, owner, flour, chocolate, waffle, table):
    stock_service.record_purchase(
        db_conn, None, "2026-01-01", [{"stock_item_id": flour["id"], "qty": 1000, "unit_cost_piasters": 10}], False, owner["id"]
    )
    stock_service.record_purchase(
        db_conn, None, "2026-01-01", [{"stock_item_id": chocolate["id"], "qty": 500, "unit_cost_piasters": 40}], False, owner["id"]
    )
    recipes_repo.set_recipe(db_conn, recipes_repo.OWNER_PRODUCT, waffle["id"], [{"stock_item_id": flour["id"], "qty_per_unit": 100}])

    group_id = addons_repo.create_group(db_conn, "إضافات", min_select=0, max_select=1)
    addon_id = addons_repo.create_addon(db_conn, group_id, "شوكولاتة إضافية", 500)
    addons_repo.set_product_addon_groups(db_conn, waffle["id"], [group_id])
    recipes_repo.set_recipe(db_conn, recipes_repo.OWNER_ADDON, addon_id, [{"stock_item_id": chocolate["id"], "qty_per_unit": 30}])

    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    item = orders_service.add_item(db_conn, order["id"], waffle["id"], 2, [addon_id], None, owner["id"])

    orders_service.pay(db_conn, order["id"], "cash", owner)

    flour_after = stock_items_repo.get_stock_item(db_conn, flour["id"])
    chocolate_after = stock_items_repo.get_stock_item(db_conn, chocolate["id"])
    assert flour_after["current_qty"] == 1000 - 100 * 2
    assert chocolate_after["current_qty"] == 500 - 30 * 2

    paid_item = orders_repo.get_order_item(db_conn, item["id"])
    expected_cost = (100 * 2 * 10) + (30 * 2 * 40)
    assert paid_item["cost_at_sale_piasters"] == expected_cost


def test_checkout_with_no_recipe_sets_zero_cost(db_conn, owner, waffle, table):
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    item = orders_service.add_item(db_conn, order["id"], waffle["id"], 1, [], None, owner["id"])
    orders_service.pay(db_conn, order["id"], "cash", owner)
    paid_item = orders_repo.get_order_item(db_conn, item["id"])
    assert paid_item["cost_at_sale_piasters"] == 0


# --- negative stock is allowed, never blocks a sale ----------------------


def test_checkout_allows_negative_stock(db_conn, owner, flour, waffle, table):
    recipes_repo.set_recipe(db_conn, recipes_repo.OWNER_PRODUCT, waffle["id"], [{"stock_item_id": flour["id"], "qty_per_unit": 100}])
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], waffle["id"], 5, [], None, owner["id"])
    orders_service.pay(db_conn, order["id"], "cash", owner)  # no stock purchased -- should still succeed
    item = stock_items_repo.get_stock_item(db_conn, flour["id"])
    assert item["current_qty"] == -500
    low_stock = stock_items_repo.list_low_stock(db_conn)
    assert any(row["id"] == flour["id"] for row in low_stock)


# --- reversal on void ----------------------------------------------------


def test_void_reverses_stock_deductions(db_conn, owner, flour, waffle, table):
    stock_service.record_purchase(
        db_conn, None, "2026-01-01", [{"stock_item_id": flour["id"], "qty": 1000, "unit_cost_piasters": 10}], False, owner["id"]
    )
    recipes_repo.set_recipe(db_conn, recipes_repo.OWNER_PRODUCT, waffle["id"], [{"stock_item_id": flour["id"], "qty_per_unit": 100}])
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], waffle["id"], 2, [], None, owner["id"])
    orders_service.pay(db_conn, order["id"], "cash", owner)
    assert stock_items_repo.get_stock_item(db_conn, flour["id"])["current_qty"] == 800

    orders_service.void(db_conn, order["id"], "عميل غير راضٍ", owner)

    item = stock_items_repo.get_stock_item(db_conn, flour["id"])
    assert item["current_qty"] == 1000
    movements = stock_movements_repo.list_movements_for_item(db_conn, flour["id"])
    types = [m["movement_type"] for m in movements]
    assert types == ["purchase", "sale", "return"]


# --- waste / stocktake ----------------------------------------------------


def test_record_waste_requires_reason(db_conn, owner, flour):
    with pytest.raises(WasteReasonRequiredError):
        stock_service.record_waste(db_conn, flour["id"], 50, "", owner["id"])


def test_record_waste_reduces_qty(db_conn, owner, flour):
    stock_service.record_purchase(
        db_conn, None, "2026-01-01", [{"stock_item_id": flour["id"], "qty": 1000, "unit_cost_piasters": 10}], False, owner["id"]
    )
    stock_service.record_waste(db_conn, flour["id"], 100, "تلف", owner["id"])
    item = stock_items_repo.get_stock_item(db_conn, flour["id"])
    assert item["current_qty"] == 900
    assert item["avg_cost_piasters"] == 10  # waste never changes the average cost


def test_record_stocktake_creates_adjustment_for_difference(db_conn, owner, flour):
    stock_service.record_purchase(
        db_conn, None, "2026-01-01", [{"stock_item_id": flour["id"], "qty": 1000, "unit_cost_piasters": 10}], False, owner["id"]
    )
    stock_service.record_stocktake(db_conn, flour["id"], 950, owner["id"], note="جرد")
    item = stock_items_repo.get_stock_item(db_conn, flour["id"])
    assert item["current_qty"] == 950
    movements = stock_movements_repo.list_movements_for_item(db_conn, flour["id"])
    assert movements[-1]["movement_type"] == "adjustment"
    assert movements[-1]["qty_delta"] == -50


# --- repair: current_qty must always equal the sum of movements ---------


def test_recompute_current_qty_matches_movements(db_conn, owner, flour):
    stock_service.record_purchase(
        db_conn, None, "2026-01-01", [{"stock_item_id": flour["id"], "qty": 1000, "unit_cost_piasters": 10}], False, owner["id"]
    )
    stock_service.record_waste(db_conn, flour["id"], 200, "تلف", owner["id"])
    # Simulate drift: corrupt current_qty directly, bypassing the service.
    stock_items_repo.set_qty_and_cost(db_conn, flour["id"], 12345, 10)
    recomputed = stock_service.recompute_current_qty(db_conn, flour["id"])
    assert recomputed == 800
    assert stock_items_repo.get_stock_item(db_conn, flour["id"])["current_qty"] == 800
