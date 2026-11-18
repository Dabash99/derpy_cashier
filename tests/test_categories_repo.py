from __future__ import annotations

from derby.core.db import categories_repo


def test_create_and_list(db_conn):
    categories_repo.create_category(db_conn, "مشروبات")
    categories_repo.create_category(db_conn, "سناكس")
    names = [c["name"] for c in categories_repo.list_categories(db_conn)]
    assert names == ["مشروبات", "سناكس"]


def test_sort_order_increments(db_conn):
    first_id = categories_repo.create_category(db_conn, "أ")
    second_id = categories_repo.create_category(db_conn, "ب")
    first = categories_repo.get_category(db_conn, first_id)
    second = categories_repo.get_category(db_conn, second_id)
    assert second["sort_order"] > first["sort_order"]


def test_unique_name_detection(db_conn):
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    assert categories_repo.is_name_duplicate(db_conn, "مشروبات") is True
    assert categories_repo.is_name_duplicate(db_conn, "مشروبات", exclude_id=category_id) is False
    assert categories_repo.is_name_duplicate(db_conn, "غير موجود") is False


def test_rename(db_conn):
    category_id = categories_repo.create_category(db_conn, "قديم")
    categories_repo.rename_category(db_conn, category_id, "جديد")
    assert categories_repo.get_category(db_conn, category_id)["name"] == "جديد"


def test_soft_delete_keeps_the_row(db_conn):
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    categories_repo.set_active(db_conn, category_id, False)

    category = categories_repo.get_category(db_conn, category_id)
    assert category is not None
    assert category["is_active"] == 0

    active_only = categories_repo.list_categories(db_conn, active_only=True)
    assert category_id not in [c["id"] for c in active_only]

    all_categories = categories_repo.list_categories(db_conn, active_only=False)
    assert category_id in [c["id"] for c in all_categories]


def test_move_category_swaps_sort_order(db_conn):
    first_id = categories_repo.create_category(db_conn, "أ")
    second_id = categories_repo.create_category(db_conn, "ب")

    categories_repo.move_category(db_conn, second_id, -1)  # move "ب" up

    ordered = categories_repo.list_categories(db_conn)
    assert [c["id"] for c in ordered] == [second_id, first_id]


def test_move_category_at_boundary_is_a_no_op(db_conn):
    first_id = categories_repo.create_category(db_conn, "أ")
    categories_repo.create_category(db_conn, "ب")

    categories_repo.move_category(db_conn, first_id, -1)  # already first

    ordered = categories_repo.list_categories(db_conn)
    assert ordered[0]["id"] == first_id
