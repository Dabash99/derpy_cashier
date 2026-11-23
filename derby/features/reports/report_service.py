"""Builds one ReportResult for a date range -- used by both the daily and
monthly views (and their exports). No UI code here; all SQL lives in
derby/core/db/reports_repo.py, this module only aggregates the rows it
gets back. Money stays integer piasters throughout.

Definitions (see also CLAUDE.md):
  - Sales = paid orders only; void and cancelled orders are excluded.
    Net sales = SUM(total_piasters) -- i.e. AFTER each order's own discount.
  - Top items / sales-by-category are computed from order_items directly,
    so they are GROSS (before the order-level discount is subtracted) --
    the Reports screen must say so next to these sections.
  - PlayStation hours = SUM(actual_minutes) / 60 of ps_time lines that are
    still on a paid order; a removed (voided) line has no order_items row
    left, so it is excluded automatically, with no extra filter needed.
  - Profit = net sales - active expenses in the same range (simple cash
    basis, no cost of goods; can be negative).
  - Average per day = net sales / days_elapsed, where days_elapsed is the
    full range length if the range already ended before `today`, or only
    the days up to and including `today` if the range is still ongoing
    (covers "a past month" vs "the current month so far").
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from datetime import time as time_of_day
from typing import Dict, List, Optional

from derby.core.db import (
    expense_categories_repo,
    expenses_repo,
    orders_repo,
    ps_sessions_repo,
    reports_repo,
    settings_repo,
    stock_movements_repo,
)
from derby.core.utils.business_date import business_date as compute_business_date
from derby.core.utils.time_utils import parse_utc_iso, to_cairo, utc_now
from derby.features.pos.orders_service import is_from_previous_business_day

# A paid purchase's auto-filed expense lives under this category (see
# migrations.py and stock_service._supplies_category_id) -- it must be
# excluded from "operating expenses" in the profit report, since the
# purchase cost is already counted through COGS (cost_at_sale_piasters).
SUPPLIES_EXPENSE_CATEGORY_NAME = "مشتريات"

PAYMENT_METHODS = ("cash", "instapay", "credit")


@dataclass
class PaymentMethodTotal:
    total_piasters: int = 0
    count: int = 0


@dataclass
class ItemStat:
    name: str
    qty: int
    revenue_piasters: int
    cost_piasters: int = 0
    profit_piasters: int = 0
    margin_percent: Optional[float] = None


@dataclass
class CategoryAmount:
    category: str
    total_piasters: int


@dataclass
class DeviceStats:
    device_name: str
    revenue_piasters: int
    minutes: int


@dataclass
class DaySummary:
    day: date
    invoice_count: int
    net_sales_piasters: int
    expenses_piasters: int
    profit_piasters: int


@dataclass
class ReportResult:
    start_date: date
    end_date: date
    invoice_count: int = 0
    net_sales_piasters: int = 0
    discount_total_piasters: int = 0
    average_invoice_piasters: int = 0
    payment_methods: Dict[str, PaymentMethodTotal] = field(default_factory=dict)
    top_items_by_qty: List[ItemStat] = field(default_factory=list)
    top_items_by_revenue: List[ItemStat] = field(default_factory=list)
    sales_by_category: List[CategoryAmount] = field(default_factory=list)
    ps_devices: List[DeviceStats] = field(default_factory=list)
    ps_total_revenue_piasters: int = 0
    expenses_total_piasters: int = 0
    expenses_by_category: List[CategoryAmount] = field(default_factory=list)
    profit_piasters: int = 0
    per_day: List[DaySummary] = field(default_factory=list)
    average_per_day_piasters: int = 0
    open_orders_count: int = 0
    running_sessions_count: int = 0
    previous_day_open_orders_count: int = 0

    # --- Phase 9: COGS / profit (owner only, see permissions.view_profit_report) ---
    cogs_piasters: int = 0
    gross_profit_piasters: int = 0
    operating_expenses_piasters: int = 0  # expenses_total_piasters minus the "مشتريات" category
    net_profit_piasters: int = 0
    food_drinks_revenue_piasters: int = 0  # net_sales_piasters - ps_total_revenue_piasters
    top_items_by_profit: List[ItemStat] = field(default_factory=list)
    low_margin_items: List[ItemStat] = field(default_factory=list)
    waste_cost_piasters: int = 0


_TOP_ITEMS_LIMIT = 10
_UNSPECIFIED_CATEGORY = "غير محدد"
# A product is flagged as "low margin" below this percent (and always
# when its margin is negative) -- no spec number given, chosen as a
# sensible cafe default; see docs/PHASE9_REPORT.md "Decisions I made".
_LOW_MARGIN_THRESHOLD_PERCENT = 10.0


def _close_time(conn: sqlite3.Connection) -> time_of_day:
    text = settings_repo.get(conn, "business_close_time", "23:59") or "23:59"
    hour_str, minute_str = text.split(":")
    return time_of_day(int(hour_str), int(minute_str))


def today_business_date(conn: sqlite3.Connection) -> date:
    return compute_business_date(utc_now(), _close_time(conn))


def days_elapsed_in_period(start_date: date, end_date: date, today: date) -> int:
    """How many days of [start_date, end_date] count toward an average:
    the whole range if it is already in the past, or only up to `today`
    if it is still ongoing (today falls inside or before the range)."""
    if today < start_date:
        return 0
    effective_end = min(end_date, today)
    return (effective_end - start_date).days + 1


def _iter_dates(start_date: date, end_date: date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def _aggregate_product_items(rows):
    by_key: Dict[str, Dict[str, int]] = {}
    category_totals: Dict[str, int] = {}
    for row in rows:
        stat = by_key.setdefault(row["name"], {"qty": 0, "revenue_piasters": 0, "cost_piasters": 0})
        stat["qty"] += row["qty"]
        stat["revenue_piasters"] += row["revenue_piasters"]
        stat["cost_piasters"] += row["cost_piasters"]
        category_name = row["category_name"] or _UNSPECIFIED_CATEGORY
        category_totals[category_name] = category_totals.get(category_name, 0) + row["revenue_piasters"]

    items = []
    for name, stat in by_key.items():
        profit = stat["revenue_piasters"] - stat["cost_piasters"]
        margin = (profit / stat["revenue_piasters"] * 100.0) if stat["revenue_piasters"] else None
        items.append(
            ItemStat(
                name=name, qty=stat["qty"], revenue_piasters=stat["revenue_piasters"],
                cost_piasters=stat["cost_piasters"], profit_piasters=profit, margin_percent=margin,
            )
        )
    top_by_qty = sorted(items, key=lambda i: i.qty, reverse=True)[:_TOP_ITEMS_LIMIT]
    top_by_revenue = sorted(items, key=lambda i: i.revenue_piasters, reverse=True)[:_TOP_ITEMS_LIMIT]
    top_by_profit = sorted(items, key=lambda i: i.profit_piasters, reverse=True)[:_TOP_ITEMS_LIMIT]
    low_margin_items = sorted(
        (i for i in items if i.cost_piasters > 0 and (i.margin_percent is None or i.margin_percent < _LOW_MARGIN_THRESHOLD_PERCENT)),
        key=lambda i: (i.margin_percent if i.margin_percent is not None else -1.0),
    )
    sales_by_category = sorted(
        (CategoryAmount(category=name, total_piasters=total) for name, total in category_totals.items()),
        key=lambda c: c.total_piasters,
        reverse=True,
    )
    return top_by_qty, top_by_revenue, top_by_profit, low_margin_items, sales_by_category


def _aggregate_ps_items(rows):
    by_device: Dict[str, Dict[str, int]] = {}
    total_cost = 0
    for row in rows:
        device_name = row["device_name"] or _UNSPECIFIED_CATEGORY
        stat = by_device.setdefault(device_name, {"revenue_piasters": 0, "minutes": 0})
        stat["revenue_piasters"] += row["revenue_piasters"]
        stat["minutes"] += row["actual_minutes"] or 0
        total_cost += row["cost_piasters"]

    devices = [
        DeviceStats(device_name=name, revenue_piasters=stat["revenue_piasters"], minutes=stat["minutes"])
        for name, stat in by_device.items()
    ]
    devices.sort(key=lambda d: d.revenue_piasters, reverse=True)
    total_revenue = sum(d.revenue_piasters for d in devices)
    return devices, total_revenue, total_cost


def _aggregate_expenses_by_category(conn: sqlite3.Connection, expense_rows) -> List[CategoryAmount]:
    totals: Dict[int, int] = {}
    for row in expense_rows:
        totals[row["category_id"]] = totals.get(row["category_id"], 0) + row["amount_piasters"]
    result = []
    for category_id, total in totals.items():
        category = expense_categories_repo.get_category(conn, category_id)
        name = category["name"] if category is not None else _UNSPECIFIED_CATEGORY
        result.append(CategoryAmount(category=name, total_piasters=total))
    result.sort(key=lambda c: c.total_piasters, reverse=True)
    return result


def _build_per_day(start_date: date, end_date: date, paid_orders, expense_rows) -> List[DaySummary]:
    invoices_by_day: Dict[str, int] = {}
    sales_by_day: Dict[str, int] = {}
    for order in paid_orders:
        day = order["business_date"]
        invoices_by_day[day] = invoices_by_day.get(day, 0) + 1
        sales_by_day[day] = sales_by_day.get(day, 0) + order["total_piasters"]

    expenses_by_day: Dict[str, int] = {}
    for expense in expense_rows:
        day = expense["expense_date"]
        expenses_by_day[day] = expenses_by_day.get(day, 0) + expense["amount_piasters"]

    per_day = []
    for day in _iter_dates(start_date, end_date):
        day_iso = day.isoformat()
        net_sales = sales_by_day.get(day_iso, 0)
        expenses_total = expenses_by_day.get(day_iso, 0)
        per_day.append(
            DaySummary(
                day=day,
                invoice_count=invoices_by_day.get(day_iso, 0),
                net_sales_piasters=net_sales,
                expenses_piasters=expenses_total,
                profit_piasters=net_sales - expenses_total,
            )
        )
    return per_day


def sales_by_hour(conn: sqlite3.Connection, business_date: date) -> List[int]:
    """Net sales (paid orders only) bucketed by the LOCAL (Cairo) hour
    they were paid in, for ONE business date -- 24 buckets, index 0..23.
    Reuses the same paid-orders query build_report() uses; this is a new
    grouping of it (by hour instead of by day), not a second copy of the
    sales math itself."""
    iso = business_date.isoformat()
    paid_orders = reports_repo.list_paid_orders_in_range(conn, iso, iso)
    buckets = [0] * 24
    for order in paid_orders:
        if not order["paid_at_utc"]:
            continue
        hour = to_cairo(parse_utc_iso(order["paid_at_utc"])).hour
        buckets[hour] += order["total_piasters"]
    return buckets


def build_report(
    conn: sqlite3.Connection, start_date: date, end_date: date, today: Optional[date] = None
) -> ReportResult:
    today = today if today is not None else today_business_date(conn)
    start_iso, end_iso = start_date.isoformat(), end_date.isoformat()

    paid_orders = reports_repo.list_paid_orders_in_range(conn, start_iso, end_iso)
    order_ids = [order["id"] for order in paid_orders]

    invoice_count = len(paid_orders)
    net_sales = sum(order["total_piasters"] for order in paid_orders)
    discount_total = sum(order["discount_piasters"] for order in paid_orders)
    average_invoice = net_sales // invoice_count if invoice_count else 0

    payment_methods = {method: PaymentMethodTotal() for method in PAYMENT_METHODS}
    for order in paid_orders:
        # آجل (credit) sales leave payment_method NULL and set customer_id
        # instead (see orders_repo.mark_order_paid_on_credit) -- never a
        # third value in the CHECK-constrained payment_method column.
        method_key = "credit" if order["customer_id"] else order["payment_method"]
        stat = payment_methods.get(method_key)
        if stat is not None:
            stat.total_piasters += order["total_piasters"]
            stat.count += 1

    product_rows = reports_repo.list_product_item_rows(conn, order_ids)
    top_by_qty, top_by_revenue, top_by_profit, low_margin_items, sales_by_category = _aggregate_product_items(product_rows)
    product_cogs = sum(row["cost_piasters"] for row in product_rows)

    ps_rows = reports_repo.list_ps_item_rows(conn, order_ids)
    ps_devices, ps_total_revenue, ps_cogs = _aggregate_ps_items(ps_rows)

    active_expenses = expenses_repo.list_expenses(conn, start_date=start_iso, end_date=end_iso, status="active")
    expenses_total = sum(expense["amount_piasters"] for expense in active_expenses)
    expenses_by_category = _aggregate_expenses_by_category(conn, active_expenses)

    profit = net_sales - expenses_total

    # --- Phase 9: COGS / gross+net profit -----------------------------
    cogs = product_cogs + ps_cogs
    gross_profit = net_sales - cogs
    supplies_category = next(
        (c for c in expense_categories_repo.list_categories(conn) if c["name"] == SUPPLIES_EXPENSE_CATEGORY_NAME), None
    )
    supplies_expenses_total = 0
    if supplies_category is not None:
        supplies_expenses_total = sum(
            expense["amount_piasters"] for expense in active_expenses if expense["category_id"] == supplies_category["id"]
        )
    operating_expenses = expenses_total - supplies_expenses_total
    net_profit = gross_profit - operating_expenses
    waste_cost = stock_movements_repo.sum_waste_cost_in_range(conn, start_iso, end_iso)

    per_day = _build_per_day(start_date, end_date, paid_orders, active_expenses)
    days_elapsed = days_elapsed_in_period(start_date, end_date, today)
    average_per_day = net_sales // days_elapsed if days_elapsed else 0

    open_orders = orders_repo.list_orders(conn, status="open")
    previous_day_open_orders = sum(1 for order in open_orders if is_from_previous_business_day(conn, order))

    return ReportResult(
        start_date=start_date,
        end_date=end_date,
        invoice_count=invoice_count,
        net_sales_piasters=net_sales,
        discount_total_piasters=discount_total,
        average_invoice_piasters=average_invoice,
        payment_methods=payment_methods,
        top_items_by_qty=top_by_qty,
        top_items_by_revenue=top_by_revenue,
        sales_by_category=sales_by_category,
        ps_devices=ps_devices,
        ps_total_revenue_piasters=ps_total_revenue,
        expenses_total_piasters=expenses_total,
        expenses_by_category=expenses_by_category,
        profit_piasters=profit,
        per_day=per_day,
        average_per_day_piasters=average_per_day,
        open_orders_count=len(open_orders),
        running_sessions_count=ps_sessions_repo.count_running_sessions(conn),
        previous_day_open_orders_count=previous_day_open_orders,
        cogs_piasters=cogs,
        gross_profit_piasters=gross_profit,
        operating_expenses_piasters=operating_expenses,
        net_profit_piasters=net_profit,
        food_drinks_revenue_piasters=net_sales - ps_total_revenue,
        top_items_by_profit=top_by_profit,
        low_margin_items=low_margin_items,
        waste_cost_piasters=waste_cost,
    )
