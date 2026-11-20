from __future__ import annotations

from derby.core.db import tables_repo


def test_seeded_tables_exist(db_conn):
    tables = tables_repo.list_tables(db_conn)
    assert [t["name"] for t in tables] == ["ترابيزة 1", "ترابيزة 2", "ترابيزة 3"]
    assert all(t["is_active"] == 1 for t in tables)


def test_create_table_appends(db_conn):
    new_id = tables_repo.create_table(db_conn, "ترابيزة 4")
    tables = tables_repo.list_tables(db_conn)
    assert tables[-1]["id"] == new_id
    assert tables[-1]["name"] == "ترابيزة 4"


def test_rename_table(db_conn):
    table_id = tables_repo.list_tables(db_conn)[0]["id"]
    tables_repo.rename_table(db_conn, table_id, "VIP")
    assert tables_repo.get_table(db_conn, table_id)["name"] == "VIP"


def test_soft_delete_keeps_row(db_conn):
    table_id = tables_repo.list_tables(db_conn)[0]["id"]
    tables_repo.set_active(db_conn, table_id, False)
    table = tables_repo.get_table(db_conn, table_id)
    assert table is not None
    assert table["is_active"] == 0
    assert table_id not in [t["id"] for t in tables_repo.list_tables(db_conn, active_only=True)]


def test_move_table_swaps_order(db_conn):
    tables = tables_repo.list_tables(db_conn)
    first_id, second_id = tables[0]["id"], tables[1]["id"]
    tables_repo.move_table(db_conn, second_id, -1)
    reordered = tables_repo.list_tables(db_conn)
    assert [t["id"] for t in reordered[:2]] == [second_id, first_id]
