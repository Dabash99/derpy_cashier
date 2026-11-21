from __future__ import annotations

import pytest

from derby.core.db import (
    categories_repo,
    products_repo,
    recipes_repo,
    stock_items_repo,
    tables_repo,
    users_repo,
)
from derby.features.expenses import expenses_service
from derby.features.inventory import stock_service
from derby.features.pos import orders_service
from derby.features.reports import report_service


@pytest.fixture()
def owner(db_conn):
    user_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    return users_repo.get_user(db_conn, user_id)


@pytest.fixture()
def table(db_conn):
    return tables_repo.list_tables(db_conn)[0]


@pytest.fixture()
def waffle_with_recipe(db_conn, owner):
    flour_id = stock_items_repo.create_stock_item(db_conn, "دقيق", "g", min_qty=0)
    stock_service.record_purchase(
        db_conn, None, "2026-01-01", [{"stock_item_id": flour_id, "qty": 10000, "unit_cost_piasters": 1}], False, owner["id"]
    )
    category_id = categories_repo.create_category(db_conn, "وافل")
    product_id = products_repo.create_product(db_conn, category_id, "وافل", "Waffle", 5000)  # 50 EGP
    recipes_repo.set_recipe(db_conn, recipes_repo.OWNER_PRODUCT, product_id, [{"stock_item_id": flour_id, "qty_per_unit": 100}])
    return product_id  # cost per unit = 100g * 1 piaster/g = 100 piasters


def test_profit_report_computes_gross_and_net_without_double_counting(db_conn, owner, table, waffle_with_recipe):
    today = report_service.today_business_date(db_conn)

    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], waffle_with_recipe, 3, [], None, owner["id"])  # revenue 15000, cost 300
    orders_service.pay(db_conn, order["id"], "cash", owner)

    # A paid purchase on the same day files an expense under "مشتريات" --
    # this must NOT also be subtracted as an operating expense, since its
    # cost already flows into COGS via cost_at_sale_piasters.
    flour_id = stock_items_repo.list_stock_items(db_conn)[0]["id"]
    stock_service.record_purchase(
        db_conn, None, today.isoformat(), [{"stock_item_id": flour_id, "qty": 1000, "unit_cost_piasters": 1}], True, owner["id"]
    )
    # A genuine operating expense (rent) must still reduce net profit.
    rent_category = [c for c in __import__("derby.core.db.expense_categories_repo", fromlist=["x"]).list_categories(db_conn) if c["name"] == "إيجار"][0]
    expenses_service.create_expense(db_conn, rent_category["id"], 2000, today, "إيجار الشهر", owner["id"])

    report = report_service.build_report(db_conn, today, today)

    assert report.net_sales_piasters == 15000
    assert report.cogs_piasters == 300
    assert report.gross_profit_piasters == 15000 - 300
    # expenses_total includes BOTH the purchase expense (1000 piasters) and
    # rent (2000); operating_expenses must exclude the purchase one.
    assert report.expenses_total_piasters == 1000 + 2000
    assert report.operating_expenses_piasters == 2000
    assert report.net_profit_piasters == (15000 - 300) - 2000
    assert report.food_drinks_revenue_piasters == 15000


def test_top_items_by_profit_and_low_margin_flagging(db_conn, owner, table):
    flour_id = stock_items_repo.create_stock_item(db_conn, "دقيق", "g", min_qty=0)
    stock_service.record_purchase(
        db_conn, None, "2026-01-01", [{"stock_item_id": flour_id, "qty": 100000, "unit_cost_piasters": 1}], False, owner["id"]
    )
    category_id = categories_repo.create_category(db_conn, "منتجات")
    cheap_margin_id = products_repo.create_product(db_conn, category_id, "منتج هامش منخفض", "Low margin", 1000)  # 10 EGP
    recipes_repo.set_recipe(db_conn, recipes_repo.OWNER_PRODUCT, cheap_margin_id, [{"stock_item_id": flour_id, "qty_per_unit": 950}])  # cost 950, margin 5%
    good_margin_id = products_repo.create_product(db_conn, category_id, "منتج هامش جيد", "Good margin", 1000)
    recipes_repo.set_recipe(db_conn, recipes_repo.OWNER_PRODUCT, good_margin_id, [{"stock_item_id": flour_id, "qty_per_unit": 100}])  # cost 100, margin 90%

    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], cheap_margin_id, 1, [], None, owner["id"])
    orders_service.add_item(db_conn, order["id"], good_margin_id, 1, [], None, owner["id"])
    orders_service.pay(db_conn, order["id"], "cash", owner)

    today = report_service.today_business_date(db_conn)
    report = report_service.build_report(db_conn, today, today)

    names_by_profit = [i.name for i in report.top_items_by_profit]
    assert names_by_profit[0] == "منتج هامش جيد"  # 900 profit > 50 profit

    low_margin_names = [i.name for i in report.low_margin_items]
    assert "منتج هامش منخفض" in low_margin_names
    assert "منتج هامش جيد" not in low_margin_names


def test_waste_cost_appears_in_report(db_conn, owner):
    flour_id = stock_items_repo.create_stock_item(db_conn, "دقيق", "g", min_qty=0)
    stock_service.record_purchase(
        db_conn, None, "2026-01-01", [{"stock_item_id": flour_id, "qty": 1000, "unit_cost_piasters": 10}], False, owner["id"]
    )
    today = report_service.today_business_date(db_conn)
    stock_service.record_waste(db_conn, flour_id, 50, "تلف", owner["id"])
    report = report_service.build_report(db_conn, today, today)
    assert report.waste_cost_piasters == 500
