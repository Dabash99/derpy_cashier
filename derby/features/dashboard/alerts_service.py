"""تنبيهات (alerts center) on الرئيسية -- owner only (every alert here
exposes something privacy-class-sensitive: receivables, supplier debt,
drawer/shift state, or is simply not actionable by a cashier), compact
and tappable. Every check is a light, indexed query; each one runs
inside its own try/except in compute_alerts so one failing check (an
unexpected schema state, a missing setting) never takes the whole
dashboard down with it -- same discipline as daily_stats_screen._safe.
"""
from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass
from datetime import date
from datetime import time as time_of_day
from typing import List, Optional

from derby.core.db import (
    ps_devices_repo,
    ps_sessions_repo,
    purchases_repo,
    settings_repo,
    shifts_repo,
    stock_items_repo,
)
from derby.core.i18n import ar
from derby.core.utils import error_log
from derby.core.utils.business_date import business_date as compute_business_date
from derby.core.utils.time_utils import parse_utc_iso, utc_now
from derby.features.closing import backup_service

SEVERITY_WARNING = "warning"
SEVERITY_ERROR = "error"


@dataclass
class Alert:
    text: str
    severity: str
    navigate_key: Optional[str] = None


def _close_time_setting(conn: sqlite3.Connection) -> time_of_day:
    text = settings_repo.get(conn, "business_close_time", "23:59") or "23:59"
    hour_str, minute_str = text.split(":")
    return time_of_day(int(hour_str), int(minute_str))


def _enabled(conn: sqlite3.Connection, key: str) -> bool:
    return settings_repo.get(conn, key, "1") == "1"


def _check_ps_long_sessions(conn: sqlite3.Connection, now) -> List[Alert]:
    if not _enabled(conn, "alert_ps_long_session_enabled"):
        return []
    threshold_hours = int(settings_repo.get(conn, "ps_long_session_alert_hours", "6") or "6")
    alerts = []
    for session in ps_sessions_repo.list_running_sessions(conn):
        started = parse_utc_iso(session["started_at_utc"])
        hours_running = (now - started).total_seconds() / 3600.0
        if hours_running >= threshold_hours:
            device = ps_devices_repo.get_device(conn, session["device_id"])
            device_name = device["name"] if device is not None else session["device_name_snapshot"]
            alerts.append(
                Alert(
                    ar.ALERT_PS_LONG_SESSION.format(device=device_name, hours=int(hours_running)),
                    SEVERITY_WARNING, "playstation",
                )
            )
    return alerts


def _check_customer_overdue(conn: sqlite3.Connection, today: date) -> List[Alert]:
    if not _enabled(conn, "alert_customer_overdue_enabled"):
        return []
    from derby.core.db import customers_repo
    from derby.features.customers import customer_service

    overdue_days = int(settings_repo.get(conn, "customer_overdue_days", "14") or "14")
    count = sum(
        1 for customer in customers_repo.list_customers(conn, active_only=True)
        if customer_service.is_overdue(conn, customer["id"], overdue_days, today)
    )
    if count:
        return [Alert(ar.ALERT_CUSTOMER_OVERDUE.format(count=count), SEVERITY_WARNING, "customers")]
    return []


def _check_backup_overdue(conn: sqlite3.Connection, now) -> List[Alert]:
    if not _enabled(conn, "alert_backup_overdue_enabled"):
        return []
    from pathlib import Path

    secondary_text = settings_repo.get(conn, "backup_folder_secondary", "") or ""
    secondary_dir = Path(secondary_text) if secondary_text else None
    warning_days = int(settings_repo.get(conn, "backup_warning_days", "2") or "2")
    status = backup_service.external_backup_status(conn, now, secondary_dir, warning_days)
    if status != "ok":
        return [Alert(ar.ALERT_BACKUP_OVERDUE, SEVERITY_WARNING, "settings")]
    return []


def _check_low_stock(conn: sqlite3.Connection, _today: date) -> List[Alert]:
    if not _enabled(conn, "alert_low_stock_enabled"):
        return []
    count = len(stock_items_repo.list_low_stock(conn))
    if count:
        return [Alert(ar.ALERT_LOW_STOCK.format(count=count), SEVERITY_WARNING, "inventory")]
    return []


def _check_drawer_not_opened(conn: sqlite3.Connection, today: date) -> List[Alert]:
    if not _enabled(conn, "alert_drawer_not_opened_enabled"):
        return []
    from derby.core.db import drawer_repo

    close_time = _close_time_setting(conn)
    last_opening = drawer_repo.get_last_opening_entry(conn)
    if last_opening is None:
        return [Alert(ar.ALERT_DRAWER_NOT_OPENED, SEVERITY_WARNING, "drawer")]
    opened_business_date = compute_business_date(parse_utc_iso(last_opening["created_at_utc"]), close_time)
    if opened_business_date != today:
        return [Alert(ar.ALERT_DRAWER_NOT_OPENED, SEVERITY_WARNING, "drawer")]
    return []


def _check_shift_left_open(conn: sqlite3.Connection, today: date) -> List[Alert]:
    if not _enabled(conn, "alert_shift_left_open_enabled"):
        return []
    open_shift = shifts_repo.get_open_shift(conn)
    if open_shift is not None and open_shift["business_date"] != today.isoformat():
        return [Alert(ar.ALERT_SHIFT_LEFT_OPEN, SEVERITY_WARNING, "shifts_employees")]
    return []


def _check_unpaid_supplier_invoices(conn: sqlite3.Connection, today: date) -> List[Alert]:
    if not _enabled(conn, "alert_unpaid_supplier_invoices_enabled"):
        return []
    days = int(settings_repo.get(conn, "supplier_invoice_overdue_days", "14") or "14")
    count = 0
    for purchase in purchases_repo.list_purchases(conn, is_paid=False):
        age = (today - date.fromisoformat(purchase["purchase_date"])).days
        if age > days:
            count += 1
    if count:
        return [Alert(ar.ALERT_UNPAID_SUPPLIER_INVOICES.format(count=count, days=days), SEVERITY_WARNING, "inventory")]
    return []


_CHECKS_NOW = (_check_ps_long_sessions, _check_backup_overdue)
_CHECKS_TODAY = (
    _check_customer_overdue, _check_low_stock, _check_drawer_not_opened,
    _check_shift_left_open, _check_unpaid_supplier_invoices,
)


def compute_alerts(conn: sqlite3.Connection, now=None) -> List[Alert]:
    now = now if now is not None else utc_now()
    today = compute_business_date(now, _close_time_setting(conn))
    alerts: List[Alert] = []
    for check in _CHECKS_NOW:
        try:
            alerts.extend(check(conn, now))
        except Exception:
            # One failing check must never take the dashboard down -- but
            # it is still logged (not silently dropped), so a real bug in
            # a check is discoverable instead of just permanently muting
            # that one alert type.
            error_log.log_exception(*sys.exc_info())
    for check in _CHECKS_TODAY:
        try:
            alerts.extend(check(conn, today))
        except Exception:
            error_log.log_exception(*sys.exc_info())
    return alerts
