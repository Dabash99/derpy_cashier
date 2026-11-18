from __future__ import annotations

from derby.core.db import expense_categories_repo


def test_create_rename_and_list(db_conn):
    category_id = expense_categories_repo.create_category(db_conn, "صيانة أجهزة")
    expense_categories_repo.rename_category(db_conn, category_id, "صيانة معدات")
    category = expense_categories_repo.get_category(db_conn, category_id)
    assert category["name"] == "صيانة معدات"


def test_set_active_and_list_active_only(db_conn):
    categories = expense_categories_repo.list_categories(db_conn)
    expense_categories_repo.set_active(db_conn, categories[0]["id"], False)
    active = expense_categories_repo.list_categories(db_conn, active_only=True)
    assert categories[0]["id"] not in [c["id"] for c in active]


def test_move_category_swaps_sort_order(db_conn):
    categories = expense_categories_repo.list_categories(db_conn)
    first_id, second_id = categories[0]["id"], categories[1]["id"]
    expense_categories_repo.move_category(db_conn, first_id, 1)
    reordered = expense_categories_repo.list_categories(db_conn)
    assert reordered[0]["id"] == second_id
    assert reordered[1]["id"] == first_id
