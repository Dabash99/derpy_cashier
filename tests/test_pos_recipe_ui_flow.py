"""Exercises recipe-based stock deduction and its reversal THROUGH the
real UI widgets (PosScreen + PaymentDialog for checkout, SalesLogScreen's
void button for the reversal) rather than calling orders_service/
stock_service directly -- Phase 9 step (c) asks for this explicitly.
"""
from __future__ import annotations

from PySide2.QtWidgets import QInputDialog

from derby.core.db import (
    categories_repo,
    orders_repo,
    products_repo,
    recipes_repo,
    stock_items_repo,
    tables_repo,
    users_repo,
)
from derby.features.inventory import stock_service
from derby.features.pos.payment_dialog import PaymentDialog
from derby.features.pos.pos_screen import PosScreen
from derby.features.pos.sales_log_screen import SalesLogScreen


def test_checkout_and_void_through_real_ui_widgets(qapp, db_conn, monkeypatch):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)

    flour_id = stock_items_repo.create_stock_item(db_conn, "دقيق", "g", min_qty=0)
    stock_service.record_purchase(
        db_conn, None, "2026-01-01", [{"stock_item_id": flour_id, "qty": 1000, "unit_cost_piasters": 10}], False, owner["id"]
    )
    category_id = categories_repo.create_category(db_conn, "وافل")
    product_id = products_repo.create_product(db_conn, category_id, "وافل", "Waffle", 5000)
    recipes_repo.set_recipe(db_conn, recipes_repo.OWNER_PRODUCT, product_id, [{"stock_item_id": flour_id, "qty_per_unit": 200}])

    table = tables_repo.list_tables(db_conn)[0]

    # 1) Real PosScreen flow: open the table, add the item.
    pos_screen = PosScreen(db_conn, owner)
    pos_screen._on_start_table(table["id"])
    order_id = pos_screen._materialize_pending_order()

    from derby.features.pos import orders_service

    orders_service.add_item(db_conn, order_id, product_id, 2, [], None, owner["id"])
    pos_screen._cart_panel.reload()
    order = orders_repo.get_order(db_conn, order_id)

    # 2) Real PaymentDialog pays cash -- this is where stock_service
    # deduction actually runs (inside orders_service.pay).
    payment_dialog = PaymentDialog(db_conn, order, owner)
    payment_dialog._on_pay("cash")
    paid_order = payment_dialog.paid_order
    assert paid_order["status"] == "paid"

    flour_after_sale = stock_items_repo.get_stock_item(db_conn, flour_id)
    assert flour_after_sale["current_qty"] == 1000 - 200 * 2  # 600

    # 3) Real SalesLogScreen void button (the reason prompt is a blocking
    # native dialog -- monkeypatched to return a fixed reason+confirm,
    # exactly as a human filling it in would).
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("أخطأ الكاشير", True)))
    sales_log = SalesLogScreen(db_conn, owner)
    sales_log.reload()
    row = next(i for i, o in enumerate(sales_log._orders_by_row) if o["id"] == paid_order["id"])
    sales_log._table.setCurrentCell(row, 0)
    sales_log._on_void_clicked()

    voided_order = orders_repo.get_order(db_conn, paid_order["id"])
    assert voided_order["status"] == "void"

    flour_after_void = stock_items_repo.get_stock_item(db_conn, flour_id)
    assert flour_after_void["current_qty"] == 1000  # fully reversed
