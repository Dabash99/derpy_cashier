from __future__ import annotations

from derby.core.db import categories_repo, products_repo, recipes_repo, stock_items_repo, users_repo
from derby.features.inventory.recipe_editor_dialog import RecipeEditorDialog


def _owner_id(db_conn):
    return users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1234")


def _waffle(db_conn):
    category_id = categories_repo.create_category(db_conn, "وافل")
    return products_repo.create_product(db_conn, category_id, "وافل", "Waffle", 5000)


def test_recipe_editor_saves_new_recipe(qapp, db_conn):
    _owner_id(db_conn)
    flour_id = stock_items_repo.create_stock_item(db_conn, "دقيق", "g")
    stock_items_repo.set_qty_and_cost(db_conn, flour_id, 1000, 10)
    waffle_id = _waffle(db_conn)

    dialog = RecipeEditorDialog(db_conn, recipes_repo.OWNER_PRODUCT, waffle_id, "وافل", 5000)
    dialog._rows[0]._qty_input.setText("100")
    dialog._on_save()

    lines = recipes_repo.list_recipe_lines(db_conn, recipes_repo.OWNER_PRODUCT, waffle_id)
    assert len(lines) == 1
    assert lines[0]["stock_item_id"] == flour_id
    assert lines[0]["qty_per_unit"] == 100.0


def test_recipe_editor_loads_existing_recipe(qapp, db_conn):
    _owner_id(db_conn)
    flour_id = stock_items_repo.create_stock_item(db_conn, "دقيق", "g")
    stock_items_repo.set_qty_and_cost(db_conn, flour_id, 1000, 10)
    waffle_id = _waffle(db_conn)
    recipes_repo.set_recipe(db_conn, recipes_repo.OWNER_PRODUCT, waffle_id, [{"stock_item_id": flour_id, "qty_per_unit": 150}])

    dialog = RecipeEditorDialog(db_conn, recipes_repo.OWNER_PRODUCT, waffle_id, "وافل", 5000)
    assert len(dialog._rows) == 1
    assert dialog._rows[0].qty_per_unit() == 150.0
    assert "1500" in dialog._cost_label.text() or "15.00" in dialog._cost_label.text()


def test_recipe_editor_removing_all_lines_clears_recipe(qapp, db_conn):
    _owner_id(db_conn)
    flour_id = stock_items_repo.create_stock_item(db_conn, "دقيق", "g")
    stock_items_repo.set_qty_and_cost(db_conn, flour_id, 1000, 10)
    waffle_id = _waffle(db_conn)
    recipes_repo.set_recipe(db_conn, recipes_repo.OWNER_PRODUCT, waffle_id, [{"stock_item_id": flour_id, "qty_per_unit": 150}])

    dialog = RecipeEditorDialog(db_conn, recipes_repo.OWNER_PRODUCT, waffle_id, "وافل", 5000)
    dialog._remove_row(dialog._rows[0])
    dialog._on_save()

    assert recipes_repo.list_recipe_lines(db_conn, recipes_repo.OWNER_PRODUCT, waffle_id) == []
