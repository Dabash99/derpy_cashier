"""Builds the Arabic closing report text sent over WhatsApp -- a pure
function (no DB, no Qt) so it has straightforward golden tests. Kept
compact (~1800 chars target): if the full text is too long, sections are
dropped in order (items beyond the top 3, then PlayStation per-device
detail), but the totals are never dropped.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from derby.core.utils.money import format_egp
from derby.features.reports.report_service import ReportResult

ARABIC_WEEKDAYS = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

TARGET_LENGTH = 1800
_MAX_PREVIOUS_DAY_NAMES = 5


def _hours_minutes(minutes: int) -> str:
    return "{0:02d}:{1:02d}".format(minutes // 60, minutes % 60)


def _header(cafe_name: str, business_date: date) -> str:
    weekday = ARABIC_WEEKDAYS[business_date.weekday()]
    return "*{0}*\nتقرير يوم {1} ({2})".format(cafe_name, business_date.strftime("%d/%m/%Y"), weekday)


def _day_section(day_report: ReportResult, top_items_limit: int, show_ps_detail: bool) -> str:
    lines = ["*مبيعات اليوم*"]
    lines.append("عدد الفواتير: {0}".format(day_report.invoice_count))
    lines.append("إجمالي المبيعات: {0}".format(format_egp(day_report.net_sales_piasters)))
    cash = day_report.payment_methods.get("cash")
    instapay = day_report.payment_methods.get("instapay")
    if cash is not None and instapay is not None:
        lines.append(
            "نقدي: {0} — إنستاباي: {1}".format(format_egp(cash.total_piasters), format_egp(instapay.total_piasters))
        )
    if day_report.discount_total_piasters:
        lines.append("الخصومات: {0}".format(format_egp(day_report.discount_total_piasters)))

    top_items = day_report.top_items_by_revenue[:top_items_limit]
    if top_items:
        lines.append("*الأصناف الأكثر طلبًا*")
        for item in top_items:
            lines.append("{0} × {1}".format(item.name, item.qty))

    if day_report.ps_devices:
        lines.append("*البلاي ستيشن*")
        if show_ps_detail:
            for device in day_report.ps_devices:
                lines.append(
                    "{0}: {1} ({2})".format(device.device_name, format_egp(device.revenue_piasters), _hours_minutes(device.minutes))
                )
        else:
            lines.append("الإجمالي: {0}".format(format_egp(day_report.ps_total_revenue_piasters)))

    lines.append("مصروفات اليوم: {0}".format(format_egp(day_report.expenses_total_piasters)))
    # Phase 9: gross/net profit (COGS-aware) sit alongside the plain
    # net-sales-minus-expenses figure the line below has always shown --
    # both numbers are real, they just answer different questions (see
    # report_service's docstring).
    lines.append("الربح الإجمالي: {0}".format(format_egp(day_report.gross_profit_piasters)))
    lines.append("الربح الصافي: {0}".format(format_egp(day_report.net_profit_piasters)))
    if day_report.waste_cost_piasters:
        lines.append("تكلفة الهالك: {0}".format(format_egp(day_report.waste_cost_piasters)))
    lines.append("*صافي اليوم: {0}*".format(format_egp(day_report.net_sales_piasters - day_report.expenses_total_piasters)))
    return "\n".join(lines)


def _month_section(month_report: ReportResult) -> str:
    lines = [
        "*من بداية الشهر*",
        "إجمالي المبيعات: {0}".format(format_egp(month_report.net_sales_piasters)),
        "المصروفات: {0}".format(format_egp(month_report.expenses_total_piasters)),
        "الربح: {0}".format(format_egp(month_report.profit_piasters)),
        "الربح الصافي (بعد تكلفة البضاعة): {0}".format(format_egp(month_report.net_profit_piasters)),
        "متوسط اليوم: {0}".format(format_egp(month_report.average_per_day_piasters)),
    ]
    return "\n".join(lines)


def _warnings_section(
    open_orders_count: int,
    running_sessions_count: int,
    previous_day_names: List[str],
    backup_status_line: Optional[str],
    low_stock_count: int = 0,
    drawer_count_difference_piasters: Optional[int] = None,
) -> Optional[str]:
    lines = []
    if open_orders_count or running_sessions_count:
        lines.append("⚠️ لسه فيه {0} طلب مفتوح و{1} جلسة بلاي ستيشن شغالة".format(open_orders_count, running_sessions_count))
    if previous_day_names:
        shown = previous_day_names[:_MAX_PREVIOUS_DAY_NAMES]
        lines.append("⚠️ من يوم سابق: {0}".format("، ".join(shown)))
    if low_stock_count:
        lines.append("⚠️ عناصر ناقصة في المخزون: {0}".format(low_stock_count))
    if drawer_count_difference_piasters is not None:
        if drawer_count_difference_piasters == 0:
            lines.append("جرد الدرج: مطابق تمامًا")
        elif drawer_count_difference_piasters > 0:
            lines.append("جرد الدرج: زيادة {0}".format(format_egp(drawer_count_difference_piasters)))
        else:
            lines.append("جرد الدرج: عجز {0}".format(format_egp(-drawer_count_difference_piasters)))
    if backup_status_line:
        lines.append(backup_status_line)
    if not lines:
        return None
    return "\n".join(lines)


def build_closing_text(
    cafe_name: str,
    business_date: date,
    day_report: ReportResult,
    month_report: ReportResult,
    open_orders_count: int = 0,
    running_sessions_count: int = 0,
    previous_day_names: Optional[List[str]] = None,
    backup_status_line: Optional[str] = None,
    low_stock_count: int = 0,
    drawer_count_difference_piasters: Optional[int] = None,
    max_length: int = TARGET_LENGTH,
) -> str:
    previous_day_names = previous_day_names or []

    def _assemble(top_items_limit: int, show_ps_detail: bool) -> str:
        blocks = [
            _header(cafe_name, business_date),
            _day_section(day_report, top_items_limit, show_ps_detail),
            _month_section(month_report),
        ]
        warnings = _warnings_section(
            open_orders_count, running_sessions_count, previous_day_names, backup_status_line,
            low_stock_count=low_stock_count, drawer_count_difference_piasters=drawer_count_difference_piasters,
        )
        if warnings:
            blocks.append(warnings)
        return "\n\n".join(blocks)

    text = _assemble(top_items_limit=5, show_ps_detail=True)
    if len(text) <= max_length:
        return text

    text = _assemble(top_items_limit=3, show_ps_detail=True)
    if len(text) <= max_length:
        return text

    return _assemble(top_items_limit=3, show_ps_detail=False)
