"""Drives the real SuppliesScreen/dialogs -- offscreen Qt only."""
from __future__ import annotations

from PySide2.QtWidgets import QDialog, QPushButton

from derby.core.db import users_repo
from derby.features.supplies import supplies_service
from derby.features.supplies.supplies_screen import SuppliesScreen
from derby.features.supplies.supply_dialogs import ConvertToExpenseDialog, SupplyEditDialog


def test_quick_add_creates_a_needed_item(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    screen = SuppliesScreen(db_conn, owner)

    screen._name_input.setText("سكر")
    screen._quantity_input.setText("كيلو")
    screen._on_add()

    needed = supplies_service.list_for_display(db_conn, status=supplies_service.STATUS_NEEDED)
    assert len(needed) == 1
    assert needed[0]["name"] == "سكر"
    assert screen._name_input.text() == ""  # cleared after a successful add


def test_cashier_cannot_see_convert_button_cashier_can_mark_bought(qapp, db_conn, monkeypatch):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    cashier_id = users_repo.create_user(db_conn, "Cashier", users_repo.ROLE_CASHIER, "2222")
    owner = users_repo.get_user(db_conn, owner_id)
    cashier = users_repo.get_user(db_conn, cashier_id)

    supply = supplies_service.add_supply(db_conn, "سكر", None, supplies_service.PRIORITY_NORMAL, None, owner["id"])
    supplies_service.mark_bought(db_conn, supply["id"], cashier["id"])

    cashier_screen = SuppliesScreen(db_conn, cashier)
    cashier_screen._filter_input.setCurrentIndex(cashier_screen._filter_input.findData("bought"))
    row = cashier_screen._rows_layout.itemAt(0).widget()
    assert not any(b.text() == "تحويل لمصروف" for b in row.findChildren(QPushButton))

    owner_screen = SuppliesScreen(db_conn, owner)
    owner_screen._filter_input.setCurrentIndex(owner_screen._filter_input.findData("bought"))
    row = owner_screen._rows_layout.itemAt(0).widget()
    assert any(b.text() == "تحويل لمصروف" for b in row.findChildren(QPushButton))


def test_edit_dialog_updates_the_supply(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    supply = supplies_service.add_supply(db_conn, "سكر", None, supplies_service.PRIORITY_NORMAL, None, owner["id"])

    dialog = SupplyEditDialog(db_conn, supply, owner)
    dialog._name_input.setText("سكر أبيض")
    dialog._on_save()

    assert dialog.result() == QDialog.Accepted
    from derby.core.db import supplies_repo

    assert supplies_repo.get_supply(db_conn, supply["id"])["name"] == "سكر أبيض"


def test_convert_dialog_creates_expense(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    supply = supplies_service.add_supply(db_conn, "فناجين", None, supplies_service.PRIORITY_NORMAL, None, owner["id"])
    bought = supplies_service.mark_bought(db_conn, supply["id"], owner["id"])

    dialog = ConvertToExpenseDialog(db_conn, bought, owner)
    dialog._cost_input.setText("25")
    dialog._on_convert()

    assert dialog.result() == QDialog.Accepted
    from derby.core.db import supplies_repo

    updated = supplies_repo.get_supply(db_conn, supply["id"])
    assert updated["cost_piasters"] == 2500
    assert updated["expense_id"] is not None
