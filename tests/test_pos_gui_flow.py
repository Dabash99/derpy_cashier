"""Drives the real widgets (PosScreen, AddonDialog, PaymentDialog,
InvoiceDialog) end to end: add a product with a required add-on group,
pay with cash, and confirm an invoice can be built. Dialogs are
constructed directly and their handlers called directly instead of
exec_() (which blocks waiting for a human) -- this still exercises the
real production code path, just without the modal event loop.
"""
from __future__ import annotations

from PySide2.QtWidgets import QLabel

from derby.core.db import addons_repo, categories_repo, orders_repo, products_repo, tables_repo, users_repo
from derby.features.pos.addon_dialog import AddonDialog
from derby.features.pos.invoice_dialog import InvoiceDialog
from derby.features.pos.payment_dialog import PaymentDialog
from derby.features.pos.pos_screen import PosScreen


def test_full_flow_table_order_with_addons_pay_cash_invoice(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)

    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "Coffee", 2500)
    group_id = addons_repo.create_group(db_conn, "الحجم", min_select=1, max_select=1)
    addon_id = addons_repo.create_addon(db_conn, group_id, "كبير", 500)
    addons_repo.set_product_addon_groups(db_conn, product_id, [group_id])

    table = tables_repo.list_tables(db_conn)[0]

    # 1) Open the cashier screen and start an order on the first free table.
    pos_screen = PosScreen(db_conn, owner)
    pos_screen._on_start_table(table["id"])
    order = orders_repo.get_open_order_for_table(db_conn, table["id"])
    assert order is not None
    assert pos_screen._current_order_id == order["id"]

    # 2) Drive the real AddonDialog: select the required add-on, confirm.
    addon_dialog = AddonDialog(db_conn, product_id, "قهوة")
    assert len(addon_dialog._checkboxes) == 1
    addon_dialog._checkboxes[0].setChecked(True)
    addon_dialog._on_confirm()
    assert addon_dialog.result() == addon_dialog.Accepted
    assert addon_dialog.selected_addon_ids() == [addon_id]

    # 3) Add the item to the cart the same way pos_screen._on_product_clicked would.
    from derby.features.pos import orders_service

    orders_service.add_item(
        db_conn, order["id"], product_id, 1, addon_dialog.selected_addon_ids(), None, owner["id"]
    )
    pos_screen._cart_panel.reload()
    refreshed_order = orders_repo.get_order(db_conn, order["id"])
    assert refreshed_order["subtotal_piasters"] == 3000  # 2500 base + 500 addon

    # 4) Pay with cash via the real PaymentDialog (without exec_()).
    payment_dialog = PaymentDialog(db_conn, refreshed_order, owner)
    payment_dialog._on_pay("cash")
    assert payment_dialog.paid_order is not None
    assert payment_dialog.paid_order["status"] == "paid"
    assert payment_dialog.paid_order["invoice_no"] == 1

    # 5) The on-screen invoice builds without crashing and shows the line + addon.
    invoice_dialog = InvoiceDialog(db_conn, payment_dialog.paid_order["id"], is_copy=False)
    all_text = " ".join(label.text() for label in invoice_dialog.findChildren(QLabel))
    assert "قهوة" in all_text
    assert "كبير" in all_text


def test_addon_dialog_rejects_incomplete_required_selection(qapp, db_conn):
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 2500)
    group_id = addons_repo.create_group(db_conn, "الحجم", min_select=1, max_select=1)
    addons_repo.create_addon(db_conn, group_id, "كبير", 500)
    addons_repo.set_product_addon_groups(db_conn, product_id, [group_id])

    dialog = AddonDialog(db_conn, product_id, "قهوة")
    dialog._on_confirm()  # nothing checked
    assert dialog.result() != dialog.Accepted
    assert dialog._error_label.text() != ""


def test_pos_screen_cancel_requires_no_approval_when_empty(qapp, db_conn, monkeypatch):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    table = tables_repo.list_tables(db_conn)[0]

    pos_screen = PosScreen(db_conn, owner)
    pos_screen._on_start_table(table["id"])
    order_id = pos_screen._current_order_id

    # Auto-confirm the "are you sure" dialog instead of blocking on it.
    from PySide2.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    pos_screen._on_cancel_requested()

    order = orders_repo.get_order(db_conn, order_id)
    assert order["status"] == "cancelled"
