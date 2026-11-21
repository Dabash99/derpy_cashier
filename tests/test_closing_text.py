"""Golden tests for the pure closing-text builder -- no DB, no Qt."""
from __future__ import annotations

from datetime import date

from derby.features.closing.closing_text import build_closing_text
from derby.features.reports.report_service import (
    CategoryAmount,
    DeviceStats,
    ItemStat,
    PaymentMethodTotal,
    ReportResult,
)


def _day_report(**overrides):
    defaults = dict(
        start_date=date(2026, 1, 10),
        end_date=date(2026, 1, 10),
        invoice_count=12,
        net_sales_piasters=150000,
        discount_total_piasters=5000,
        payment_methods={
            "cash": PaymentMethodTotal(total_piasters=100000, count=8),
            "instapay": PaymentMethodTotal(total_piasters=50000, count=4),
        },
        top_items_by_revenue=[
            ItemStat(name="قهوة", qty=20, revenue_piasters=50000),
            ItemStat(name="كرواسون", qty=15, revenue_piasters=22500),
            ItemStat(name="شاي", qty=10, revenue_piasters=10000),
            ItemStat(name="عصير", qty=8, revenue_piasters=8000),
            ItemStat(name="كيك", qty=5, revenue_piasters=15000),
        ],
        sales_by_category=[CategoryAmount(category="مشروبات", total_piasters=60000)],
        ps_devices=[DeviceStats(device_name="بلاي ستيشن 1", revenue_piasters=25000, minutes=37)],
        ps_total_revenue_piasters=25000,
        expenses_total_piasters=20000,
    )
    defaults.update(overrides)
    return ReportResult(**defaults)


def _month_report(**overrides):
    defaults = dict(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        net_sales_piasters=3000000,
        expenses_total_piasters=400000,
        profit_piasters=2600000,
        average_per_day_piasters=300000,
    )
    defaults.update(overrides)
    return ReportResult(**defaults)


def test_full_day_report_contains_expected_numbers():
    text = build_closing_text("ديربي", date(2026, 1, 10), _day_report(), _month_report())

    assert "ديربي" in text
    assert "10/01/2026" in text
    assert "السبت" in text  # 2026-01-10 is a Saturday
    assert "عدد الفواتير: 12" in text
    assert "1500.00 ج.م" in text  # net sales
    assert "نقدي: 1000.00 ج.م" in text
    assert "قهوة × 20" in text
    assert "كيك × 5" in text  # top 5 shown by default
    assert "بلاي ستيشن 1: 250.00 ج.م (00:37)" in text
    assert "صافي اليوم: 1300.00 ج.م" in text  # 1500.00 - 200.00 (expenses_total_piasters=20000)
    assert "26000.00 ج.م" in text  # month profit


def test_quiet_day_has_no_ps_or_discount_lines():
    quiet = _day_report(
        invoice_count=0, net_sales_piasters=0, discount_total_piasters=0,
        payment_methods={"cash": PaymentMethodTotal(), "instapay": PaymentMethodTotal()},
        top_items_by_revenue=[], ps_devices=[], ps_total_revenue_piasters=0, expenses_total_piasters=0,
    )
    text = build_closing_text("ديربي", date(2026, 1, 10), quiet, _month_report())
    assert "عدد الفواتير: 0" in text
    assert "الخصومات" not in text
    assert "البلاي ستيشن" not in text
    assert "الأصناف الأكثر طلبًا" not in text


def test_warnings_only_shown_when_present():
    text_without = build_closing_text("ديربي", date(2026, 1, 10), _day_report(), _month_report())
    assert "طلب مفتوح" not in text_without
    assert "من يوم سابق" not in text_without

    text_with = build_closing_text(
        "ديربي", date(2026, 1, 10), _day_report(), _month_report(),
        open_orders_count=2, running_sessions_count=1, previous_day_names=["ترابيزة 1", "ترابيزة 2"],
        backup_status_line="النسخة الاحتياطية: تمت ✅",
    )
    assert "لسه فيه 2 طلب مفتوح و1 جلسة بلاي ستيشن شغالة" in text_with
    assert "من يوم سابق: ترابيزة 1، ترابيزة 2" in text_with
    assert "النسخة الاحتياطية: تمت ✅" in text_with


def test_previous_day_names_capped_at_five():
    names = ["ترابيزة {0}".format(i) for i in range(1, 8)]
    text = build_closing_text(
        "ديربي", date(2026, 1, 10), _day_report(), _month_report(), previous_day_names=names
    )
    assert "ترابيزة 5" in text
    assert "ترابيزة 6" not in text


def test_trimming_path_drops_items_then_ps_detail_but_keeps_totals():
    many_items = [ItemStat(name="صنف رقم {0}".format(i), qty=i, revenue_piasters=i * 100) for i in range(1, 6)]
    many_devices = [DeviceStats(device_name="جهاز طويل الاسم رقم {0}".format(i), revenue_piasters=1000, minutes=60) for i in range(1, 6)]
    day = _day_report(top_items_by_revenue=many_items, ps_devices=many_devices)

    text = build_closing_text("ديربي", date(2026, 1, 10), day, _month_report(), max_length=400)

    assert len(text) <= 1800  # the hard trimming path always applies regardless of how small max_length is
    assert "صافي اليوم" in text  # totals never dropped
    assert "جهاز طويل الاسم رقم 4" not in text  # per-device detail dropped in the final trim
    assert "صنف رقم 4" not in text  # only top 3 items kept


def test_text_never_exceeds_hard_cap_even_with_many_devices():
    many_devices = [DeviceStats(device_name="جهاز {0}".format(i), revenue_piasters=1000, minutes=60) for i in range(1, 20)]
    day = _day_report(ps_devices=many_devices)
    text = build_closing_text("ديربي", date(2026, 1, 10), day, _month_report())
    assert len(text) <= 1800


def test_phase9_gross_net_waste_and_low_stock_and_drawer_count_appear():
    day = _day_report(gross_profit_piasters=130000, net_profit_piasters=110000, waste_cost_piasters=500)
    month = _month_report(net_profit_piasters=2500000)
    text = build_closing_text(
        "ديربي", date(2026, 1, 10), day, month,
        low_stock_count=3, drawer_count_difference_piasters=-200,
    )
    assert "الربح الإجمالي" in text
    assert "الربح الصافي: " in text
    assert "تكلفة الهالك" in text
    assert "عناصر ناقصة في المخزون: 3" in text
    assert "جرد الدرج: عجز" in text


def test_drawer_count_exact_match_line():
    text = build_closing_text(
        "ديربي", date(2026, 1, 10), _day_report(), _month_report(), drawer_count_difference_piasters=0
    )
    assert "جرد الدرج: مطابق تمامًا" in text
