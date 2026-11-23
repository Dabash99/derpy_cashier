from __future__ import annotations

from derby.core.db.users_repo import ROLE_CASHIER, ROLE_OWNER
from derby.features.auth import permissions
from derby.features.shell.sidebar import SECTIONS


def test_only_owner_views_audit_log():
    assert permissions.view_audit_log(ROLE_OWNER) is True
    assert permissions.view_audit_log(ROLE_CASHIER) is False


def test_audit_log_section_hidden_from_cashier_sidebar():
    section = next(s for s in SECTIONS if s[0] == "audit_log")
    allowed = section[4]
    assert allowed(ROLE_OWNER) is True
    assert allowed(ROLE_CASHIER) is False


def test_cashier_cannot_void_order_and_attempt_is_audited(db_conn):
    from derby.core.db import categories_repo, products_repo, tables_repo, users_repo
    from derby.features.pos import orders_service
    from derby.features.pos.exceptions import PermissionDeniedError

    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    cashier_id = users_repo.create_user(db_conn, "Cashier", users_repo.ROLE_CASHIER, "2222")
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 2500)
    table = tables_repo.list_tables(db_conn)[0]
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner_id)
    orders_service.add_item(db_conn, order["id"], product_id, 1, [], None, owner_id)
    paid = orders_service.pay(db_conn, order["id"], "cash", users_repo.get_user(db_conn, owner_id))

    cashier = users_repo.get_user(db_conn, cashier_id)
    try:
        orders_service.void(db_conn, paid["id"], "test", cashier)
        assert False, "expected PermissionDeniedError"
    except PermissionDeniedError:
        pass

    row = db_conn.execute("SELECT * FROM audit_log WHERE action = 'permission_denied'").fetchone()
    assert row is not None
    assert row["severity"] == "warning"
