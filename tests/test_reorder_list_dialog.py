from __future__ import annotations

from derby.core.db import stock_items_repo
from derby.features.inventory.reorder_list_dialog import ReorderListDialog


def test_dialog_lists_low_stock_items(qapp, db_conn):
    stock_items_repo.create_stock_item(db_conn, "سكر", "kg", min_qty=5)
    dialog = ReorderListDialog(db_conn)
    assert dialog._table.rowCount() == 1
    assert dialog._empty_label.isVisible() is False


def test_dialog_shows_empty_state_when_nothing_is_low(qapp, db_conn):
    dialog = ReorderListDialog(db_conn)
    assert dialog._table.rowCount() == 0
    # isVisible() alone would depend on the (never-shown-in-tests) parent
    # chain too -- isHidden() reflects this widget's own explicit
    # setVisible() call regardless of that, which is what matters here.
    assert dialog._empty_label.isHidden() is False


def test_copy_button_copies_plain_text(qapp, db_conn, monkeypatch):
    from PySide2.QtWidgets import QApplication

    stock_items_repo.create_stock_item(db_conn, "سكر", "kg", min_qty=5)
    dialog = ReorderListDialog(db_conn)

    copied = []
    monkeypatch.setattr(QApplication.clipboard(), "setText", lambda text: copied.append(text))
    dialog._on_copy()
    assert copied and "سكر" in copied[0]
