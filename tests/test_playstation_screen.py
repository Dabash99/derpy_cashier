"""Drives the real PlaystationScreen/_DeviceCard/PsDeviceManagementPanel
widgets -- no screenshots, offscreen Qt only, per the working rules."""
from __future__ import annotations

from datetime import timedelta

from PySide2.QtWidgets import QLabel

from derby.core.db import categories_repo, orders_repo, products_repo, ps_devices_repo, users_repo
from derby.core.utils.money import piasters_to_plain_text
from derby.core.utils.time_utils import utc_now
from derby.features.playstation import ps_service
from derby.features.playstation.playstation_screen import PlaystationScreen
from derby.features.playstation.ps_device_management_panel import PsDeviceManagementPanel
from derby.features.pos.invoice_dialog import InvoiceDialog
from derby.features.pos.payment_dialog import PaymentDialog


def test_two_device_cards_shown(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    screen = PlaystationScreen(db_conn, users_repo.get_user(db_conn, owner_id))
    assert len(screen._cards) == 2


def test_owner_sees_management_tab_cashier_does_not(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    cashier_id = users_repo.create_user(db_conn, "Cashier", users_repo.ROLE_CASHIER, "2222")

    owner_screen = PlaystationScreen(db_conn, users_repo.get_user(db_conn, owner_id))
    assert hasattr(owner_screen, "_management_panel")

    cashier_screen = PlaystationScreen(db_conn, users_repo.get_user(db_conn, cashier_id))
    assert not hasattr(cashier_screen, "_management_panel")


def test_card_start_button_shows_error_when_rate_unset(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    screen = PlaystationScreen(db_conn, users_repo.get_user(db_conn, owner_id))
    device_id = list(screen._cards.keys())[0]
    card = screen._cards[device_id]

    card._on_start("single")
    assert card._error_label.text() != ""
    assert card.has_running_session() is False


def test_card_start_then_stop_updates_state_and_timer(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    device = ps_devices_repo.list_devices(db_conn)[0]
    ps_devices_repo.set_rates(db_conn, device["id"], 4000, 6000)

    screen = PlaystationScreen(db_conn, users_repo.get_user(db_conn, owner_id))
    card = screen._cards[device["id"]]

    card._on_start("single")
    assert card.has_running_session() is True
    assert screen._timer.isActive() is True

    card._on_stop()
    assert card.has_running_session() is False
    assert screen._timer.isActive() is False


def test_device_management_panel_add_rename_rates_disable(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    panel = PsDeviceManagementPanel(db_conn, owner)

    panel._new_name_input.setText("بلاي ستيشن 3")
    panel._on_add()
    assert len(ps_devices_repo.list_devices(db_conn)) == 3

    panel._list.setCurrentRow(2)
    panel._rename_input.setText("جهاز جديد")
    panel._on_rename()
    device = ps_devices_repo.list_devices(db_conn)[2]
    assert device["name"] == "جهاز جديد"

    panel._list.setCurrentRow(2)
    panel._single_rate_input.setText("40")
    panel._multi_rate_input.setText("60")
    panel._on_save_rates()
    device = ps_devices_repo.get_device(db_conn, device["id"])
    assert device["single_rate_piasters_per_hour"] == 4000
    assert device["multi_rate_piasters_per_hour"] == 6000
    assert piasters_to_plain_text(device["single_rate_piasters_per_hour"]) == "40.00"

    panel._list.setCurrentRow(2)
    panel._on_toggle_active()
    device = ps_devices_repo.get_device(db_conn, device["id"])
    assert device["is_active"] == 0


def test_device_management_panel_cannot_disable_busy_device(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    device = ps_devices_repo.list_devices(db_conn)[0]
    ps_devices_repo.set_rates(db_conn, device["id"], 4000, 6000)
    ps_service.start_session(db_conn, device["id"], "single", owner_id)

    panel = PsDeviceManagementPanel(db_conn, owner)
    panel._list.setCurrentRow(0)
    panel._on_toggle_active()

    assert panel._message_label.text() != ""
    assert ps_devices_repo.get_device(db_conn, device["id"])["is_active"] == 1


def test_adjust_start_dialog_owner_direct(qapp, db_conn):
    from derby.core.utils.time_utils import to_cairo
    from derby.features.playstation.ps_adjust_start_dialog import PsAdjustStartDialog

    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    device = ps_devices_repo.list_devices(db_conn)[0]
    ps_devices_repo.set_rates(db_conn, device["id"], 4000, 6000)
    t0 = utc_now() - timedelta(hours=1)  # started an hour ago, so backdating 10 more minutes is safely in range
    ps_service.start_session(db_conn, device["id"], "single", owner_id, now=t0)

    dialog = PsAdjustStartDialog(db_conn, device["id"], owner, parent=None)
    new_cairo = to_cairo(t0 - timedelta(minutes=10))
    dialog._time_input.setText(new_cairo.strftime("%H:%M"))
    dialog._on_save()
    assert dialog.result() == dialog.Accepted


def test_adjust_start_dialog_rejects_a_future_time(qapp, db_conn):
    from derby.core.utils.time_utils import to_cairo
    from derby.features.playstation.ps_adjust_start_dialog import PsAdjustStartDialog

    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    device = ps_devices_repo.list_devices(db_conn)[0]
    ps_devices_repo.set_rates(db_conn, device["id"], 4000, 6000)
    t0 = utc_now()
    ps_service.start_session(db_conn, device["id"], "single", owner_id, now=t0)

    dialog = PsAdjustStartDialog(db_conn, device["id"], owner, parent=None)
    dialog._time_input.setText(to_cairo(t0 + timedelta(minutes=5)).strftime("%H:%M"))
    dialog._on_save()
    assert dialog.result() != dialog.Accepted
    assert dialog._error_label.text() != ""


def test_full_gui_flow_session_plus_drink_then_pay(qapp, db_conn):
    """Start Single -> advance the fake clock 37 min -> stop -> drink added
    -> pay cash -> on-screen invoice shows both the PS line and the drink."""
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    device = ps_devices_repo.list_devices(db_conn)[0]
    ps_devices_repo.set_rates(db_conn, device["id"], 4000, 6000)  # 40 EGP/h single

    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "كوكاكولا", "", 1500)

    t0 = utc_now()
    session = ps_service.start_session(db_conn, device["id"], "single", owner_id, now=t0)
    stopped = ps_service.stop_session(db_conn, device["id"], owner_id, now=t0 + timedelta(minutes=37))
    assert stopped["price_piasters"] == 2500  # 40 EGP/h x 37 min -> 24.67 -> 25 EGP

    order_id = session["order_id"]
    from derby.features.pos import orders_service

    orders_service.add_item(db_conn, order_id, product_id, 1, [], None, owner_id)

    order = orders_repo.get_order(db_conn, order_id)
    assert order["subtotal_piasters"] == 2500 + 1500

    payment_dialog = PaymentDialog(db_conn, order, owner, parent=None)
    payment_dialog._on_pay("cash")
    assert payment_dialog.paid_order is not None
    assert payment_dialog.paid_order["status"] == "paid"

    invoice = InvoiceDialog(db_conn, order_id, is_copy=True, parent=None)
    joined = " ".join(label.text() for label in invoice.findChildren(QLabel))
    assert device["name"] in joined
    assert "كوكاكولا" in joined
