from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from derby.core.db import addons_repo, categories_repo, orders_repo, products_repo, tables_repo, users_repo
from derby.features.auth import lockout
from derby.features.pos import orders_service
from derby.features.pos.exceptions import (
    AddonSelectionError,
    ApprovalLockedOutError,
    DiscountExceedsSubtotalError,
    DiscountReasonRequiredError,
    InvalidTransitionError,
    PermissionDeniedError,
    QuantityOutOfRangeError,
    TableBusyError,
    WrongApprovalPinError,
)


@pytest.fixture()
def owner(db_conn):
    user_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    return users_repo.get_user(db_conn, user_id)


@pytest.fixture()
def cashier(db_conn):
    user_id = users_repo.create_user(db_conn, "Cashier", users_repo.ROLE_CASHIER, "2222")
    return users_repo.get_user(db_conn, user_id)


@pytest.fixture()
def product(db_conn):
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "Coffee", 2500)
    return products_repo.get_product(db_conn, product_id)


@pytest.fixture()
def table(db_conn):
    return tables_repo.list_tables(db_conn)[0]


# --- opening orders / one-open-per-table / takeaway multiples ------------


def test_get_or_create_table_order_reuses_open_order(db_conn, owner, table):
    first = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    second = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    assert first["id"] == second["id"]


def test_takeaway_orders_are_always_new(db_conn, owner):
    first = orders_service.create_takeaway_order(db_conn, owner["id"])
    second = orders_service.create_takeaway_order(db_conn, owner["id"])
    assert first["id"] != second["id"]
    assert first["table_id"] is None
    assert second["table_id"] is None


# --- cart math: add, merge, qty, remove, addons ---------------------------


def test_add_item_updates_totals(db_conn, owner, table, product):
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], product["id"], 2, [], None, owner["id"])
    refreshed = orders_repo.get_order(db_conn, order["id"])
    assert refreshed["subtotal_piasters"] == 5000
    assert refreshed["total_piasters"] == 5000


def test_add_item_rejects_qty_out_of_range(db_conn, owner, table, product):
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    with pytest.raises(QuantityOutOfRangeError):
        orders_service.add_item(db_conn, order["id"], product["id"], 0, [], None, owner["id"])
    with pytest.raises(QuantityOutOfRangeError):
        orders_service.add_item(db_conn, order["id"], product["id"], 100, [], None, owner["id"])


def test_same_product_same_addons_no_note_merges(db_conn, owner, table, product):
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], product["id"], 1, [], None, owner["id"])
    item2 = orders_service.add_item(db_conn, order["id"], product["id"], 2, [], None, owner["id"])
    items = orders_repo.list_order_items(db_conn, order["id"])
    assert len(items) == 1
    assert item2["qty"] == 3


def test_a_note_prevents_merging(db_conn, owner, table, product):
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], product["id"], 1, [], "سكر زيادة", owner["id"])
    orders_service.add_item(db_conn, order["id"], product["id"], 1, [], None, owner["id"])
    assert len(orders_repo.list_order_items(db_conn, order["id"])) == 2


def test_different_addons_do_not_merge(db_conn, owner, table, product):
    group_id = addons_repo.create_group(db_conn, "الحجم", min_select=0, max_select=1)
    small = addons_repo.create_addon(db_conn, group_id, "صغير", 0)
    large = addons_repo.create_addon(db_conn, group_id, "كبير", 500)
    addons_repo.set_product_addon_groups(db_conn, product["id"], [group_id])

    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], product["id"], 1, [small], None, owner["id"])
    orders_service.add_item(db_conn, order["id"], product["id"], 1, [large], None, owner["id"])
    assert len(orders_repo.list_order_items(db_conn, order["id"])) == 2


def test_merge_exceeding_99_is_rejected(db_conn, owner, table, product):
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], product["id"], 98, [], None, owner["id"])
    with pytest.raises(QuantityOutOfRangeError):
        orders_service.add_item(db_conn, order["id"], product["id"], 5, [], None, owner["id"])


def test_addon_price_included_in_line_total(db_conn, owner, table, product):
    group_id = addons_repo.create_group(db_conn, "الحجم", min_select=1, max_select=1)
    large = addons_repo.create_addon(db_conn, group_id, "كبير", 500)
    addons_repo.set_product_addon_groups(db_conn, product["id"], [group_id])

    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    item = orders_service.add_item(db_conn, order["id"], product["id"], 2, [large], None, owner["id"])
    # (2500 base + 500 addon) * 2 qty = 6000
    assert item["line_total_piasters"] == 6000


def test_addon_min_select_violation_raises(db_conn, owner, table, product):
    group_id = addons_repo.create_group(db_conn, "الحجم", min_select=1, max_select=1)
    addons_repo.set_product_addon_groups(db_conn, product["id"], [group_id])
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    with pytest.raises(AddonSelectionError):
        orders_service.add_item(db_conn, order["id"], product["id"], 1, [], None, owner["id"])


def test_change_qty_updates_totals(db_conn, owner, table, product):
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    item = orders_service.add_item(db_conn, order["id"], product["id"], 1, [], None, owner["id"])
    orders_service.change_qty(db_conn, order["id"], item["id"], 4)
    refreshed = orders_repo.get_order(db_conn, order["id"])
    assert refreshed["subtotal_piasters"] == 10000


def test_remove_item_updates_totals(db_conn, owner, table, product):
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    item = orders_service.add_item(db_conn, order["id"], product["id"], 1, [], None, owner["id"])
    orders_service.remove_item(db_conn, order["id"], item["id"])
    refreshed = orders_repo.get_order(db_conn, order["id"])
    assert refreshed["subtotal_piasters"] == 0
    assert orders_repo.list_order_items(db_conn, order["id"]) == []


# --- snapshots unaffected by later menu edits -----------------------------


def test_snapshots_survive_later_price_and_name_changes(db_conn, owner, table, product):
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    item = orders_service.add_item(db_conn, order["id"], product["id"], 1, [], None, owner["id"])

    products_repo.update_product(db_conn, product["id"], product["category_id"], "لاتيه", "Latte", 9999, None, True)

    unchanged = orders_repo.get_order_item(db_conn, item["id"])
    assert unchanged["name_snapshot"] == "قهوة"
    assert unchanged["unit_price_snapshot_piasters"] == 2500


# --- discounts -------------------------------------------------------------


def test_owner_applies_discount_directly(db_conn, owner, table, product):
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], product["id"], 2, [], None, owner["id"])  # 5000
    updated = orders_service.apply_discount(db_conn, order["id"], "percent", 10, "زبون دائم", owner)
    assert updated["discount_piasters"] == 500
    assert updated["total_piasters"] == 4500
    assert updated["discount_approved_by"] == owner["id"]


def test_discount_requires_a_reason(db_conn, owner, table, product):
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], product["id"], 1, [], None, owner["id"])
    with pytest.raises(DiscountReasonRequiredError):
        orders_service.apply_discount(db_conn, order["id"], "percent", 10, "", owner)


def test_discount_cannot_exceed_subtotal(db_conn, owner, table, product):
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], product["id"], 1, [], None, owner["id"])  # 2500
    with pytest.raises(DiscountExceedsSubtotalError):
        orders_service.apply_discount(db_conn, order["id"], "fixed", 3000, "too much", owner)


def test_cashier_discount_requires_owner_pin(db_conn, owner, cashier, table, product):
    order = orders_service.get_or_create_table_order(db_conn, table["id"], cashier["id"])
    orders_service.add_item(db_conn, order["id"], product["id"], 1, [], None, cashier["id"])

    with pytest.raises(WrongApprovalPinError):
        orders_service.apply_discount(db_conn, order["id"], "fixed", 100, "test", cashier, approving_pin="9999")


def test_cashiers_own_pin_is_never_accepted_as_approval(db_conn, owner, cashier, table, product):
    order = orders_service.get_or_create_table_order(db_conn, table["id"], cashier["id"])
    orders_service.add_item(db_conn, order["id"], product["id"], 1, [], None, cashier["id"])
    with pytest.raises(WrongApprovalPinError):
        orders_service.apply_discount(db_conn, order["id"], "fixed", 100, "test", cashier, approving_pin="2222")


def test_correct_owner_pin_approves_and_logs_both_users(db_conn, owner, cashier, table, product):
    order = orders_service.get_or_create_table_order(db_conn, table["id"], cashier["id"])
    orders_service.add_item(db_conn, order["id"], product["id"], 1, [], None, cashier["id"])

    updated = orders_service.apply_discount(db_conn, order["id"], "fixed", 100, "test", cashier, approving_pin="1111")
    assert updated["discount_approved_by"] == owner["id"]

    log_row = db_conn.execute(
        "SELECT * FROM audit_log WHERE action = 'discount_applied'"
    ).fetchone()
    assert log_row["user_id"] == cashier["id"]
    assert "approved_by={0}".format(owner["id"]) in log_row["details"]


def test_wrong_owner_pin_counts_toward_global_lockout(db_conn, owner, cashier, table, product):
    order = orders_service.get_or_create_table_order(db_conn, table["id"], cashier["id"])
    orders_service.add_item(db_conn, order["id"], product["id"], 1, [], None, cashier["id"])

    for _ in range(5):
        with pytest.raises(WrongApprovalPinError):
            orders_service.apply_discount(db_conn, order["id"], "fixed", 100, "test", cashier, approving_pin="0000")

    assert lockout.is_locked(db_conn) is True

    with pytest.raises(ApprovalLockedOutError):
        orders_service.apply_discount(db_conn, order["id"], "fixed", 100, "test", cashier, approving_pin="1111")


def test_remove_discount(db_conn, owner, table, product):
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], product["id"], 1, [], None, owner["id"])
    orders_service.apply_discount(db_conn, order["id"], "fixed", 100, "test", owner)
    updated = orders_service.remove_discount(db_conn, order["id"], owner)
    assert updated["discount_piasters"] == 0
    assert updated["total_piasters"] == updated["subtotal_piasters"]


# --- cancel ----------------------------------------------------------------


def test_cancel_empty_order_needs_no_approval(db_conn, cashier, table):
    order = orders_service.get_or_create_table_order(db_conn, table["id"], cashier["id"])
    cancelled = orders_service.cancel(db_conn, order["id"], cashier)
    assert cancelled["status"] == "cancelled"


def test_cancel_nonempty_order_as_cashier_needs_approval(db_conn, cashier, table, product):
    order = orders_service.get_or_create_table_order(db_conn, table["id"], cashier["id"])
    orders_service.add_item(db_conn, order["id"], product["id"], 1, [], None, cashier["id"])
    with pytest.raises(WrongApprovalPinError):
        orders_service.cancel(db_conn, order["id"], cashier, approving_pin="0000")


def test_cancel_nonempty_order_as_owner_is_direct(db_conn, owner, table, product):
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], product["id"], 1, [], None, owner["id"])
    cancelled = orders_service.cancel(db_conn, order["id"], owner)
    assert cancelled["status"] == "cancelled"


# --- state machine -----------------------------------------------------------


def test_cannot_add_item_to_a_paid_order(db_conn, owner, table, product):
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], product["id"], 1, [], None, owner["id"])
    orders_service.pay(db_conn, order["id"], "cash", owner)
    with pytest.raises(InvalidTransitionError):
        orders_service.add_item(db_conn, order["id"], product["id"], 1, [], None, owner["id"])


def test_cannot_pay_twice(db_conn, owner, table, product):
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], product["id"], 1, [], None, owner["id"])
    orders_service.pay(db_conn, order["id"], "cash", owner)
    with pytest.raises(InvalidTransitionError):
        orders_service.pay(db_conn, order["id"], "cash", owner)


def test_cannot_cancel_a_paid_order(db_conn, owner, table, product):
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], product["id"], 1, [], None, owner["id"])
    orders_service.pay(db_conn, order["id"], "cash", owner)
    with pytest.raises(InvalidTransitionError):
        orders_service.cancel(db_conn, order["id"], owner)


def test_void_requires_paid_status(db_conn, owner, table, product):
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    with pytest.raises(InvalidTransitionError):
        orders_service.void(db_conn, order["id"], "reason", owner)


def test_void_paid_order_as_owner(db_conn, owner, table, product):
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], product["id"], 1, [], None, owner["id"])
    orders_service.pay(db_conn, order["id"], "cash", owner)
    voided = orders_service.void(db_conn, order["id"], "طلب العميل", owner)
    assert voided["status"] == "void"
    assert voided["void_reason"] == "طلب العميل"


def test_void_rejected_for_cashier(db_conn, owner, cashier, table, product):
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], product["id"], 1, [], None, owner["id"])
    orders_service.pay(db_conn, order["id"], "cash", owner)
    with pytest.raises(PermissionDeniedError):
        orders_service.void(db_conn, order["id"], "reason", cashier)


def test_void_requires_a_reason(db_conn, owner, table, product):
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], product["id"], 1, [], None, owner["id"])
    orders_service.pay(db_conn, order["id"], "cash", owner)
    with pytest.raises(Exception):
        orders_service.void(db_conn, order["id"], "", owner)


# --- one open order per table / move_order ----------------------------------


def test_only_one_open_order_per_table(db_conn, owner, table):
    first = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    second = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    assert first["id"] == second["id"]
    open_orders = db_conn.execute(
        "SELECT COUNT(*) AS n FROM orders WHERE table_id = ? AND status = 'open'", (table["id"],)
    ).fetchone()
    assert open_orders["n"] == 1


def test_move_order_rejects_busy_target(db_conn, owner):
    tables = tables_repo.list_tables(db_conn)
    table_a, table_b = tables[0], tables[1]
    order_a = orders_service.get_or_create_table_order(db_conn, table_a["id"], owner["id"])
    orders_service.get_or_create_table_order(db_conn, table_b["id"], owner["id"])  # table_b is now busy

    with pytest.raises(TableBusyError):
        orders_service.move_order(db_conn, order_a["id"], table_b["id"], owner)


def test_move_order_to_free_table_succeeds(db_conn, owner):
    tables = tables_repo.list_tables(db_conn)
    table_a, table_b = tables[0], tables[1]
    order_a = orders_service.get_or_create_table_order(db_conn, table_a["id"], owner["id"])

    moved = orders_service.move_order(db_conn, order_a["id"], table_b["id"], owner)
    assert moved["table_id"] == table_b["id"]

    log_row = db_conn.execute("SELECT * FROM audit_log WHERE action = 'order_moved'").fetchone()
    assert "from_table={0}".format(table_a["id"]) in log_row["details"]
    assert "to_table={0}".format(table_b["id"]) in log_row["details"]


def test_move_takeaway_to_table(db_conn, owner):
    takeaway = orders_service.create_takeaway_order(db_conn, owner["id"])
    table_a = tables_repo.list_tables(db_conn)[0]
    moved = orders_service.move_order(db_conn, takeaway["id"], table_a["id"], owner)
    assert moved["table_id"] == table_a["id"]


# --- invoice numbers / business_date ---------------------------------------


def test_invoice_numbers_have_no_gaps(db_conn, owner, product):
    tables = tables_repo.list_tables(db_conn)
    invoice_numbers = []
    for t in tables:
        order = orders_service.get_or_create_table_order(db_conn, t["id"], owner["id"])
        orders_service.add_item(db_conn, order["id"], product["id"], 1, [], None, owner["id"])
        paid = orders_service.pay(db_conn, order["id"], "cash", owner)
        invoice_numbers.append(paid["invoice_no"])
    assert invoice_numbers == sorted(invoice_numbers)
    assert invoice_numbers == list(range(invoice_numbers[0], invoice_numbers[0] + len(invoice_numbers)))


def test_cancelled_order_consumes_no_invoice_number(db_conn, owner, product):
    tables = tables_repo.list_tables(db_conn)
    order_a = orders_service.get_or_create_table_order(db_conn, tables[0]["id"], owner["id"])
    orders_service.add_item(db_conn, order_a["id"], product["id"], 1, [], None, owner["id"])
    orders_service.cancel(db_conn, order_a["id"], owner)

    order_b = orders_service.get_or_create_table_order(db_conn, tables[1]["id"], owner["id"])
    orders_service.add_item(db_conn, order_b["id"], product["id"], 1, [], None, owner["id"])
    paid = orders_service.pay(db_conn, order_b["id"], "cash", owner)
    assert paid["invoice_no"] == 1


def test_business_date_follows_close_time_rule(db_conn, owner, product, monkeypatch):
    from derby.core.db import settings_repo

    settings_repo.set_value(db_conn, "business_close_time", "03:00")

    table_a = tables_repo.list_tables(db_conn)[0]
    order = orders_service.get_or_create_table_order(db_conn, table_a["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], product["id"], 1, [], None, owner["id"])

    # 01:30 Cairo time with close_time 03:00 belongs to the PREVIOUS business day.
    from derby.core.utils.time_utils import to_cairo

    offset = to_cairo(datetime(2024, 1, 10, 12, 0, tzinfo=timezone.utc)).utcoffset()
    cairo_0130 = datetime(2024, 1, 10, 1, 30, 0)
    utc_at_0130 = (cairo_0130 - offset).replace(tzinfo=timezone.utc)

    monkeypatch.setattr("derby.features.pos.orders_service.utc_now", lambda: utc_at_0130)
    paid = orders_service.pay(db_conn, order["id"], "cash", owner)
    assert paid["business_date"] == date(2024, 1, 9).isoformat()


# --- persistence -------------------------------------------------------------


def test_order_survives_reopening_the_db_mid_order(tmp_path):
    from derby.core.db import settings_repo as settings_repo_mod
    from derby.core.db.connection import connect
    from derby.core.db.migrations import run_pending_migrations

    db_path = tmp_path / "persist.db"
    conn = connect(db_path)
    run_pending_migrations(conn)
    settings_repo_mod.ensure_defaults(conn)
    owner_id = users_repo.create_user(conn, "Owner", users_repo.ROLE_OWNER, "1111")
    category_id = categories_repo.create_category(conn, "مشروبات")
    product_id = products_repo.create_product(conn, category_id, "قهوة", "", 2500)
    table_a = tables_repo.list_tables(conn)[0]

    order = orders_service.get_or_create_table_order(conn, table_a["id"], owner_id)
    orders_service.add_item(conn, order["id"], product_id, 2, [], None, owner_id)
    conn.close()

    reconnected = connect(db_path)
    reopened_order = orders_repo.get_open_order_for_table(reconnected, table_a["id"])
    assert reopened_order is not None
    assert reopened_order["subtotal_piasters"] == 5000
    items = orders_repo.list_order_items(reconnected, reopened_order["id"])
    assert len(items) == 1
    assert items[0]["qty"] == 2
    reconnected.close()


# --- "من يوم سابق" badge -----------------------------------------------------


def test_is_from_previous_business_day(db_conn, owner, table, monkeypatch):
    from derby.core.db import settings_repo

    settings_repo.set_value(db_conn, "business_close_time", "03:00")

    from derby.core.utils.time_utils import to_cairo

    offset = to_cairo(datetime(2024, 1, 10, 12, 0, tzinfo=timezone.utc)).utcoffset()

    # Order opened at 01:00 Cairo time (still "yesterday" with close_time 03:00).
    cairo_0100 = datetime(2024, 1, 10, 1, 0, 0)
    opened_utc = (cairo_0100 - offset).replace(tzinfo=timezone.utc)
    monkeypatch.setattr("derby.features.pos.orders_service.utc_now", lambda: opened_utc)
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])

    # "Now" has moved on to the next business day (same calendar day, after close time).
    cairo_1000 = datetime(2024, 1, 10, 10, 0, 0)
    now_utc = (cairo_1000 - offset).replace(tzinfo=timezone.utc)
    monkeypatch.setattr("derby.features.pos.orders_service.utc_now", lambda: now_utc)

    assert orders_service.is_from_previous_business_day(db_conn, order) is True


def test_is_not_from_previous_business_day_when_opened_today(db_conn, owner, table):
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    assert orders_service.is_from_previous_business_day(db_conn, order) is False
