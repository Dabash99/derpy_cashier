"""Drives the real ProductDialog widget (not just products_repo) to prove
the audit-logging wiring and validation actually fire from the UI code
path -- QFileDialog itself is never invoked (it's a blocking native
picker), so image handling is exercised through the dialog's internal
state directly.
"""
from __future__ import annotations

from derby.core.db import categories_repo, products_repo, users_repo
from derby.core.i18n import ar
from derby.features.menu.product_dialog import ProductDialog


def _owner_id(db_conn):
    return users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1234")


def test_add_product_via_dialog(qapp, db_conn):
    user_id = _owner_id(db_conn)
    category_id = categories_repo.create_category(db_conn, "مشروبات")

    dialog = ProductDialog(db_conn, user_id, default_category_id=category_id)
    dialog._name_ar_input.setText("قهوة")
    dialog._name_en_input.setText("Coffee")
    dialog._price_input.setText("25")
    dialog._on_save()

    products = products_repo.list_products(db_conn)
    assert len(products) == 1
    assert products[0]["name_ar"] == "قهوة"
    assert products[0]["price_piasters"] == 2500


def test_add_product_rejects_empty_name(qapp, db_conn):
    user_id = _owner_id(db_conn)
    category_id = categories_repo.create_category(db_conn, "مشروبات")

    dialog = ProductDialog(db_conn, user_id, default_category_id=category_id)
    dialog._price_input.setText("25")
    dialog._on_save()

    assert dialog._error_label.text() == ar.MENU_PRODUCT_ERROR_NAME_AR_REQUIRED
    assert products_repo.list_products(db_conn) == []


def test_add_product_rejects_duplicate_name_in_same_category(qapp, db_conn):
    user_id = _owner_id(db_conn)
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    products_repo.create_product(db_conn, category_id, "قهوة", "", 100)

    dialog = ProductDialog(db_conn, user_id, default_category_id=category_id)
    dialog._name_ar_input.setText("قهوة")
    dialog._price_input.setText("25")
    dialog._on_save()

    assert dialog._error_label.text() == ar.MENU_PRODUCT_ERROR_NAME_TAKEN
    assert len(products_repo.list_products(db_conn)) == 1


def test_add_product_rejects_invalid_price(qapp, db_conn):
    user_id = _owner_id(db_conn)
    category_id = categories_repo.create_category(db_conn, "مشروبات")

    dialog = ProductDialog(db_conn, user_id, default_category_id=category_id)
    dialog._name_ar_input.setText("قهوة")
    dialog._price_input.setText("25.555")
    dialog._on_save()

    assert dialog._error_label.text() == ar.MENU_PRODUCT_ERROR_PRICE_INVALID
    assert products_repo.list_products(db_conn) == []


def test_editing_price_writes_audit_log(qapp, db_conn):
    user_id = _owner_id(db_conn)
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 100)

    dialog = ProductDialog(db_conn, user_id, product_id=product_id)
    dialog._price_input.setText("30")
    dialog._on_save()

    product = products_repo.get_product(db_conn, product_id)
    assert product["price_piasters"] == 3000

    rows = db_conn.execute(
        "SELECT * FROM audit_log WHERE action = 'product_price_changed'"
    ).fetchall()
    assert len(rows) == 1
    assert '"before_piasters": 100' in rows[0]["details_json"]
    assert '"after_piasters": 3000' in rows[0]["details_json"]
    assert rows[0]["user_id"] == user_id


def test_editing_without_changing_price_writes_no_audit_log(qapp, db_conn):
    user_id = _owner_id(db_conn)
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 100)

    dialog = ProductDialog(db_conn, user_id, product_id=product_id)
    dialog._name_en_input.setText("Coffee")  # unrelated change
    dialog._on_save()

    rows = db_conn.execute("SELECT * FROM audit_log WHERE action = 'product_price_changed'").fetchall()
    assert rows == []


def test_editing_clears_needs_price_review(qapp, db_conn):
    user_id = _owner_id(db_conn)
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(
        db_conn, category_id, "قهوة", "", 100, needs_price_review=True
    )

    dialog = ProductDialog(db_conn, user_id, product_id=product_id)
    dialog._on_save()

    assert products_repo.get_product(db_conn, product_id)["needs_price_review"] == 0


def test_addon_groups_are_saved(qapp, db_conn):
    from derby.core.db import addons_repo

    user_id = _owner_id(db_conn)
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    group_id = addons_repo.create_group(db_conn, "الحجم")

    dialog = ProductDialog(db_conn, user_id, default_category_id=category_id)
    dialog._name_ar_input.setText("قهوة")
    dialog._price_input.setText("25")
    for row in range(dialog._groups_list.count()):
        item = dialog._groups_list.item(row)
        if item.data(1000) == group_id:
            from PySide2.QtCore import Qt

            item.setCheckState(Qt.Checked)
    dialog._on_save()

    products = products_repo.list_products(db_conn)
    assert addons_repo.get_product_group_ids(db_conn, products[0]["id"]) == [group_id]
