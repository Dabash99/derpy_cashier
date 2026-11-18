from __future__ import annotations

from derby.core.db import addons_repo, categories_repo, products_repo


def test_create_group_and_addon(db_conn):
    group_id = addons_repo.create_group(db_conn, "الحجم", min_select=1, max_select=1)
    addon_id = addons_repo.create_addon(db_conn, group_id, "كبير", 500)

    group = addons_repo.get_group(db_conn, group_id)
    assert group["name"] == "الحجم"
    assert group["min_select"] == 1
    assert group["max_select"] == 1

    addons = addons_repo.list_addons(db_conn, group_id)
    assert len(addons) == 1
    assert addons[0]["id"] == addon_id
    assert addons[0]["price_delta_piasters"] == 500


def test_max_select_unlimited_is_null(db_conn):
    group_id = addons_repo.create_group(db_conn, "إضافات", min_select=0, max_select=None)
    group = addons_repo.get_group(db_conn, group_id)
    assert group["max_select"] is None


def test_update_group(db_conn):
    group_id = addons_repo.create_group(db_conn, "قديم", min_select=0, max_select=None)
    addons_repo.update_group(db_conn, group_id, "جديد", 1, 2)
    group = addons_repo.get_group(db_conn, group_id)
    assert group["name"] == "جديد"
    assert group["min_select"] == 1
    assert group["max_select"] == 2


def test_soft_delete_group_and_addon(db_conn):
    group_id = addons_repo.create_group(db_conn, "الحجم")
    addon_id = addons_repo.create_addon(db_conn, group_id, "كبير", 500)

    addons_repo.set_group_active(db_conn, group_id, False)
    addons_repo.set_addon_active(db_conn, addon_id, False)

    assert addons_repo.get_group(db_conn, group_id)["is_active"] == 0
    assert group_id not in [g["id"] for g in addons_repo.list_groups(db_conn, active_only=True)]
    assert group_id in [g["id"] for g in addons_repo.list_groups(db_conn)]

    assert addon_id not in [a["id"] for a in addons_repo.list_addons(db_conn, group_id, active_only=True)]
    assert addon_id in [a["id"] for a in addons_repo.list_addons(db_conn, group_id)]


def test_product_addon_group_association(db_conn):
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 100)
    group_a = addons_repo.create_group(db_conn, "الحجم")
    group_b = addons_repo.create_group(db_conn, "الإضافات")

    addons_repo.set_product_addon_groups(db_conn, product_id, [group_a, group_b])
    assert set(addons_repo.get_product_group_ids(db_conn, product_id)) == {group_a, group_b}

    # Replacing the set drops anything not re-sent.
    addons_repo.set_product_addon_groups(db_conn, product_id, [group_a])
    assert addons_repo.get_product_group_ids(db_conn, product_id) == [group_a]

    addons_repo.set_product_addon_groups(db_conn, product_id, [])
    assert addons_repo.get_product_group_ids(db_conn, product_id) == []
