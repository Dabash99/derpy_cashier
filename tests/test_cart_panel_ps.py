"""Drives the real CartPanel for a device order: the provisional running
line, the disabled pay button, and owner-approved ps_time line removal."""
from __future__ import annotations

from datetime import timedelta

from PySide2.QtWidgets import QMessageBox

from derby.core.db import orders_repo, ps_devices_repo, users_repo
from derby.core.utils.time_utils import utc_now
from derby.features.playstation import ps_service
from derby.features.pos.cart_panel import CartPanel


def test_pay_button_disabled_and_provisional_line_shown_while_running(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    device = ps_devices_repo.list_devices(db_conn)[0]
    ps_devices_repo.set_rates(db_conn, device["id"], 4000, 6000)

    session = ps_service.start_session(db_conn, device["id"], "single", owner_id)
    panel = CartPanel(db_conn, session["order_id"], owner)

    assert panel.pay_allowed() is False
    assert panel._pay_hint_label.isHidden() is False
    assert panel._provisional_label.isHidden() is False


def test_pay_button_enabled_again_after_stop(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    device = ps_devices_repo.list_devices(db_conn)[0]
    ps_devices_repo.set_rates(db_conn, device["id"], 4000, 6000)

    t0 = utc_now()
    session = ps_service.start_session(db_conn, device["id"], "single", owner_id, now=t0)
    ps_service.stop_session(db_conn, device["id"], owner_id, now=t0 + timedelta(minutes=35))

    panel = CartPanel(db_conn, session["order_id"], owner)
    assert panel.pay_allowed() is True
    assert panel._provisional_label.isHidden() is True


def test_remove_ps_line_as_owner_via_cart_panel(qapp, db_conn, monkeypatch):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    device = ps_devices_repo.list_devices(db_conn)[0]
    ps_devices_repo.set_rates(db_conn, device["id"], 4000, 6000)

    t0 = utc_now()
    session = ps_service.start_session(db_conn, device["id"], "single", owner_id, now=t0)
    ps_service.stop_session(db_conn, device["id"], owner_id, now=t0 + timedelta(minutes=35))

    panel = CartPanel(db_conn, session["order_id"], owner)
    item = orders_repo.list_order_items(db_conn, session["order_id"])[0]

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    panel._on_remove_ps_item(item["id"])

    assert orders_repo.list_order_items(db_conn, session["order_id"]) == []


def test_remove_ps_line_as_cashier_needs_owner_pin(qapp, db_conn, monkeypatch):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    cashier_id = users_repo.create_user(db_conn, "Cashier", users_repo.ROLE_CASHIER, "2222")
    cashier = users_repo.get_user(db_conn, cashier_id)
    device = ps_devices_repo.list_devices(db_conn)[0]
    ps_devices_repo.set_rates(db_conn, device["id"], 4000, 6000)

    t0 = utc_now()
    session = ps_service.start_session(db_conn, device["id"], "single", owner_id, now=t0)
    ps_service.stop_session(db_conn, device["id"], owner_id, now=t0 + timedelta(minutes=35))

    panel = CartPanel(db_conn, session["order_id"], cashier)
    item = orders_repo.list_order_items(db_conn, session["order_id"])[0]

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr("derby.features.pos.cart_panel.ask_for_owner_pin", lambda parent=None: "1111")
    panel._on_remove_ps_item(item["id"])

    assert orders_repo.list_order_items(db_conn, session["order_id"]) == []
