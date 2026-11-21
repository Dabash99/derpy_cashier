from __future__ import annotations

import pytest

from derby.core.db import drawer_repo, users_repo
from derby.features.inventory import drawer_service
from derby.features.inventory.exceptions import InventoryError, NoteRequiredError, OpeningBalanceRequiredError


@pytest.fixture()
def owner(db_conn):
    user_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    return users_repo.get_user(db_conn, user_id)


def test_expected_cash_is_none_before_any_opening(db_conn):
    assert drawer_service.expected_cash_piasters(db_conn) is None


def test_historical_backfilled_rows_excluded_from_expected_cash(db_conn, owner):
    # Simulate a Phase 9 upgrade's backfill: historical rows exist but no
    # live opening entry has been made yet.
    drawer_repo.create_entry(db_conn, "sale_cash", 100000, is_historical=True, user_id=owner["id"])
    assert drawer_service.expected_cash_piasters(db_conn) is None

    drawer_service.open_drawer(db_conn, 5000, owner["id"])
    # The historical row must still be excluded even once a live opening exists.
    assert drawer_service.expected_cash_piasters(db_conn) == 5000


def test_expected_cash_sums_live_entries_since_last_opening(db_conn, owner):
    drawer_service.open_drawer(db_conn, 10000, owner["id"])
    drawer_repo.create_entry(db_conn, drawer_repo.TYPE_SALE_CASH, 2500, user_id=owner["id"])
    drawer_service.record_withdrawal(db_conn, 1000, "سحب لشراء", owner["id"])
    assert drawer_service.expected_cash_piasters(db_conn) == 10000 + 2500 - 1000


def test_reopening_drawer_resets_the_window(db_conn, owner):
    drawer_service.open_drawer(db_conn, 10000, owner["id"])
    drawer_repo.create_entry(db_conn, drawer_repo.TYPE_SALE_CASH, 5000, user_id=owner["id"])
    drawer_service.open_drawer(db_conn, 3000, owner["id"])  # a fresh day/shift
    assert drawer_service.expected_cash_piasters(db_conn) == 3000


def test_deposit_and_withdrawal_require_a_note(db_conn, owner):
    with pytest.raises(NoteRequiredError):
        drawer_service.record_deposit(db_conn, 1000, "", owner["id"])
    with pytest.raises(NoteRequiredError):
        drawer_service.record_withdrawal(db_conn, 1000, "   ", owner["id"])


def test_deposit_and_withdrawal_amounts_must_be_positive(db_conn, owner):
    with pytest.raises(InventoryError):
        drawer_service.record_deposit(db_conn, 0, "note", owner["id"])
    with pytest.raises(InventoryError):
        drawer_service.record_withdrawal(db_conn, -5, "note", owner["id"])


def test_count_requires_opening_balance_first(db_conn, owner):
    with pytest.raises(OpeningBalanceRequiredError):
        drawer_service.record_count(db_conn, 5000, owner["id"])


def test_count_records_difference_and_adjustment(db_conn, owner):
    drawer_service.open_drawer(db_conn, 10000, owner["id"])
    count = drawer_service.record_count(db_conn, 10500, owner["id"])
    assert count["expected_piasters"] == 10000
    assert count["counted_piasters"] == 10500
    assert count["difference_piasters"] == 500
    # Future expected cash must reflect the adjustment entry.
    assert drawer_service.expected_cash_piasters(db_conn) == 10500


def test_count_with_no_difference_files_no_adjustment(db_conn, owner):
    drawer_service.open_drawer(db_conn, 10000, owner["id"])
    drawer_service.record_count(db_conn, 10000, owner["id"])
    entries = drawer_repo.list_entries(db_conn)
    assert not any(e["entry_type"] == drawer_repo.TYPE_COUNT_ADJUSTMENT for e in entries)


def test_count_history_filterable_by_user(db_conn, owner):
    cashier_id = users_repo.create_user(db_conn, "Cashier", users_repo.ROLE_CASHIER, "2222")
    drawer_service.open_drawer(db_conn, 1000, owner["id"])
    drawer_service.record_count(db_conn, 1000, owner["id"])
    drawer_service.record_count(db_conn, 1200, cashier_id)
    owner_only = drawer_service.count_history(db_conn, user_id=owner["id"])
    assert len(owner_only) == 1
    assert owner_only[0]["user_id"] == owner["id"]


def test_recompute_balance_matches_expected(db_conn, owner):
    drawer_service.open_drawer(db_conn, 10000, owner["id"])
    drawer_repo.create_entry(db_conn, drawer_repo.TYPE_SALE_CASH, 1500, user_id=owner["id"])
    assert drawer_service.recompute_balance_piasters(db_conn) == drawer_service.expected_cash_piasters(db_conn) == 11500
