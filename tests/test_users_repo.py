from __future__ import annotations

from derby.core.db import users_repo


def test_unique_pin_rule(db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    assert users_repo.is_pin_in_use(db_conn, "1111") is True
    assert users_repo.is_pin_in_use(db_conn, "2222") is False

    # Excluding the owner's own id lets them "reuse" their own current PIN.
    assert users_repo.is_pin_in_use(db_conn, "1111", exclude_user_id=owner_id) is False


def test_find_active_user_by_pin(db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    users_repo.create_user(db_conn, "Cashier", users_repo.ROLE_CASHIER, "2222")

    found = users_repo.find_active_user_by_pin(db_conn, "1111")
    assert found is not None
    assert found["id"] == owner_id
    assert users_repo.find_active_user_by_pin(db_conn, "9999") is None


def test_inactive_user_not_found_by_pin(db_conn):
    user_id = users_repo.create_user(db_conn, "Cashier", users_repo.ROLE_CASHIER, "3333")
    users_repo.set_active(db_conn, user_id, False)
    assert users_repo.find_active_user_by_pin(db_conn, "3333") is None
    # A deactivated user's PIN is free to reuse.
    assert users_repo.is_pin_in_use(db_conn, "3333") is False


def test_count_active_owners(db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    assert users_repo.count_active_owners(db_conn) == 1
    assert users_repo.count_active_owners(db_conn, exclude_user_id=owner_id) == 0

    users_repo.create_user(db_conn, "Owner 2", users_repo.ROLE_OWNER, "2222")
    assert users_repo.count_active_owners(db_conn) == 2
