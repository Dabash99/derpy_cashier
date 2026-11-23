from __future__ import annotations

import pytest

from derby.core.db import (
    categories_repo,
    customer_ledger_repo,
    products_repo,
    settings_repo,
    tables_repo,
    users_repo,
)
from derby.features.customers import customer_service
from derby.features.inventory import drawer_service
from derby.features.pos import orders_service
from derby.features.pos.exceptions import CreditNotAllowedError


def _owner_and_cashier(db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    cashier_id = users_repo.create_user(db_conn, "Cashier", users_repo.ROLE_CASHIER, "2222")
    return users_repo.get_user(db_conn, owner_id), users_repo.get_user(db_conn, cashier_id)


def _open_order(db_conn, user, price=2500):
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", price)
    table = tables_repo.list_tables(db_conn)[0]
    order = orders_service.get_or_create_table_order(db_conn, table["id"], user["id"])
    orders_service.add_item(db_conn, order["id"], product_id, 1, [], None, user["id"])
    return order


def test_credit_sale_creates_charge_and_does_not_touch_drawer(db_conn):
    owner, _cashier = _owner_and_cashier(db_conn)
    drawer_service.open_drawer(db_conn, 0, owner["id"])
    customer = customer_service.create_customer(db_conn, "محمد", "01000000000", None, None, owner)
    order = _open_order(db_conn, owner)

    before_cash = drawer_service.expected_cash_piasters(db_conn)
    paid = customer_service.credit_sale(db_conn, order["id"], customer["id"], owner)
    after_cash = drawer_service.expected_cash_piasters(db_conn)

    assert paid["status"] == "paid"
    assert paid["payment_method"] is None
    assert paid["customer_id"] == customer["id"]
    assert after_cash == before_cash  # آجل never touches the drawer
    assert customer_service.balance_piasters(db_conn, customer["id"]) == 2500

    row = db_conn.execute("SELECT * FROM audit_log WHERE action = 'credit_sale'").fetchone()
    assert row is not None


def test_credit_sale_counts_as_revenue_in_reports(db_conn):
    from derby.features.reports import report_service

    owner, _cashier = _owner_and_cashier(db_conn)
    customer = customer_service.create_customer(db_conn, "محمد", None, None, None, owner)
    order = _open_order(db_conn, owner)
    customer_service.credit_sale(db_conn, order["id"], customer["id"], owner)

    today = report_service.today_business_date(db_conn)
    report = report_service.build_report(db_conn, today, today)
    assert report.net_sales_piasters == 2500
    assert report.payment_methods["credit"].total_piasters == 2500
    assert report.payment_methods["cash"].total_piasters == 0


def test_voiding_a_credit_sale_reverses_the_ledger(db_conn):
    owner, _cashier = _owner_and_cashier(db_conn)
    customer = customer_service.create_customer(db_conn, "محمد", None, None, None, owner)
    order = _open_order(db_conn, owner)
    paid = customer_service.credit_sale(db_conn, order["id"], customer["id"], owner)
    assert customer_service.balance_piasters(db_conn, customer["id"]) == 2500

    orders_service.void(db_conn, paid["id"], "خطأ", owner)
    assert customer_service.balance_piasters(db_conn, customer["id"]) == 0

    row = db_conn.execute("SELECT * FROM audit_log WHERE action = 'credit_sale_void_reversed'").fetchone()
    assert row is not None


def test_cashier_cannot_sell_on_credit_when_setting_disabled(db_conn):
    owner, cashier = _owner_and_cashier(db_conn)
    settings_repo.set_value(db_conn, "cashiers_may_sell_on_credit", "0")
    customer = customer_service.create_customer(db_conn, "محمد", None, None, None, owner)
    order = _open_order(db_conn, cashier)

    with pytest.raises(CreditNotAllowedError):
        customer_service.credit_sale(db_conn, order["id"], customer["id"], cashier)


def test_exceeding_credit_limit_requires_owner_pin(db_conn):
    from derby.features.pos.exceptions import WrongApprovalPinError

    owner, cashier = _owner_and_cashier(db_conn)
    customer = customer_service.create_customer(db_conn, "محمد", None, None, 1000, owner)  # limit 10 EGP
    order = _open_order(db_conn, cashier, price=2500)  # 25 EGP > limit

    with pytest.raises(WrongApprovalPinError):
        customer_service.credit_sale(db_conn, order["id"], customer["id"], cashier, approving_pin="9999")

    # correct owner PIN succeeds
    paid = customer_service.credit_sale(db_conn, order["id"], customer["id"], cashier, approving_pin="1111")
    assert paid["status"] == "paid"
    exceed_row = db_conn.execute("SELECT * FROM audit_log WHERE action = 'credit_limit_exceeded_approved'").fetchone()
    assert exceed_row is not None


def test_cash_payment_reduces_balance_and_adds_cash_to_drawer(db_conn):
    owner, _cashier = _owner_and_cashier(db_conn)
    drawer_service.open_drawer(db_conn, 0, owner["id"])
    customer = customer_service.create_customer(db_conn, "محمد", None, None, None, owner)
    order = _open_order(db_conn, owner)
    customer_service.credit_sale(db_conn, order["id"], customer["id"], owner)

    before_cash = drawer_service.expected_cash_piasters(db_conn)
    customer_service.record_payment(db_conn, customer["id"], 1000, "cash", owner)
    after_cash = drawer_service.expected_cash_piasters(db_conn)

    assert customer_service.balance_piasters(db_conn, customer["id"]) == 1500
    assert after_cash == before_cash + 1000


def test_instapay_payment_reduces_balance_but_not_drawer(db_conn):
    owner, _cashier = _owner_and_cashier(db_conn)
    drawer_service.open_drawer(db_conn, 0, owner["id"])
    customer = customer_service.create_customer(db_conn, "محمد", None, None, None, owner)
    order = _open_order(db_conn, owner)
    customer_service.credit_sale(db_conn, order["id"], customer["id"], owner)

    before_cash = drawer_service.expected_cash_piasters(db_conn)
    customer_service.record_payment(db_conn, customer["id"], 1000, "instapay", owner)
    after_cash = drawer_service.expected_cash_piasters(db_conn)

    assert customer_service.balance_piasters(db_conn, customer["id"]) == 1500
    assert after_cash == before_cash  # InstaPay never touches the drawer


def test_statement_math_running_balance(db_conn):
    owner, _cashier = _owner_and_cashier(db_conn)
    customer = customer_service.create_customer(db_conn, "محمد", None, None, None, owner)
    order = _open_order(db_conn, owner)
    customer_service.credit_sale(db_conn, order["id"], customer["id"], owner)
    customer_service.record_payment(db_conn, customer["id"], 1000, "cash", owner)

    entries = customer_ledger_repo.list_for_customer(db_conn, customer["id"])
    running = sum(e["amount_piasters"] for e in entries)
    assert running == 1500
    assert running == customer_service.balance_piasters(db_conn, customer["id"])
