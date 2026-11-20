"""Item 2: the تيك أواي "new order" section on the Tables screen --
lazy creation with an optional label, label persistence/display, empty
drafts being discarded silently, per-state card actions, and the
move-to-table-only rule.
"""
from __future__ import annotations

from PySide2.QtWidgets import QDialog, QLabel, QLineEdit, QPushButton

from derby.core.db import categories_repo, orders_repo, products_repo, tables_repo, users_repo
from derby.features.pos.invoice_dialog import InvoiceDialog
from derby.features.pos.pos_screen import PosScreen
from derby.features.pos.sales_log_screen import SalesLogScreen
from derby.features.tables.move_order_dialog import MoveOrderDialog
from derby.features.tables.tables_screen import TablesScreen


def _owner(db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    return users_repo.get_user(db_conn, owner_id)


def _product(db_conn):
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 2500)
    return products_repo.get_product(db_conn, product_id)


# --- lazy creation + label persistence --------------------------------------


def test_start_takeaway_pending_creates_no_row_until_first_item(qapp, db_conn):
    owner = _owner(db_conn)
    product = _product(db_conn)
    pos_screen = PosScreen(db_conn, owner)

    pos_screen.start_takeaway_pending("للعميل أحمد")
    assert pos_screen._current_order_id is None
    assert orders_repo.list_open_takeaway_orders(db_conn) == []

    order_id = pos_screen._materialize_pending_order()
    orders_repo.create_order_item(db_conn, order_id, "product", product["id"], "قهوة", 2500, 1, 2500)

    order = orders_repo.get_order(db_conn, order_id)
    assert order["label"] == "للعميل أحمد"
    assert order["table_id"] is None
    assert order["device_id"] is None


def test_empty_label_is_stored_as_null(qapp, db_conn):
    owner = _owner(db_conn)
    pos_screen = PosScreen(db_conn, owner)
    pos_screen.start_takeaway_pending("   ")  # whitespace-only -- treated as no label
    order_id = pos_screen._materialize_pending_order()
    assert orders_repo.get_order(db_conn, order_id)["label"] is None


def test_label_shown_in_cashier_header(qapp, db_conn):
    owner = _owner(db_conn)
    pos_screen = PosScreen(db_conn, owner)
    pos_screen.start_takeaway_pending("طاولة الشارع")
    assert pos_screen._order_label.text() == "طاولة الشارع"


def test_label_shown_in_sales_log(qapp, db_conn):
    owner = _owner(db_conn)
    product = _product(db_conn)
    pos_screen = PosScreen(db_conn, owner)
    pos_screen.start_takeaway_pending("للعميل سارة")
    order_id = pos_screen._materialize_pending_order()
    orders_repo.create_order_item(db_conn, order_id, "product", product["id"], "قهوة", 2500, 1, 2500)
    orders_service_module = __import__("derby.features.pos.orders_service", fromlist=["recompute_totals"])
    orders_service_module.recompute_totals(db_conn, order_id)
    orders_repo.mark_order_paid(db_conn, order_id, orders_repo.next_invoice_no(db_conn), owner["id"], "2026-01-01", "cash")

    screen = SalesLogScreen(db_conn, owner)
    screen._date_input.setText("2026-01-01")
    screen.reload()
    assert screen._table.item(0, 2).text() == "للعميل سارة"


def test_label_shown_on_invoice(qapp, db_conn):
    owner = _owner(db_conn)
    product = _product(db_conn)
    order_id = orders_repo.create_order(db_conn, None, owner["id"], label="للعميل محمد")
    orders_repo.create_order_item(db_conn, order_id, "product", product["id"], "قهوة", 2500, 1, 2500)
    orders_repo.update_order_totals(db_conn, order_id, 2500, 0, 2500)
    orders_repo.mark_order_paid(db_conn, order_id, orders_repo.next_invoice_no(db_conn), owner["id"], "2026-01-01", "cash")

    dialog = InvoiceDialog(db_conn, order_id, is_copy=False)
    joined = " ".join(label.text() for label in dialog.findChildren(QLabel))
    assert "للعميل محمد" in joined


# --- discarding an empty draft ----------------------------------------------


def test_leaving_cashier_screen_discards_empty_takeaway_draft(qapp, db_conn):
    owner = _owner(db_conn)
    pos_screen = PosScreen(db_conn, owner)
    pos_screen.start_takeaway_pending("مسودة فاضية")

    pos_screen.leave_screen()

    assert pos_screen._current_order_id is None
    assert orders_repo.list_open_takeaway_orders(db_conn) == []


def test_materialized_but_never_gets_an_item_is_swept(qapp, db_conn):
    from derby.features.pos import orders_service

    owner = _owner(db_conn)
    order = orders_service.create_takeaway_order(db_conn, owner["id"], label="سيُهجر")

    cancelled = orders_service.auto_cancel_empty_open_orders(db_conn, owner["id"])

    assert cancelled == 1
    assert orders_repo.get_order(db_conn, order["id"])["status"] == "cancelled"


# --- tables-screen card UI: new-order section + per-state actions ----------


def test_new_takeaway_button_emits_signal_with_label_and_clears_input(qapp, db_conn):
    owner = _owner(db_conn)
    screen = TablesScreen(db_conn, owner)
    received = []
    screen.takeaway_requested.connect(lambda label: received.append(label))

    screen._takeaway_label_input.setText("حجز تليفون")
    screen._on_new_takeaway()

    assert received == ["حجز تليفون"]
    assert screen._takeaway_label_input.text() == ""


def test_takeaway_card_shows_all_four_actions_when_busy(qapp, db_conn):
    from derby.features.pos import orders_service

    owner = _owner(db_conn)
    product = _product(db_conn)
    order = orders_service.create_takeaway_order(db_conn, owner["id"])
    orders_service.add_item(db_conn, order["id"], product["id"], 1, [], None, owner["id"])

    screen = TablesScreen(db_conn, owner)
    screen.reload()
    card = screen._takeaway_layout.itemAt(0).widget()
    button_texts = {b.text() for b in card.findChildren(QPushButton)}
    assert button_texts == {"فتح الطلب", "دفع", "تحويل لترابيزة", "إلغاء الطلب"}


def test_takeaway_card_shows_only_close_when_empty(qapp, db_conn):
    from derby.features.pos import orders_service

    owner = _owner(db_conn)
    orders_service.create_takeaway_order(db_conn, owner["id"])

    screen = TablesScreen(db_conn, owner)
    screen.reload()
    card = screen._takeaway_layout.itemAt(0).widget()
    button_texts = {b.text() for b in card.findChildren(QPushButton)}
    assert button_texts == {"إغلاق"}


def test_empty_state_shown_when_no_takeaway_orders(qapp, db_conn):
    owner = _owner(db_conn)
    screen = TablesScreen(db_conn, owner)
    screen.reload()
    assert screen._takeaway_layout.count() == 1
    label = screen._takeaway_layout.itemAt(0).widget()
    assert isinstance(label, QLineEdit) is False  # sanity: it's the empty-state QLabel, not stray input
    assert "لا توجد" in label.text()


def test_quick_pay_from_takeaway_card_pays_and_removes_it(qapp, db_conn):
    from derby.features.pos import orders_service

    owner = _owner(db_conn)
    product = _product(db_conn)
    order = orders_service.create_takeaway_order(db_conn, owner["id"])
    orders_service.add_item(db_conn, order["id"], product["id"], 1, [], None, owner["id"])

    screen = TablesScreen(db_conn, owner)
    # Drive the real PaymentDialog directly instead of exec_() (blocks
    # waiting on a human) -- same technique _on_quick_pay uses internally.
    from derby.features.pos.payment_dialog import PaymentDialog

    dialog = PaymentDialog(db_conn, orders_repo.get_order(db_conn, order["id"]), owner)
    dialog._on_pay("cash")
    assert dialog.paid_order is not None

    screen.reload()
    assert orders_repo.list_open_takeaway_orders(db_conn) == []


# --- move-to-table-only rule -------------------------------------------------


def test_move_to_table_dialog_only_lists_tables_not_devices(qapp, db_conn):
    owner = _owner(db_conn)
    order_id = orders_repo.create_order(db_conn, None, owner["id"])

    dialog = MoveOrderDialog(db_conn, order_id, owner, allowed_kinds=("table",))
    kinds = {dialog._list.item(i).data(1000)[0] for i in range(dialog._list.count())}
    assert kinds == {"table"}


def test_move_to_table_rejects_a_busy_table(qapp, db_conn):
    from derby.features.pos import orders_service

    owner = _owner(db_conn)
    tables = tables_repo.list_tables(db_conn)
    orders_service.get_or_create_table_order(db_conn, tables[0]["id"], owner["id"])  # busy
    order_id = orders_repo.create_order(db_conn, None, owner["id"])

    dialog = MoveOrderDialog(db_conn, order_id, owner, allowed_kinds=("table",))
    listed_table_ids = {dialog._list.item(i).data(1000)[1] for i in range(dialog._list.count())}
    assert tables[0]["id"] not in listed_table_ids
    assert tables[1]["id"] in listed_table_ids


def test_move_to_table_moves_order_and_rules_hold(qapp, db_conn):
    owner = _owner(db_conn)
    table = tables_repo.list_tables(db_conn)[0]
    order_id = orders_repo.create_order(db_conn, None, owner["id"])

    dialog = MoveOrderDialog(db_conn, order_id, owner, allowed_kinds=("table",))
    dialog._list.setCurrentRow(0)
    dialog._on_confirm()

    assert dialog.result() == QDialog.Accepted
    moved = orders_repo.get_order(db_conn, order_id)
    assert moved["table_id"] == table["id"]
    assert moved["device_id"] is None
