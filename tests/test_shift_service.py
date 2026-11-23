from __future__ import annotations

import pytest

from derby.core.db import categories_repo, products_repo, tables_repo, users_repo
from derby.features.pos import orders_service
from derby.features.shifts import shift_service
from derby.features.shifts.exceptions import ShiftAlreadyOpenError


def _owner_and_cashier(db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    cashier_id = users_repo.create_user(db_conn, "Cashier", users_repo.ROLE_CASHIER, "2222")
    return users_repo.get_user(db_conn, owner_id), users_repo.get_user(db_conn, cashier_id)


def _paid_order(db_conn, user, method="cash"):
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 2500)
    table = tables_repo.list_tables(db_conn)[0]
    order = orders_service.get_or_create_table_order(db_conn, table["id"], user["id"])
    orders_service.add_item(db_conn, order["id"], product_id, 1, [], None, user["id"])
    return orders_service.pay(db_conn, order["id"], method, user)


def test_open_shift_opens_drawer_when_none_open(db_conn):
    owner, _cashier = _owner_and_cashier(db_conn)
    shift = shift_service.open_shift(db_conn, owner, 10000)
    assert shift["status"] == "open"
    assert shift["opening_cash_piasters"] == 10000

    row = db_conn.execute("SELECT * FROM audit_log WHERE action = 'shift_opened'").fetchone()
    assert row is not None


def test_cannot_open_two_shifts_at_once(db_conn):
    owner, _cashier = _owner_and_cashier(db_conn)
    shift_service.open_shift(db_conn, owner, 10000)
    with pytest.raises(ShiftAlreadyOpenError):
        shift_service.open_shift(db_conn, owner, 5000)


def test_shift_report_matches_orders_and_drawer(db_conn):
    owner, _cashier = _owner_and_cashier(db_conn)
    shift = shift_service.open_shift(db_conn, owner, 10000)
    _paid_order(db_conn, owner, "cash")
    _paid_order(db_conn, owner, "instapay")

    report = shift_service.build_shift_report(db_conn, shift_service.get_open_shift(db_conn))
    assert report.sales_by_method_piasters["cash"] == 2500
    assert report.sales_by_method_piasters["instapay"] == 2500
    assert report.order_count == 2
    assert report.expected_cash_piasters == 10000 + 2500  # opening + the cash sale only

    closed, closing_report = shift_service.close_shift(db_conn, shift, 12500, None, owner)
    assert closed["status"] == "closed"
    assert closing_report.difference_piasters == 0


def test_handover_closes_and_reopens_in_one_flow(db_conn):
    owner, cashier = _owner_and_cashier(db_conn)
    shift = shift_service.open_shift(db_conn, owner, 10000)
    _paid_order(db_conn, owner, "cash")

    closed, _report, new_shift = shift_service.handover_shift(db_conn, shift, 12500, "تسليم عادي", owner, cashier)
    assert closed["status"] == "closed"
    assert closed["handed_over_to_user_id"] == cashier["id"]
    assert new_shift["status"] == "open"
    assert new_shift["user_id"] == cashier["id"]
    assert new_shift["opening_cash_piasters"] == 12500

    handover_row = db_conn.execute("SELECT * FROM audit_log WHERE action = 'shift_handover'").fetchone()
    assert handover_row is not None


def test_require_open_shift_setting_blocks_payment_without_one(db_conn):
    from derby.core.db import settings_repo
    from derby.features.pos.exceptions import ShiftRequiredError

    owner, _cashier = _owner_and_cashier(db_conn)
    settings_repo.set_value(db_conn, "require_open_shift", "1")
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 2500)
    table = tables_repo.list_tables(db_conn)[0]
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], product_id, 1, [], None, owner["id"])

    with pytest.raises(ShiftRequiredError):
        orders_service.pay(db_conn, order["id"], "cash", owner)

    shift_service.open_shift(db_conn, owner, 0)
    paid = orders_service.pay(db_conn, order["id"], "cash", owner)
    assert paid["status"] == "paid"
