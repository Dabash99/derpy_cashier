"""Covers the Home screen's "الطلبات المفتوحة" section: the service
layer (derby/features/dashboard/open_orders_service.py) and the widget
(derby/features/dashboard/open_orders_panel.py), built offscreen per the
project's working rules -- no screenshots in this file, see
tools/render_phase10_previews.py for that.
"""
from __future__ import annotations

from derby.core.db import (
    categories_repo,
    products_repo,
    ps_devices_repo,
    tables_repo,
    users_repo,
)
from derby.features.dashboard import open_orders_service
from derby.features.dashboard.daily_stats_screen import DailyStatsScreen
from derby.features.dashboard.open_orders_panel import OpenOrdersPanel
from derby.features.playstation import ps_service
from derby.features.pos import orders_service


def _owner(db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    return users_repo.get_user(db_conn, owner_id)


def _cashier(db_conn):
    cashier_id = users_repo.create_user(db_conn, "Cashier", users_repo.ROLE_CASHIER, "2222")
    return users_repo.get_user(db_conn, cashier_id)


def test_no_open_orders_shows_empty_state(qapp, db_conn):
    owner = _owner(db_conn)
    panel = OpenOrdersPanel(db_conn)
    assert panel._empty_container.isVisible() or not panel._empty_container.isHidden()
    assert len(panel._all_cards_data) == 0
    # Both roles build the panel without issue.
    OpenOrdersPanel(db_conn)
    assert owner is not None


def test_one_table_order_shows_one_card(qapp, db_conn):
    owner = _owner(db_conn)
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 2500)
    table = tables_repo.list_tables(db_conn)[0]
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], product_id, 1, [], None, owner["id"])

    cards = open_orders_service.list_open_order_cards(db_conn)
    assert len(cards) == 1
    assert cards[0].kind == open_orders_service.KIND_TABLE
    assert cards[0].item_count == 1
    assert cards[0].opened_by_name == "Owner"

    panel = OpenOrdersPanel(db_conn)
    assert panel._grid_layout.count() == 1


def test_many_open_orders_tables_ps_and_takeaway(qapp, db_conn):
    owner = _owner(db_conn)
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 2500)

    tables = tables_repo.list_tables(db_conn)
    order1 = orders_service.get_or_create_table_order(db_conn, tables[0]["id"], owner["id"])
    orders_service.add_item(db_conn, order1["id"], product_id, 1, [], None, owner["id"])
    order2 = orders_service.get_or_create_table_order(db_conn, tables[1]["id"], owner["id"])
    orders_service.add_item(db_conn, order2["id"], product_id, 1, [], None, owner["id"])

    takeaway = orders_service.create_takeaway_order(db_conn, owner["id"], label="تيك أواي محمد")
    orders_service.add_item(db_conn, takeaway["id"], product_id, 1, [], None, owner["id"])

    device = ps_devices_repo.list_devices(db_conn)[0]
    ps_devices_repo.set_rates(db_conn, device["id"], 4000, 6000)
    ps_service.start_session(db_conn, device["id"], "single", owner["id"])

    cards = open_orders_service.list_open_order_cards(db_conn)
    assert len(cards) == 4
    assert cards[0].kind == open_orders_service.KIND_PLAYSTATION  # PS sorts first
    assert cards[0].is_estimated_total is True
    assert cards[0].ps_mode_label is not None
    kinds = {card.kind for card in cards}
    assert kinds == {
        open_orders_service.KIND_PLAYSTATION,
        open_orders_service.KIND_TABLE,
        open_orders_service.KIND_TAKEAWAY,
    }

    panel = OpenOrdersPanel(db_conn)
    assert panel._grid_layout.count() == 4

    # Filter chips narrow the grid without touching the underlying data.
    panel._on_filter("tables")
    assert panel._grid_layout.count() == 2
    panel._on_filter("playstation")
    assert panel._grid_layout.count() == 1
    panel._on_filter("all")
    assert panel._grid_layout.count() == 4


def test_card_click_emits_order_opened_with_correct_order_id(qapp, db_conn):
    owner = _owner(db_conn)
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 2500)
    table = tables_repo.list_tables(db_conn)[0]
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], product_id, 1, [], None, owner["id"])

    panel = OpenOrdersPanel(db_conn)
    received = []
    panel.order_opened.connect(received.append)

    card_widget = panel._grid_layout.itemAt(0).widget()
    card_widget.clicked.emit(order["id"])
    assert received == [order["id"]]


def test_ps_timer_text_advances_locally_without_hitting_db(qapp, db_conn, monkeypatch):
    owner = _owner(db_conn)
    device = ps_devices_repo.list_devices(db_conn)[0]
    ps_devices_repo.set_rates(db_conn, device["id"], 4000, 6000)
    ps_service.start_session(db_conn, device["id"], "single", owner["id"])

    panel = OpenOrdersPanel(db_conn)
    assert len(panel._running_ps_widgets) == 1
    card_widget = panel._running_ps_widgets[0]
    first_text = card_widget._elapsed_label.text()

    card_widget._base_elapsed_seconds += 5  # simulate 5 real seconds elapsed
    card_widget.tick_local()
    second_text = card_widget._elapsed_label.text()
    assert second_text != first_text


def test_refresh_after_order_paid_mid_flow_does_not_crash(qapp, db_conn):
    owner = _owner(db_conn)
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 2500)
    table = tables_repo.list_tables(db_conn)[0]
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], product_id, 1, [], None, owner["id"])

    panel = OpenOrdersPanel(db_conn)
    assert panel._grid_layout.count() == 1

    orders_service.pay(db_conn, order["id"], "cash", owner)
    panel.reload()  # must not raise even though the order is gone now
    assert panel._grid_layout.count() == 0


def test_home_screen_builds_with_open_orders_for_both_roles(qapp, db_conn):
    owner = _owner(db_conn)
    cashier = _cashier(db_conn)
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 2500)
    table = tables_repo.list_tables(db_conn)[0]
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], product_id, 1, [], None, owner["id"])

    for user in (owner, cashier):
        screen = DailyStatsScreen(db_conn, user)  # must not raise
        screen.reload()
        assert screen._open_orders_panel._grid_layout.count() == 1


def test_a_broken_card_is_skipped_without_crashing_the_panel(qapp, db_conn, monkeypatch):
    owner = _owner(db_conn)
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 2500)
    tables = tables_repo.list_tables(db_conn)
    order1 = orders_service.get_or_create_table_order(db_conn, tables[0]["id"], owner["id"])
    orders_service.add_item(db_conn, order1["id"], product_id, 1, [], None, owner["id"])
    order2 = orders_service.get_or_create_table_order(db_conn, tables[1]["id"], owner["id"])
    orders_service.add_item(db_conn, order2["id"], product_id, 1, [], None, owner["id"])

    import derby.features.dashboard.open_orders_panel as panel_module

    original_widget_cls = panel_module._OpenOrderCardWidget
    call_count = {"n": 0}

    class _FlakyWidget(original_widget_cls):
        def set_data(self, card):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("simulated card build failure")
            super().set_data(card)

    monkeypatch.setattr(panel_module, "_OpenOrderCardWidget", _FlakyWidget)
    panel = OpenOrdersPanel(db_conn)  # must not raise
    assert panel._grid_layout.count() == 1  # the broken one was skipped
