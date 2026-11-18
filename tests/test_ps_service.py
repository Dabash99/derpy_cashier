from __future__ import annotations

from datetime import timedelta

import pytest

from derby.core.db import (
    categories_repo,
    orders_repo,
    products_repo,
    ps_devices_repo,
    ps_sessions_repo,
    tables_repo,
    users_repo,
)
from derby.core.utils.time_utils import utc_now
from derby.features.playstation import ps_service
from derby.features.pos import orders_service
from derby.features.pos.exceptions import (
    ApprovalLockedOutError,
    DeviceBusyError,
    DeviceRateNotSetError,
    InvalidTransitionError,
    SessionRunningError,
    WrongApprovalPinError,
)


@pytest.fixture()
def owner(db_conn):
    user_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    return users_repo.get_user(db_conn, user_id)


@pytest.fixture()
def cashier(db_conn):
    user_id = users_repo.create_user(db_conn, "Cashier", users_repo.ROLE_CASHIER, "2222")
    return users_repo.get_user(db_conn, user_id)


@pytest.fixture()
def device(db_conn):
    return ps_devices_repo.list_devices(db_conn)[0]


def _set_rates(db_conn, device_id, single_egp, multi_egp):
    ps_devices_repo.set_rates(db_conn, device_id, single_egp * 100, multi_egp * 100)


# --- starting -----------------------------------------------------------


def test_start_blocked_when_rate_is_zero(db_conn, device, owner):
    with pytest.raises(DeviceRateNotSetError):
        ps_service.start_session(db_conn, device["id"], "single", owner["id"])


def test_start_creates_device_order_and_running_session(db_conn, device, owner):
    _set_rates(db_conn, device["id"], 40, 60)
    session = ps_service.start_session(db_conn, device["id"], "single", owner["id"])
    assert session["stopped_at_utc"] is None
    order = orders_repo.get_open_order_for_device(db_conn, device["id"])
    assert order is not None
    assert order["table_id"] is None
    assert order["id"] == session["order_id"]


def test_only_one_running_session_per_device(db_conn, device, owner):
    _set_rates(db_conn, device["id"], 40, 60)
    ps_service.start_session(db_conn, device["id"], "single", owner["id"])
    with pytest.raises(SessionRunningError):
        ps_service.start_session(db_conn, device["id"], "multi", owner["id"])


def test_table_and_device_order_are_exclusive_at_db_level(db_conn, device, owner):
    _set_rates(db_conn, device["id"], 40, 60)
    session = ps_service.start_session(db_conn, device["id"], "single", owner["id"])
    order_id = session["order_id"]
    table = tables_repo.list_tables(db_conn)[0]
    with pytest.raises(Exception):
        db_conn.execute("UPDATE orders SET table_id = ? WHERE id = ?", (table["id"], order_id))


# --- switching mode / stopping -------------------------------------------


def test_switch_mode_bills_actual_minutes_only_no_minimum(db_conn, device, owner):
    _set_rates(db_conn, device["id"], 40, 60)
    t0 = utc_now()
    ps_service.start_session(db_conn, device["id"], "single", owner["id"], now=t0)
    new_session = ps_service.switch_mode(db_conn, device["id"], "multi", owner["id"], now=t0 + timedelta(minutes=10))

    order_id = new_session["order_id"]
    items = orders_repo.list_order_items(db_conn, order_id)
    assert len(items) == 1
    assert items[0]["qty"] == 1
    # 40 EGP/h x 10 actual minutes (no minimum on a switch) -> 6.67 EGP -> rounds to 5 EGP.
    assert items[0]["line_total_piasters"] == 500
    assert new_session["mode"] == "multi"
    assert new_session["id"] != new_session["order_id"]  # sanity: different rows


def test_final_stop_applies_the_visit_minimum(db_conn, device, owner):
    _set_rates(db_conn, device["id"], 40, 60)
    t0 = utc_now()
    ps_service.start_session(db_conn, device["id"], "single", owner["id"], now=t0)
    stopped = ps_service.stop_session(db_conn, device["id"], owner["id"], now=t0 + timedelta(minutes=10))
    assert stopped["billed_minutes"] == 30  # topped up to ps_min_minutes default (30)
    # 40 EGP/h x 30 min = 20 EGP exactly.
    assert stopped["price_piasters"] == 2000


def test_visit_crossing_minimum_via_switch_then_final_bills_actual_only(db_conn, device, owner):
    _set_rates(db_conn, device["id"], 40, 60)
    t0 = utc_now()
    ps_service.start_session(db_conn, device["id"], "single", owner["id"], now=t0)
    ps_service.switch_mode(db_conn, device["id"], "multi", owner["id"], now=t0 + timedelta(minutes=10))
    stopped = ps_service.stop_session(db_conn, device["id"], owner["id"], now=t0 + timedelta(minutes=60))
    assert stopped["billed_minutes"] == 50  # 10 (switch) + 50 actual = 60 >= 30, no top-up on the final one


def test_restart_after_final_stop_does_not_reapply_minimum(db_conn, device, owner):
    _set_rates(db_conn, device["id"], 40, 60)
    t0 = utc_now()
    ps_service.start_session(db_conn, device["id"], "single", owner["id"], now=t0)
    first_stop = ps_service.stop_session(db_conn, device["id"], owner["id"], now=t0 + timedelta(minutes=10))
    assert first_stop["billed_minutes"] == 30

    ps_service.start_session(db_conn, device["id"], "single", owner["id"], now=t0 + timedelta(minutes=40))
    second_stop = ps_service.stop_session(db_conn, device["id"], owner["id"], now=t0 + timedelta(minutes=45))
    assert second_stop["billed_minutes"] == 5  # actual only, minimum already satisfied this visit


def test_timers_survive_reopening_the_db_fake_clock(db_conn, device, owner):
    _set_rates(db_conn, device["id"], 40, 60)
    t0 = utc_now()
    ps_service.start_session(db_conn, device["id"], "single", owner["id"], now=t0)

    later = t0 + timedelta(minutes=37)
    state = ps_service.current_state(db_conn, device["id"], now=later)
    assert state["elapsed_seconds"] == 37 * 60
    assert state["provisional_price_piasters"] == 2500  # 40 EGP/h x 37 min -> 25 EGP


def test_clock_moved_backwards_is_clamped_to_zero(db_conn, device, owner):
    _set_rates(db_conn, device["id"], 40, 60)
    t0 = utc_now()
    ps_service.start_session(db_conn, device["id"], "single", owner["id"], now=t0)
    stopped = ps_service.stop_session(db_conn, device["id"], owner["id"], now=t0 - timedelta(minutes=5))
    assert stopped["actual_minutes"] == 1  # never negative, floored at 1


def test_rate_snapshot_unaffected_by_later_rate_edits(db_conn, device, owner):
    _set_rates(db_conn, device["id"], 40, 60)
    t0 = utc_now()
    session = ps_service.start_session(db_conn, device["id"], "single", owner["id"], now=t0)
    assert session["rate_snapshot_piasters_per_hour"] == 4000

    ps_devices_repo.set_rates(db_conn, device["id"], 9999, 9999)  # rate changed mid-session
    stopped = ps_service.stop_session(db_conn, device["id"], owner["id"], now=t0 + timedelta(minutes=40))
    assert stopped["rate_snapshot_piasters_per_hour"] == 4000  # unchanged
    assert stopped["price_piasters"] == 2500  # 40 EGP/h x 40 min -> 26.67 EGP -> rounds to 25 EGP


# --- pay guard -------------------------------------------------------------


def test_pay_blocked_while_a_session_is_running(db_conn, device, owner):
    _set_rates(db_conn, device["id"], 40, 60)
    session = ps_service.start_session(db_conn, device["id"], "single", owner["id"])
    with pytest.raises(SessionRunningError):
        orders_service.pay(db_conn, session["order_id"], "cash", owner)


def test_pay_succeeds_after_stopping(db_conn, device, owner):
    _set_rates(db_conn, device["id"], 40, 60)
    t0 = utc_now()
    session = ps_service.start_session(db_conn, device["id"], "single", owner["id"], now=t0)
    ps_service.stop_session(db_conn, device["id"], owner["id"], now=t0 + timedelta(minutes=35))
    paid = orders_service.pay(db_conn, session["order_id"], "cash", owner)
    assert paid["status"] == "paid"
    assert paid["invoice_no"] == 1


# --- move_order: table <-> device -------------------------------------------


def test_move_table_order_to_free_device(db_conn, owner):
    device_a, device_b = ps_devices_repo.list_devices(db_conn)[:2]
    table = tables_repo.list_tables(db_conn)[0]
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])

    moved = orders_service.move_order(db_conn, order["id"], None, owner, target_device_id=device_a["id"])
    assert moved["table_id"] is None
    assert moved["device_id"] == device_a["id"]


def test_move_to_busy_device_is_rejected(db_conn, owner):
    device_a, device_b = ps_devices_repo.list_devices(db_conn)[:2]
    _set_rates(db_conn, device_a["id"], 40, 60)
    ps_service.start_session(db_conn, device_a["id"], "single", owner["id"])  # device_a now busy

    table = tables_repo.list_tables(db_conn)[0]
    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    with pytest.raises(DeviceBusyError):
        orders_service.move_order(db_conn, order["id"], None, owner, target_device_id=device_a["id"])


def test_move_device_order_to_table_rejected_while_session_running(db_conn, owner):
    device_a = ps_devices_repo.list_devices(db_conn)[0]
    _set_rates(db_conn, device_a["id"], 40, 60)
    session = ps_service.start_session(db_conn, device_a["id"], "single", owner["id"])
    table = tables_repo.list_tables(db_conn)[0]

    with pytest.raises(SessionRunningError):
        orders_service.move_order(db_conn, session["order_id"], table["id"], owner)


def test_move_device_order_to_table_allowed_after_stop(db_conn, owner):
    device_a = ps_devices_repo.list_devices(db_conn)[0]
    _set_rates(db_conn, device_a["id"], 40, 60)
    t0 = utc_now()
    session = ps_service.start_session(db_conn, device_a["id"], "single", owner["id"], now=t0)
    ps_service.stop_session(db_conn, device_a["id"], owner["id"], now=t0 + timedelta(minutes=35))
    table = tables_repo.list_tables(db_conn)[0]

    moved = orders_service.move_order(db_conn, session["order_id"], table["id"], owner)
    assert moved["device_id"] is None
    assert moved["table_id"] == table["id"]


# --- removing a ps_time line (owner approval) -------------------------------


def test_remove_ps_line_requires_owner_approval_cashier_pin_rejected(db_conn, device, owner, cashier):
    _set_rates(db_conn, device["id"], 40, 60)
    t0 = utc_now()
    session = ps_service.start_session(db_conn, device["id"], "single", owner["id"], now=t0)
    ps_service.stop_session(db_conn, device["id"], owner["id"], now=t0 + timedelta(minutes=35))
    order_id = session["order_id"]
    item = orders_repo.list_order_items(db_conn, order_id)[0]

    with pytest.raises(WrongApprovalPinError):
        orders_service.remove_ps_item(db_conn, order_id, item["id"], cashier, approving_pin="2222")


def test_remove_ps_line_as_owner_keeps_session_marked_voided(db_conn, device, owner):
    _set_rates(db_conn, device["id"], 40, 60)
    t0 = utc_now()
    session = ps_service.start_session(db_conn, device["id"], "single", owner["id"], now=t0)
    ps_service.stop_session(db_conn, device["id"], owner["id"], now=t0 + timedelta(minutes=35))
    order_id = session["order_id"]
    item = orders_repo.list_order_items(db_conn, order_id)[0]

    orders_service.remove_ps_item(db_conn, order_id, item["id"], owner)

    assert orders_repo.list_order_items(db_conn, order_id) == []
    voided_session = ps_sessions_repo.get_session(db_conn, session["id"])
    assert voided_session is not None  # kept, never deleted
    assert voided_session["voided_at_utc"] is not None
    order = orders_repo.get_order(db_conn, order_id)
    assert order["subtotal_piasters"] == 0


def test_voided_session_excluded_from_visit_minimum_sum(db_conn, device, owner):
    _set_rates(db_conn, device["id"], 40, 60)
    t0 = utc_now()
    ps_service.start_session(db_conn, device["id"], "single", owner["id"], now=t0)
    stopped = ps_service.stop_session(db_conn, device["id"], owner["id"], now=t0 + timedelta(minutes=10))
    assert stopped["billed_minutes"] == 30
    item = orders_repo.list_order_items(db_conn, stopped["order_id"])[0]
    orders_service.remove_ps_item(db_conn, stopped["order_id"], item["id"], owner)

    assert ps_sessions_repo.sum_billed_minutes_for_order(db_conn, stopped["order_id"]) == 0


# --- backdating the start time ----------------------------------------------


def test_adjust_start_rejects_future_time(db_conn, device, owner):
    _set_rates(db_conn, device["id"], 40, 60)
    t0 = utc_now()
    ps_service.start_session(db_conn, device["id"], "single", owner["id"], now=t0)
    with pytest.raises(InvalidTransitionError):
        ps_service.adjust_session_start(db_conn, device["id"], t0 + timedelta(minutes=5), owner, now=t0)


def test_adjust_start_rejects_more_than_12_hours_back(db_conn, device, owner):
    _set_rates(db_conn, device["id"], 40, 60)
    t0 = utc_now()
    ps_service.start_session(db_conn, device["id"], "single", owner["id"], now=t0)
    with pytest.raises(InvalidTransitionError):
        ps_service.adjust_session_start(db_conn, device["id"], t0 - timedelta(hours=13), owner, now=t0)


def test_adjust_start_requires_owner_approval_and_audit_logs(db_conn, device, owner, cashier):
    _set_rates(db_conn, device["id"], 40, 60)
    t0 = utc_now()
    session = ps_service.start_session(db_conn, device["id"], "single", owner["id"], now=t0)

    new_start = t0 - timedelta(hours=1)
    with pytest.raises(WrongApprovalPinError):
        ps_service.adjust_session_start(db_conn, device["id"], new_start, cashier, approving_pin="0000", now=t0)

    adjusted = ps_service.adjust_session_start(db_conn, device["id"], new_start, cashier, approving_pin="1111", now=t0)
    assert adjusted["id"] == session["id"]

    row = db_conn.execute(
        "SELECT * FROM audit_log WHERE action = 'ps_session_start_adjusted' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    assert "approved_by={0}".format(owner["id"]) in row["details"]


def test_adjust_start_wrong_pin_counts_toward_global_lockout(db_conn, device, owner, cashier):
    _set_rates(db_conn, device["id"], 40, 60)
    t0 = utc_now()
    ps_service.start_session(db_conn, device["id"], "single", owner["id"], now=t0)
    for _ in range(5):
        with pytest.raises(WrongApprovalPinError):
            ps_service.adjust_session_start(db_conn, device["id"], t0 - timedelta(minutes=5), cashier, approving_pin="0000", now=t0)

    with pytest.raises(ApprovalLockedOutError):
        ps_service.adjust_session_start(db_conn, device["id"], t0 - timedelta(minutes=5), cashier, approving_pin="1111", now=t0)


# --- device management -------------------------------------------------------


def test_disable_device_rejected_with_open_order(db_conn, device, owner):
    orders_service.get_or_create_device_order(db_conn, device["id"], owner["id"])
    with pytest.raises(SessionRunningError):
        ps_service.set_device_active(db_conn, device["id"], False, owner["id"])


def test_disable_device_rejected_with_running_session(db_conn, device, owner):
    _set_rates(db_conn, device["id"], 40, 60)
    ps_service.start_session(db_conn, device["id"], "single", owner["id"])
    with pytest.raises(SessionRunningError):
        ps_service.set_device_active(db_conn, device["id"], False, owner["id"])


def test_set_rates_logs_audit_with_old_and_new_values(db_conn, device, owner):
    ps_service.set_rates(db_conn, device["id"], 4000, 6000, owner["id"])
    row = db_conn.execute(
        "SELECT * FROM audit_log WHERE action = 'ps_device_rate_changed' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    assert "0->4000" in row["details"]


# --- startup consistency repair ---------------------------------------------


def test_startup_repair_creates_missing_line_for_orphan_session(db_conn, device, owner):
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    products_repo.create_product(db_conn, category_id, "قهوة", "", 2500)  # unrelated noise
    order_id = orders_repo.create_order(db_conn, None, owner["id"], device_id=device["id"])
    t0 = utc_now()
    session_id = ps_sessions_repo.create_session(
        db_conn, device["id"], order_id, "single", t0.isoformat(), 4000, device["name"], owner["id"]
    )
    # Simulate a crash right after stop_session wrote the session row but
    # before the order line got created.
    ps_sessions_repo.stop_session(
        db_conn, session_id, (t0 + timedelta(minutes=35)).isoformat(), 35, 35, 2500, None, True, owner["id"]
    )

    repaired = ps_service.run_startup_consistency_check(db_conn)
    assert repaired == 1

    items = orders_repo.list_order_items(db_conn, order_id)
    assert len(items) == 1
    assert items[0]["line_total_piasters"] == 2500
    session = ps_sessions_repo.get_session(db_conn, session_id)
    assert session["order_item_id"] == items[0]["id"]


def test_startup_repair_is_a_noop_with_nothing_to_fix(db_conn):
    assert ps_service.run_startup_consistency_check(db_conn) == 0


# --- flags in current_state --------------------------------------------------


def test_long_session_flag(db_conn, device, owner):
    _set_rates(db_conn, device["id"], 40, 60)
    t0 = utc_now()
    ps_service.start_session(db_conn, device["id"], "single", owner["id"], now=t0)
    state = ps_service.current_state(db_conn, device["id"], now=t0 + timedelta(hours=6, minutes=1))
    assert state["is_long_session"] is True


def test_not_long_session_before_the_threshold(db_conn, device, owner):
    _set_rates(db_conn, device["id"], 40, 60)
    t0 = utc_now()
    ps_service.start_session(db_conn, device["id"], "single", owner["id"], now=t0)
    state = ps_service.current_state(db_conn, device["id"], now=t0 + timedelta(hours=1))
    assert state["is_long_session"] is False


def test_free_device_state(db_conn, device):
    state = ps_service.current_state(db_conn, device["id"])
    assert state["running_session"] is None
    assert state["order"] is None
    assert state["elapsed_seconds"] == 0
