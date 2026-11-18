"""Exporting a report, an expenses list, or a sales-log list to CSV,
Excel (.xlsx via openpyxl, imported lazily so it never slows down app
startup), or PDF (Qt-only: QPdfWriter + QTextDocument). No Qt widgets
here -- this module only writes files, so it is usable from a worker
thread (see derby/features/reports/export_worker.py) without touching
the UI thread.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Sequence, Tuple

from derby.core.theme.fonts import FONT_FAMILY, load_bundled_fonts
from derby.core.utils.money import piasters_to_egp_float, piasters_to_plain_text
from derby.features.reports.report_service import ReportResult

_SHEET_NAME_FORBIDDEN = re.compile(r'[\\/*?:\[\]]')


@dataclass
class ExportSection:
    title: str
    headers: List[str]
    rows: List[List] = field(default_factory=list)
    money_columns: Tuple[int, ...] = ()


# --- building sections from domain data -------------------------------------


def _hours_minutes(minutes: int) -> str:
    return "{0:02d}:{1:02d}".format(minutes // 60, minutes % 60)


def report_sections(report: ReportResult) -> List[ExportSection]:
    # Split in two: invoice count is a plain integer, while every other
    # summary figure is money -- keeping them in separate sections lets
    # money_columns stay a simple per-SECTION tuple (every row in the
    # money section really is money, so no per-row exception is needed).
    invoice_count = ExportSection("عدد الفواتير", ["عدد الفواتير"], [[report.invoice_count]])
    summary = ExportSection(
        "الملخص المالي",
        ["البيان", "القيمة (ج.م)"],
        [
            ["إجمالي المبيعات", report.net_sales_piasters],
            ["إجمالي الخصومات", report.discount_total_piasters],
            ["متوسط الفاتورة", report.average_invoice_piasters],
            ["متوسط اليوم", report.average_per_day_piasters],
            ["إجمالي المصروفات", report.expenses_total_piasters],
            ["الربح", report.profit_piasters],
        ],
        money_columns=(1,),
    )

    payment_methods = ExportSection(
        "طرق الدفع",
        ["الطريقة", "العدد", "الإجمالي (ج.م)"],
        [
            ["نقدي", report.payment_methods["cash"].count, report.payment_methods["cash"].total_piasters],
            ["إنستاباي", report.payment_methods["instapay"].count, report.payment_methods["instapay"].total_piasters],
        ],
        money_columns=(2,),
    )

    top_by_qty = ExportSection(
        "الأصناف الأكثر طلبًا (الكمية)",
        ["الصنف", "الكمية", "الإيراد (ج.م)"],
        [[item.name, item.qty, item.revenue_piasters] for item in report.top_items_by_qty],
        money_columns=(2,),
    )
    top_by_revenue = ExportSection(
        "الأصناف الأكثر إيرادًا",
        ["الصنف", "الكمية", "الإيراد (ج.م)"],
        [[item.name, item.qty, item.revenue_piasters] for item in report.top_items_by_revenue],
        money_columns=(2,),
    )
    sales_by_category = ExportSection(
        "المبيعات حسب القسم",
        ["القسم", "الإيراد (ج.م)"],
        [[c.category, c.total_piasters] for c in report.sales_by_category],
        money_columns=(1,),
    )
    ps_devices = ExportSection(
        "البلاي ستيشن",
        ["الجهاز", "الإيراد (ج.م)", "عدد الساعات"],
        [[d.device_name, d.revenue_piasters, _hours_minutes(d.minutes)] for d in report.ps_devices],
        money_columns=(1,),
    )
    expenses_by_category = ExportSection(
        "المصروفات حسب النوع",
        ["النوع", "الإجمالي (ج.م)"],
        [[c.category, c.total_piasters] for c in report.expenses_by_category],
        money_columns=(1,),
    )
    per_day = ExportSection(
        "تفاصيل الأيام",
        ["التاريخ", "عدد الفواتير", "المبيعات (ج.م)", "المصروفات (ج.م)", "الربح (ج.م)"],
        [
            [d.day.isoformat(), d.invoice_count, d.net_sales_piasters, d.expenses_piasters, d.profit_piasters]
            for d in report.per_day
        ],
        money_columns=(2, 3, 4),
    )

    return [
        invoice_count, summary, payment_methods, top_by_qty, top_by_revenue,
        sales_by_category, ps_devices, expenses_by_category, per_day,
    ]


def expenses_sections(expense_rows, category_name_by_id) -> List[ExportSection]:
    rows = [
        [
            expense["expense_date"],
            category_name_by_id.get(expense["category_id"], ""),
            expense["description"] or "",
            expense["amount_piasters"],
            "ملغي" if expense["status"] == "void" else "فعّال",
        ]
        for expense in expense_rows
    ]
    section = ExportSection("المصروفات", ["التاريخ", "النوع", "الوصف", "المبلغ (ج.م)", "الحالة"], rows, money_columns=(3,))
    return [section]


def sales_log_sections(order_rows, table_text_by_order, cashier_name_by_order) -> List[ExportSection]:
    _method_labels = {"cash": "نقدي", "instapay": "إنستاباي"}
    _status_labels = {"paid": "مدفوعة", "void": "باطلة"}
    rows = [
        [
            order["invoice_no"] or "",
            table_text_by_order.get(order["id"], ""),
            order["total_piasters"],
            _method_labels.get(order["payment_method"], order["payment_method"] or ""),
            cashier_name_by_order.get(order["id"], ""),
            _status_labels.get(order["status"], order["status"]),
        ]
        for order in order_rows
    ]
    section = ExportSection(
        "سجل المبيعات",
        ["رقم الفاتورة", "الترابيزة/الجهاز", "الإجمالي (ج.م)", "طريقة الدفع", "الكاشير", "الحالة"],
        rows,
        money_columns=(2,),
    )
    return [section]


# --- CSV ---------------------------------------------------------------------


def write_csv_sections(sections: Sequence[ExportSection], path: Path) -> None:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    for section in sections:
        writer.writerow([section.title])
        writer.writerow(section.headers)
        for row in section.rows:
            rendered = [
                piasters_to_plain_text(value) if index in section.money_columns else value
                for index, value in enumerate(row)
            ]
            writer.writerow(rendered)
        writer.writerow([])
    path.write_text(buffer.getvalue(), encoding="utf-8-sig")


# --- Excel (.xlsx) -----------------------------------------------------------


def _safe_sheet_name(title: str, used_names) -> str:
    cleaned = _SHEET_NAME_FORBIDDEN.sub("", title)[:31] or "ورقة"
    name = cleaned
    suffix = 2
    while name in used_names:
        name = "{0}{1}".format(cleaned[: 31 - len(str(suffix)) - 1], suffix)
        suffix += 1
    used_names.add(name)
    return name


def write_xlsx_sections(sections: Sequence[ExportSection], path: Path) -> None:
    import openpyxl  # lazy import -- keeps app startup free of this cost

    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    used_names = set()

    for section in sections:
        sheet = workbook.create_sheet(title=_safe_sheet_name(section.title, used_names))
        sheet.sheet_view.rightToLeft = True
        sheet.append(section.headers)
        for row in section.rows:
            rendered = [
                piasters_to_egp_float(value) if index in section.money_columns else value
                for index, value in enumerate(row)
            ]
            sheet.append(rendered)
        for money_index in section.money_columns:
            column_letter = sheet.cell(row=1, column=money_index + 1).column_letter
            for cell in sheet[column_letter][1:]:
                cell.number_format = "0.00"
        for column_index, header in enumerate(section.headers, start=1):
            column_letter = sheet.cell(row=1, column=column_index).column_letter
            sheet.column_dimensions[column_letter].width = max(12, len(str(header)) + 4)

    workbook.save(str(path))


# --- PDF ---------------------------------------------------------------------


def _html_table(section: ExportSection) -> str:
    header_cells = "".join("<th>{0}</th>".format(h) for h in section.headers)
    body_rows = []
    for row in section.rows:
        cells = []
        for index, value in enumerate(row):
            text = piasters_to_plain_text(value) if index in section.money_columns else str(value)
            cells.append("<td>{0}</td>".format(text))
        body_rows.append("<tr>{0}</tr>".format("".join(cells)))
    return (
        "<h3>{title}</h3>"
        "<table border='1' cellspacing='0' cellpadding='4' width='100%'>"
        "<tr>{header}</tr>{body}</table><br/>"
    ).format(title=section.title, header=header_cells, body="".join(body_rows))


def build_report_html(sections: Sequence[ExportSection], cafe_name: str, period_text: str, generated_text: str) -> str:
    tables_html = "".join(_html_table(section) for section in sections)
    return (
        "<html><body dir='rtl' style='font-family: {font}; font-size: 11pt;'>"
        "<h1>{cafe}</h1>"
        "<p>{period}</p>"
        "<p>{generated}</p>"
        "{tables}"
        "</body></html>"
    ).format(font=FONT_FAMILY, cafe=cafe_name, period=period_text, generated=generated_text, tables=tables_html)


def render_html_to_pdf(html: str, path: Path) -> None:
    load_bundled_fonts()
    # Imported here (not at module top) so a headless worker thread never
    # pays for Qt GUI classes unless a PDF export is actually requested.
    from PySide2.QtCore import QMarginsF, QRectF, Qt
    from PySide2.QtGui import QFont, QPagedPaintDevice, QPageLayout, QPainter, QPdfWriter, QTextDocument

    writer = QPdfWriter(str(path))
    writer.setPageSize(QPagedPaintDevice.A4)
    writer.setPageMargins(QMarginsF(12, 12, 12, 16), QPageLayout.Millimeter)
    writer.setResolution(150)

    document = QTextDocument()
    document.setDefaultFont(QFont(FONT_FAMILY, 10))
    document.setHtml(html)

    page_width = writer.width()
    footer_height = writer.height() * 0.04
    page_height = writer.height() - footer_height
    document.setPageSize(QRectF(0, 0, page_width, page_height).size())

    painter = QPainter(writer)
    painter.setLayoutDirection(Qt.RightToLeft)
    page_count = max(1, document.pageCount())
    for page_index in range(page_count):
        if page_index > 0:
            writer.newPage()
        clip_rect = QRectF(0, page_index * page_height, page_width, page_height)
        painter.save()
        painter.translate(0, -clip_rect.top())
        document.drawContents(painter, clip_rect)
        painter.restore()
        footer_text = "صفحة {0} من {1}".format(page_index + 1, page_count)
        painter.drawText(QRectF(0, page_height, page_width, footer_height), Qt.AlignCenter, footer_text)
    painter.end()


def export_report_pdf(
    report: ReportResult, cafe_name: str, generated_at_cairo: datetime, path: Path
) -> None:
    period_text = "الفترة: {0} إلى {1}".format(report.start_date.isoformat(), report.end_date.isoformat())
    generated_text = "تم الإنشاء: {0}".format(generated_at_cairo.strftime("%Y-%m-%d %H:%M"))
    html = build_report_html(report_sections(report), cafe_name or "ديربي", period_text, generated_text)
    render_html_to_pdf(html, path)


# --- convenience top-level exports -------------------------------------------


def export_report_csv(report: ReportResult, path: Path) -> None:
    write_csv_sections(report_sections(report), path)


def export_report_xlsx(report: ReportResult, path: Path) -> None:
    write_xlsx_sections(report_sections(report), path)


def export_expenses_csv(expense_rows, category_name_by_id, path: Path) -> None:
    write_csv_sections(expenses_sections(expense_rows, category_name_by_id), path)


def export_expenses_xlsx(expense_rows, category_name_by_id, path: Path) -> None:
    write_xlsx_sections(expenses_sections(expense_rows, category_name_by_id), path)


def export_sales_log_csv(order_rows, table_text_by_order, cashier_name_by_order, path: Path) -> None:
    write_csv_sections(sales_log_sections(order_rows, table_text_by_order, cashier_name_by_order), path)


def export_sales_log_xlsx(order_rows, table_text_by_order, cashier_name_by_order, path: Path) -> None:
    write_xlsx_sections(sales_log_sections(order_rows, table_text_by_order, cashier_name_by_order), path)
