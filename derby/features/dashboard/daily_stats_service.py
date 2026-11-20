"""Aggregates everything the "إحصائيات اليوم" dashboard needs for one
business date. Every figure comes from report_service.build_report()
(the exact same function التقارير uses) or directly from ps_service/
tables_repo -- nothing here re-derives sales/PS pricing math.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Optional

from derby.core.db import orders_repo, ps_devices_repo, tables_repo
from derby.features.playstation import ps_service
from derby.features.reports import report_service

MAX_DAYS_BACK = 6  # the date switcher covers today and the 6 days before it


@dataclass
class RunningSessionStat:
    device_name: str
    mode: str
    elapsed_seconds: int
    provisional_price_piasters: int


@dataclass
class ComparisonStat:
    kind: str  # "yesterday" or "last_week"
    has_data: bool
    percent_change: Optional[float] = None


@dataclass
class DailyStats:
    business_date: date
    report: "report_service.ReportResult"
    hourly_sales_piasters: List[int] = field(default_factory=list)
    open_orders_count: int = 0
    open_orders_total_piasters: int = 0
    running_sessions: List[RunningSessionStat] = field(default_factory=list)
    tables_busy_count: int = 0
    tables_free_count: int = 0
    vs_yesterday: Optional[ComparisonStat] = None
    vs_last_week_same_weekday: Optional[ComparisonStat] = None


def _comparison(conn: sqlite3.Connection, current_net_sales: int, compare_date: date, today: date, kind: str) -> ComparisonStat:
    if compare_date > today:
        return ComparisonStat(kind=kind, has_data=False)
    compare_report = report_service.build_report(conn, compare_date, compare_date, today=today)
    if compare_report.net_sales_piasters == 0:
        return ComparisonStat(kind=kind, has_data=False)
    percent = (current_net_sales - compare_report.net_sales_piasters) / compare_report.net_sales_piasters * 100.0
    return ComparisonStat(kind=kind, has_data=True, percent_change=percent)


def build_daily_stats(conn: sqlite3.Connection, business_date: date, today: Optional[date] = None) -> DailyStats:
    today = today if today is not None else report_service.today_business_date(conn)
    report = report_service.build_report(conn, business_date, business_date, today=today)
    hourly = report_service.sales_by_hour(conn, business_date)

    open_orders = orders_repo.list_open_orders(conn)
    open_orders_total = sum(order["total_piasters"] for order in open_orders)

    running_sessions = []
    for device in ps_devices_repo.list_devices(conn, active_only=True):
        state = ps_service.current_state(conn, device["id"])
        running = state["running_session"]
        if running is not None:
            running_sessions.append(
                RunningSessionStat(
                    device_name=device["name"],
                    mode=running["mode"],
                    elapsed_seconds=state["elapsed_seconds"],
                    provisional_price_piasters=state["provisional_price_piasters"],
                )
            )

    # "Busy" matches the Tables screen's own definition: an order that
    # has no items yet doesn't count (it shows there as a free/leftover
    # card, not a busy one) -- keeping the two screens consistent.
    tables = tables_repo.list_tables(conn, active_only=True)
    busy_count = 0
    for table in tables:
        order = orders_repo.get_open_order_for_table(conn, table["id"])
        if order is not None and orders_repo.list_order_items(conn, order["id"]):
            busy_count += 1

    return DailyStats(
        business_date=business_date,
        report=report,
        hourly_sales_piasters=hourly,
        open_orders_count=len(open_orders),
        open_orders_total_piasters=open_orders_total,
        running_sessions=running_sessions,
        tables_busy_count=busy_count,
        tables_free_count=len(tables) - busy_count,
        vs_yesterday=_comparison(conn, report.net_sales_piasters, business_date - timedelta(days=1), today, "yesterday"),
        vs_last_week_same_weekday=_comparison(
            conn, report.net_sales_piasters, business_date - timedelta(days=7), today, "last_week"
        ),
    )


def earliest_selectable_date(conn: sqlite3.Connection, today: Optional[date] = None) -> date:
    today = today if today is not None else report_service.today_business_date(conn)
    return today - timedelta(days=MAX_DAYS_BACK)
