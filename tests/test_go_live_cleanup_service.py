"""Item H of the UI fix pass: the owner-only go-live cleanup must wipe
every row of operational/test data while keeping users, settings, the
menu, PlayStation devices/rates, tables, and expense
categories/recurring templates -- and must abort (deleting nothing) if
the PIN is wrong, the confirmation word is wrong, or the safety backup
fails.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from derby.core.db import (
    addons_repo,
    backup_log_repo,
    categories_repo,
    day_closures_repo,
    expense_categories_repo,
    products_repo,
    ps_devices_repo,
    recurring_expenses_repo,
    settings_repo,
    tables_repo,
    users_repo,
)
from derby.core.utils.time_utils import utc_now
from derby.features.closing import backup_service
from derby.features.expenses import expenses_service
from derby.features.playstation import ps_service
from derby.features.pos import orders_service
from derby.features.pos.exceptions import WrongApprovalPinError
from derby.features.settings import go_live_cleanup_service
from derby.features.settings.exceptions import ConfirmationWordMismatchError
from derby.features.supplies import supplies_service

_OPERATIONAL_TABLES = (
    "order_item_addons", "ps_sessions", "order_items", "orders",
    "supplies", "expenses", "day_closures", "backup_log",
)


def _row_count(conn, table):
    return conn.execute("SELECT COUNT(*) FROM {0}".format(table)).fetchone()[0]


@pytest.fixture()
def populated(db_conn, tmp_path):
    """A database with real rows in every table the cleanup must both
    wipe and keep, plus the settings it needs to find a backup folder."""
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    settings_repo.set_value(db_conn, "backup_folder_primary", str(tmp_path / "backups"))

    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "Coffee", 2500)
    group_id = addons_repo.create_group(db_conn, "الحجم", min_select=1, max_select=1)
    addon_id = addons_repo.create_addon(db_conn, group_id, "كبير", 500)
    addons_repo.set_product_addon_groups(db_conn, product_id, [group_id])

    table = tables_repo.list_tables(db_conn)[0]
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner_id)
    orders_service.add_item(db_conn, order["id"], product_id, 1, [addon_id], None, owner_id)
    orders_service.pay(db_conn, order["id"], "cash", owner)

    device = ps_devices_repo.list_devices(db_conn)[0]
    ps_devices_repo.set_rates(db_conn, device["id"], 4000, 6000)
    t0 = utc_now()
    ps_service.start_session(db_conn, device["id"], "single", owner_id, now=t0)
    ps_service.stop_session(db_conn, device["id"], owner_id, now=t0 + timedelta(minutes=35))

    expense_category = expense_categories_repo.list_categories(db_conn)[0]
    expenses_service.create_expense(
        db_conn, expense_category["id"], 1000, expenses_service.today_business_date(db_conn), "فاتورة كهرباء", owner_id
    )
    recurring_expenses_repo.create_template(db_conn, expense_category["id"], "إيجار شهري", 50000, 1)

    supplies_service.add_supply(db_conn, "سكر", None, supplies_service.PRIORITY_NORMAL, None, owner_id)

    day_closures_repo.create_closure(db_conn, "2024-01-01", "manual", "تقرير تجريبي", 1, 2500, 1000, 1500, 0, 0)
    backup_log_repo.log_backup(db_conn, "manual", "primary", "ok", path="x.db", verified=True)

    return db_conn, owner, tmp_path


def test_cleanup_wipes_operational_tables_and_keeps_everything_else(populated):
    conn, owner, tmp_path = populated
    kept_users_before = users_repo.list_users(conn)
    kept_tables_before = tables_repo.list_tables(conn)
    kept_devices_before = ps_devices_repo.list_devices(conn)
    kept_categories_before = categories_repo.list_categories(conn)
    kept_products_before = products_repo.list_products(conn)
    kept_expense_categories_before = expense_categories_repo.list_categories(conn)
    kept_recurring_before = recurring_expenses_repo.list_templates(conn)

    for table in _OPERATIONAL_TABLES:
        assert _row_count(conn, table) > 0  # sanity: the fixture actually populated it

    result = go_live_cleanup_service.run_cleanup(
        conn, tmp_path / "test_derby.db", tmp_path / "backups", utc_now(), owner, "1111", "تصفية"
    )

    for table in _OPERATIONAL_TABLES:
        assert _row_count(conn, table) == 0
    # audit_log is append-only (Phase 11): the cleanup no longer wipes it,
    # it only adds its own "go_live_cleanup" row on top of whatever the
    # test period already produced.
    audit_rows = conn.execute("SELECT action FROM audit_log ORDER BY id").fetchall()
    assert audit_rows[-1]["action"] == "go_live_cleanup"

    assert settings_repo.get(conn, "next_invoice_no") == "1"
    assert users_repo.list_users(conn) == kept_users_before
    assert tables_repo.list_tables(conn) == kept_tables_before
    assert ps_devices_repo.list_devices(conn) == kept_devices_before
    assert categories_repo.list_categories(conn) == kept_categories_before
    assert products_repo.list_products(conn) == kept_products_before
    assert expense_categories_repo.list_categories(conn) == kept_expense_categories_before
    assert recurring_expenses_repo.list_templates(conn) == kept_recurring_before

    assert result["backup_path"].exists()


def test_cleanup_aborts_on_wrong_pin_and_deletes_nothing(populated):
    conn, owner, tmp_path = populated
    counts_before = {table: _row_count(conn, table) for table in _OPERATIONAL_TABLES}

    with pytest.raises(WrongApprovalPinError):
        go_live_cleanup_service.run_cleanup(
            conn, tmp_path / "test_derby.db", tmp_path / "backups", utc_now(), owner, "0000", "تصفية"
        )

    for table in _OPERATIONAL_TABLES:
        assert _row_count(conn, table) == counts_before[table]
    assert not (tmp_path / "backups").exists() or list((tmp_path / "backups").glob("*.db")) == []


def test_cleanup_aborts_on_wrong_confirmation_word_and_deletes_nothing(populated):
    conn, owner, tmp_path = populated
    counts_before = {table: _row_count(conn, table) for table in _OPERATIONAL_TABLES}

    with pytest.raises(ConfirmationWordMismatchError):
        go_live_cleanup_service.run_cleanup(
            conn, tmp_path / "test_derby.db", tmp_path / "backups", utc_now(), owner, "1111", "حذف الكل"
        )

    for table in _OPERATIONAL_TABLES:
        assert _row_count(conn, table) == counts_before[table]
    assert not (tmp_path / "backups").exists() or list((tmp_path / "backups").glob("*.db")) == []


def test_cleanup_aborts_when_backup_fails_and_deletes_nothing(populated, monkeypatch):
    conn, owner, tmp_path = populated
    counts_before = {table: _row_count(conn, table) for table in _OPERATIONAL_TABLES}

    def _boom(*args, **kwargs):
        raise backup_service.BackupError("فشل محاكى للاختبار")

    monkeypatch.setattr("derby.features.settings.go_live_cleanup_service.backup_service.verified_pre_cleanup_backup", _boom)

    with pytest.raises(backup_service.BackupError):
        go_live_cleanup_service.run_cleanup(
            conn, tmp_path / "test_derby.db", tmp_path / "backups", utc_now(), owner, "1111", "تصفية"
        )

    for table in _OPERATIONAL_TABLES:
        assert _row_count(conn, table) == counts_before[table]
    assert _row_count(conn, "audit_log") > 0  # unchanged: the original rows are still there
