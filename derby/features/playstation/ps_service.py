"""PlayStation device/session orchestration -- no UI code here, same split
as derby/features/pos/orders_service.py. Timers are always computed from a
UTC started_at read back from the DB (never a running in-memory counter),
so elapsed time survives an app restart or a PC reboot.
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from derby.core.db import audit_repo, orders_repo, ps_devices_repo, ps_sessions_repo, settings_repo
from derby.core.events import bus
from derby.core.i18n import ar
from derby.core.utils.time_utils import parse_utc_iso, to_cairo, to_utc_iso, utc_now
from derby.features.playstation import pricing
from derby.features.pos import orders_service, owner_approval
from derby.features.pos.exceptions import DeviceRateNotSetError, InvalidTransitionError, SessionRunningError

MODE_SINGLE = "single"
MODE_MULTI = "multi"
_MODE_LABELS = {MODE_SINGLE: ar.PS_MODE_SINGLE_LABEL, MODE_MULTI: ar.PS_MODE_MULTI_LABEL}


def _rate_for_mode(device: sqlite3.Row, mode: str) -> int:
    return device["single_rate_piasters_per_hour"] if mode == MODE_SINGLE else device["multi_rate_piasters_per_hour"]


def _min_minutes(conn: sqlite3.Connection) -> int:
    return int(settings_repo.get(conn, "ps_min_minutes", "30") or "30")


def _rounding_step_piasters(conn: sqlite3.Connection) -> int:
    return int(settings_repo.get(conn, "rounding_step_egp", "5") or "5") * 100


def _long_session_seconds(conn: sqlite3.Connection) -> float:
    return float(settings_repo.get(conn, "ps_long_session_hours", "6") or "6") * 3600


# --- starting / switching / stopping ----------------------------------------


def start_session(conn: sqlite3.Connection, device_id: int, mode: str, user_id: int, now=None) -> sqlite3.Row:
    now = now if now is not None else utc_now()
    device = ps_devices_repo.get_device(conn, device_id)
    rate = _rate_for_mode(device, mode)
    if rate <= 0:
        raise DeviceRateNotSetError(ar.PS_ERROR_RATE_NOT_SET.format(mode=_MODE_LABELS[mode]))
    if ps_sessions_repo.get_running_session(conn, device_id) is not None:
        raise SessionRunningError("device {0} already has a running session".format(device_id))

    order = orders_service.get_or_create_device_order(conn, device_id, user_id)
    session_id = ps_sessions_repo.create_session(
        conn, device_id, order["id"], mode, to_utc_iso(now), rate, device["name"], user_id
    )
    audit_repo.log(
        conn,
        "ps_session_started",
        user_id=user_id,
        details="device={0} order={1} mode={2}".format(device_id, order["id"], mode),
    )
    bus.notify()
    return ps_sessions_repo.get_session(conn, session_id)


def switch_mode(conn: sqlite3.Connection, device_id: int, new_mode: str, user_id: int, now=None) -> sqlite3.Row:
    now = now if now is not None else utc_now()
    running = ps_sessions_repo.get_running_session(conn, device_id)
    if running is None:
        raise InvalidTransitionError("device {0} has no running session".format(device_id))
    if running["mode"] == new_mode:
        raise InvalidTransitionError("device {0} is already in mode {1}".format(device_id, new_mode))

    device = ps_devices_repo.get_device(conn, device_id)
    new_rate = _rate_for_mode(device, new_mode)
    if new_rate <= 0:
        raise DeviceRateNotSetError(ar.PS_ERROR_RATE_NOT_SET.format(mode=_MODE_LABELS[new_mode]))

    _stop_session_internal(conn, running, now, user_id, is_final=False)
    session_id = ps_sessions_repo.create_session(
        conn, device_id, running["order_id"], new_mode, to_utc_iso(now), new_rate, device["name"], user_id
    )
    audit_repo.log(
        conn,
        "ps_session_mode_changed",
        user_id=user_id,
        details="device={0} order={1} from={2} to={3}".format(device_id, running["order_id"], running["mode"], new_mode),
    )
    bus.notify()
    return ps_sessions_repo.get_session(conn, session_id)


def stop_session(conn: sqlite3.Connection, device_id: int, user_id: int, now=None) -> sqlite3.Row:
    now = now if now is not None else utc_now()
    running = ps_sessions_repo.get_running_session(conn, device_id)
    if running is None:
        raise InvalidTransitionError("device {0} has no running session".format(device_id))

    _stop_session_internal(conn, running, now, user_id, is_final=True)
    audit_repo.log(
        conn,
        "ps_session_stopped",
        user_id=user_id,
        details="device={0} order={1}".format(device_id, running["order_id"]),
    )
    bus.notify()
    return ps_sessions_repo.get_session(conn, running["id"])


def _billed_minutes_and_price(conn: sqlite3.Connection, session: sqlite3.Row, actual_minutes: int, is_final: bool):
    prior_billed_total = ps_sessions_repo.sum_billed_minutes_for_order(conn, session["order_id"])
    billed_minutes = pricing.billed_minutes_for_session(prior_billed_total, actual_minutes, _min_minutes(conn), is_final)
    price = pricing.ps_price(session["rate_snapshot_piasters_per_hour"], billed_minutes, _rounding_step_piasters(conn))
    return billed_minutes, price


def _session_line_text(conn: sqlite3.Connection, session: sqlite3.Row, started_at, stopped_at, billed_minutes: int):
    mode_label = _MODE_LABELS[session["mode"]]
    note = ar.PS_LINE_NOTE.format(
        device=session["device_name_snapshot"],
        mode=mode_label,
        start=to_cairo(started_at).strftime("%H:%M"),
        stop=to_cairo(stopped_at).strftime("%H:%M"),
        minutes=billed_minutes,
    )
    name_snapshot = "{0} - {1}".format(session["device_name_snapshot"], mode_label)
    return name_snapshot, note


def _stop_session_internal(conn: sqlite3.Connection, session: sqlite3.Row, now, user_id: int, is_final: bool) -> None:
    started_at = parse_utc_iso(session["started_at_utc"])
    elapsed_seconds = max(0, int((now - started_at).total_seconds()))
    actual_minutes = pricing.actual_minutes_from_seconds(elapsed_seconds)
    billed_minutes, price = _billed_minutes_and_price(conn, session, actual_minutes, is_final)
    name_snapshot, note = _session_line_text(conn, session, started_at, now, billed_minutes)

    try:
        item_id = orders_repo.create_order_item(
            conn, session["order_id"], "ps_time", None, name_snapshot, price, 1, price, note,
            ps_session_id=session["id"], commit=False,
        )
        ps_sessions_repo.stop_session(
            conn, session["id"], to_utc_iso(now), actual_minutes, billed_minutes, price, item_id, is_final, user_id, commit=False
        )
        orders_service.recompute_totals(conn, session["order_id"], commit=False)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# --- live state (for the PlayStation screen cards) --------------------------


def current_state(conn: sqlite3.Connection, device_id: int, now=None) -> dict:
    now = now if now is not None else utc_now()
    device = ps_devices_repo.get_device(conn, device_id)
    running = ps_sessions_repo.get_running_session(conn, device_id)
    order = orders_repo.get_open_order_for_device(conn, device_id)

    state = {
        "device": device,
        "order": order,
        "running_session": running,
        "elapsed_seconds": 0,
        "provisional_minutes": 0,
        "provisional_price_piasters": 0,
        "is_long_session": False,
        "is_previous_day": False,
    }
    if running is not None:
        started_at = parse_utc_iso(running["started_at_utc"])
        elapsed_seconds = max(0, int((now - started_at).total_seconds()))
        state["elapsed_seconds"] = elapsed_seconds
        actual_minutes = pricing.actual_minutes_from_seconds(elapsed_seconds)
        # Preview assumes "stop now would be final" -- the real stop may pick
        # a different is_final (e.g. the cashier switches mode instead).
        billed_minutes, price = _billed_minutes_and_price(conn, running, actual_minutes, True)
        state["provisional_minutes"] = billed_minutes
        state["provisional_price_piasters"] = price
        state["is_long_session"] = elapsed_seconds >= _long_session_seconds(conn)
    if order is not None:
        state["is_previous_day"] = orders_service.is_from_previous_business_day(conn, order)
    return state


# --- removing a line / backdating a start (owner approval) ------------------


def adjust_session_start(
    conn: sqlite3.Connection,
    device_id: int,
    new_started_at_utc,
    requesting_user: sqlite3.Row,
    approving_pin: Optional[str] = None,
    now=None,
) -> sqlite3.Row:
    """"ضبط وقت البدء" on a RUNNING session -- the customer arrived earlier
    or the cashier forgot to start it. new_started_at_utc cannot be in the
    future nor more than 12 hours before now."""
    now = now if now is not None else utc_now()
    running = ps_sessions_repo.get_running_session(conn, device_id)
    if running is None:
        raise InvalidTransitionError("device {0} has no running session".format(device_id))
    if new_started_at_utc > now:
        raise InvalidTransitionError(ar.PS_ADJUST_START_ERROR_FUTURE)
    if (now - new_started_at_utc).total_seconds() > 12 * 3600:
        raise InvalidTransitionError(ar.PS_ADJUST_START_ERROR_TOO_OLD)

    approver_id = owner_approval.resolve_approver(conn, requesting_user, approving_pin)
    old_started_at_utc = running["started_at_utc"]
    ps_sessions_repo.update_start_time(conn, running["id"], to_utc_iso(new_started_at_utc))
    audit_repo.log(
        conn,
        "ps_session_start_adjusted",
        user_id=requesting_user["id"],
        details="session={0} old={1} new={2} approved_by={3}".format(
            running["id"], old_started_at_utc, to_utc_iso(new_started_at_utc), approver_id
        ),
    )
    return ps_sessions_repo.get_session(conn, running["id"])


# --- device management (owner only -- enforced by the UI/permissions) -------


def add_device(conn: sqlite3.Connection, name: str, user_id: int) -> sqlite3.Row:
    device_id = ps_devices_repo.create_device(conn, name)
    audit_repo.log(conn, "ps_device_added", user_id=user_id, details="device={0} name={1}".format(device_id, name))
    return ps_devices_repo.get_device(conn, device_id)


def rename_device(conn: sqlite3.Connection, device_id: int, new_name: str, user_id: int) -> None:
    ps_devices_repo.rename_device(conn, device_id, new_name)
    audit_repo.log(conn, "ps_device_renamed", user_id=user_id, details="device={0} name={1}".format(device_id, new_name))


def move_device(conn: sqlite3.Connection, device_id: int, direction: int, user_id: int) -> None:
    ps_devices_repo.move_device(conn, device_id, direction)


def set_rates(
    conn: sqlite3.Connection, device_id: int, single_rate_piasters_per_hour: int, multi_rate_piasters_per_hour: int, user_id: int
) -> None:
    old = ps_devices_repo.get_device(conn, device_id)
    ps_devices_repo.set_rates(conn, device_id, single_rate_piasters_per_hour, multi_rate_piasters_per_hour)
    audit_repo.log(
        conn,
        "ps_device_rate_changed",
        user_id=user_id,
        details="device={0} single {1}->{2} multi {3}->{4}".format(
            device_id,
            old["single_rate_piasters_per_hour"],
            single_rate_piasters_per_hour,
            old["multi_rate_piasters_per_hour"],
            multi_rate_piasters_per_hour,
        ),
    )


def set_device_active(conn: sqlite3.Connection, device_id: int, is_active: bool, user_id: int) -> None:
    if not is_active:
        if orders_repo.get_open_order_for_device(conn, device_id) is not None:
            raise SessionRunningError("device {0} has an open order".format(device_id))
        if ps_sessions_repo.get_running_session(conn, device_id) is not None:
            raise SessionRunningError("device {0} has a running session".format(device_id))
    ps_devices_repo.set_active(conn, device_id, is_active)


# --- startup consistency repair ---------------------------------------------


def run_startup_consistency_check(conn: sqlite3.Connection) -> int:
    """Any stopped session that never got an order line (e.g. a crash right
    after stop, before the commit) gets one created now. Returns the number
    of sessions repaired, each with its own audit_log entry."""
    orphans = ps_sessions_repo.list_stopped_sessions_without_order_item(conn)
    repaired = 0
    for session in orphans:
        actual_minutes = session["actual_minutes"] or 0
        billed_minutes = session["billed_minutes"] or actual_minutes
        price = session["price_piasters"]
        if price is None:
            price = pricing.ps_price(session["rate_snapshot_piasters_per_hour"], billed_minutes, _rounding_step_piasters(conn))
        started_at = parse_utc_iso(session["started_at_utc"])
        stopped_at = parse_utc_iso(session["stopped_at_utc"])
        name_snapshot, note = _session_line_text(conn, session, started_at, stopped_at, billed_minutes)
        try:
            item_id = orders_repo.create_order_item(
                conn, session["order_id"], "ps_time", None, name_snapshot, price, 1, price, note,
                ps_session_id=session["id"], commit=False,
            )
            ps_sessions_repo.link_order_item(conn, session["id"], item_id, commit=False)
            orders_service.recompute_totals(conn, session["order_id"], commit=False)
            audit_repo.log(
                conn, "ps_consistency_repair", details="session={0} order_item={1}".format(session["id"], item_id)
            )
        except Exception:
            conn.rollback()
            raise
        repaired += 1
    return repaired
