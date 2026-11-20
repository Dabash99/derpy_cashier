from __future__ import annotations

from derby.core.db import categories_repo, products_repo


def _category(db_conn, name="مشروبات"):
    return categories_repo.create_category(db_conn, name)


def test_create_and_get(db_conn):
    category_id = _category(db_conn)
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "Coffee", 2500)
    product = products_repo.get_product(db_conn, product_id)
    assert product["name_ar"] == "قهوة"
    assert product["price_piasters"] == 2500
    assert product["needs_price_review"] == 0
    assert product["is_active"] == 1


def test_sort_order_is_per_category(db_conn):
    category_a = _category(db_conn, "أ")
    category_b = _category(db_conn, "ب")
    first_in_a = products_repo.create_product(db_conn, category_a, "1", "", 100)
    first_in_b = products_repo.create_product(db_conn, category_b, "1", "", 100)
    assert products_repo.get_product(db_conn, first_in_a)["sort_order"] == 1
    assert products_repo.get_product(db_conn, first_in_b)["sort_order"] == 1


def test_unique_name_within_category(db_conn):
    category_id = _category(db_conn)
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 100)
    assert products_repo.is_name_duplicate(db_conn, category_id, "قهوة") is True
    assert products_repo.is_name_duplicate(db_conn, category_id, "قهوة", exclude_id=product_id) is False

    other_category = _category(db_conn, "آخر")
    assert products_repo.is_name_duplicate(db_conn, other_category, "قهوة") is False


def test_soft_delete_keeps_the_row(db_conn):
    category_id = _category(db_conn)
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 100)
    products_repo.set_active(db_conn, product_id, False)

    product = products_repo.get_product(db_conn, product_id)
    assert product is not None
    assert product["is_active"] == 0
    assert product_id not in [p["id"] for p in products_repo.list_products(db_conn, active_only=True)]
    assert product_id in [p["id"] for p in products_repo.list_products(db_conn)]


def test_update_product_clears_needs_review(db_conn):
    category_id = _category(db_conn)
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 100, needs_price_review=True)
    assert products_repo.get_product(db_conn, product_id)["needs_price_review"] == 1

    products_repo.update_product(db_conn, product_id, category_id, "قهوة", "Coffee", 150, None, True)
    product = products_repo.get_product(db_conn, product_id)
    assert product["needs_price_review"] == 0
    assert product["price_piasters"] == 150


def test_confirm_price_clears_review_without_changing_price(db_conn):
    category_id = _category(db_conn)
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 100, needs_price_review=True)

    products_repo.confirm_price(db_conn, product_id)

    product = products_repo.get_product(db_conn, product_id)
    assert product["needs_price_review"] == 0
    assert product["price_piasters"] == 100


def test_set_price_from_import_keeps_needs_review(db_conn):
    category_id = _category(db_conn)
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 100)

    products_repo.set_price_from_import(db_conn, product_id, 200, "new_image.jpg")

    product = products_repo.get_product(db_conn, product_id)
    assert product["price_piasters"] == 200
    assert product["image_file"] == "new_image.jpg"
    assert product["needs_price_review"] == 1


def test_find_product_by_name(db_conn):
    category_id = _category(db_conn)
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 100)
    found = products_repo.find_product_by_name(db_conn, category_id, "قهوة")
    assert found["id"] == product_id
    assert products_repo.find_product_by_name(db_conn, category_id, "غير موجود") is None


def test_list_products_filters_by_category(db_conn):
    category_a = _category(db_conn, "أ")
    category_b = _category(db_conn, "ب")
    products_repo.create_product(db_conn, category_a, "1", "", 100)
    products_repo.create_product(db_conn, category_b, "2", "", 100)

    assert len(products_repo.list_products(db_conn, category_id=category_a)) == 1
    assert len(products_repo.list_products(db_conn)) == 2
