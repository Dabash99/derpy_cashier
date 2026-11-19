"""The Reports screen (owner only): daily / monthly / custom-range views
sharing one render of report_service.ReportResult -- summary, payment
methods, top items (qty/revenue toggle), sales by category, PlayStation
per device, expenses by category, a per-day table, and CSV/Excel/PDF
export. Kept light: plain QTableWidgets, no chart libraries.
"""
from __future__ import annotations

import calendar
import sqlite3
from datetime import date

from PySide2.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from derby.core.db import settings_repo
from derby.core.i18n import ar
from derby.core.theme.table_style import centered_item, configure_table, right_item
from derby.core.utils.money import format_egp
from derby.core.utils.time_utils import to_cairo, utc_now
from derby.features.reports import report_service
from derby.features.reports.export_panel import ExportPanel
from derby.features.reports.export_service import export_report_csv, export_report_pdf, export_report_xlsx

_PAYMENT_METHOD_LABELS = {"cash": "نقدي", "instapay": "إنستاباي"}


def _month_bounds(year_month: str):
    year, month = (int(part) for part in year_month.split("-"))
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _hours_minutes(minutes: int) -> str:
    return "{0:02d}:{1:02d}".format(minutes // 60, minutes % 60)


class ReportsScreen(QWidget):
    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._report = None
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel(ar.REPORTS_TITLE)
        title.setProperty("role", "title")
        layout.addWidget(title)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_daily_tab(), ar.REPORTS_TAB_DAILY)
        self._tabs.addTab(self._build_monthly_tab(), ar.REPORTS_TAB_MONTHLY)
        self._tabs.addTab(self._build_custom_tab(), ar.REPORTS_TAB_CUSTOM)
        self._tabs.currentChanged.connect(self.reload)
        layout.addWidget(self._tabs)

        self._warning_label = QLabel("")
        self._warning_label.setProperty("role", "error")
        self._warning_label.setWordWrap(True)
        layout.addWidget(self._warning_label)

        self._summary_label = QLabel("")
        self._summary_label.setWordWrap(True)
        layout.addWidget(self._summary_label)

        self._payment_table = self._build_table([ar.REPORTS_COLUMN_METHOD, ar.REPORTS_COLUMN_COUNT, ar.REPORTS_COLUMN_TOTAL])
        layout.addWidget(QLabel(ar.REPORTS_PAYMENT_METHODS_TITLE))
        layout.addWidget(self._payment_table)

        top_items_row = QHBoxLayout()
        top_items_row.addWidget(QLabel("{0} {1}".format(ar.REPORTS_TOP_ITEMS_TITLE, ar.REPORTS_TOP_ITEMS_GROSS_NOTE)))
        self._top_items_toggle = QComboBox()
        self._top_items_toggle.addItem(ar.REPORTS_TOP_ITEMS_BY_QTY_TAB, "qty")
        self._top_items_toggle.addItem(ar.REPORTS_TOP_ITEMS_BY_REVENUE_TAB, "revenue")
        self._top_items_toggle.currentIndexChanged.connect(self._render_top_items)
        top_items_row.addWidget(self._top_items_toggle)
        layout.addLayout(top_items_row)
        self._top_items_table = self._build_table([ar.REPORTS_COLUMN_ITEM_NAME, ar.REPORTS_COLUMN_QTY, ar.REPORTS_COLUMN_REVENUE])
        layout.addWidget(self._top_items_table)

        layout.addWidget(QLabel(ar.REPORTS_SALES_BY_CATEGORY_TITLE))
        self._category_table = self._build_table([ar.REPORTS_COLUMN_CATEGORY, ar.REPORTS_COLUMN_REVENUE])
        layout.addWidget(self._category_table)

        layout.addWidget(QLabel(ar.REPORTS_PS_TITLE))
        self._ps_table = self._build_table([ar.REPORTS_COLUMN_DEVICE, ar.REPORTS_COLUMN_REVENUE, ar.REPORTS_COLUMN_HOURS])
        layout.addWidget(self._ps_table)
        self._ps_share_label = QLabel("")
        layout.addWidget(self._ps_share_label)

        layout.addWidget(QLabel(ar.REPORTS_EXPENSES_BY_CATEGORY_TITLE))
        self._expenses_table = self._build_table([ar.REPORTS_COLUMN_CATEGORY, ar.REPORTS_COLUMN_TOTAL])
        layout.addWidget(self._expenses_table)

        layout.addWidget(QLabel(ar.REPORTS_PER_DAY_TITLE))
        self._per_day_table = self._build_table(
            [ar.REPORTS_COLUMN_DATE, ar.REPORTS_COLUMN_INVOICES, ar.REPORTS_COLUMN_NET_SALES, ar.REPORTS_COLUMN_EXPENSES, ar.REPORTS_COLUMN_PROFIT]
        )
        layout.addWidget(self._per_day_table)

        self._export_panel = ExportPanel(self._default_filename_stem)
        self._export_panel.set_exporters(csv_fn=self._export_csv, xlsx_fn=self._export_xlsx, pdf_fn=self._export_pdf)
        layout.addWidget(self._export_panel)

    @staticmethod
    def _build_table(headers) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        configure_table(table, stretch_columns=(0,))  # column 0 is always the name/date/method label
        return table

    # --- date range tabs ---------------------------------------------------

    def _build_daily_tab(self) -> QWidget:
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.addWidget(QLabel(ar.REPORTS_DATE_LABEL))
        self._daily_input = QLineEdit(report_service.today_business_date(self._conn).isoformat())
        self._daily_input.editingFinished.connect(self.reload)
        layout.addWidget(self._daily_input)
        return tab

    def _build_monthly_tab(self) -> QWidget:
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.addWidget(QLabel(ar.REPORTS_MONTH_LABEL))
        self._monthly_input = QLineEdit(report_service.today_business_date(self._conn).strftime("%Y-%m"))
        self._monthly_input.editingFinished.connect(self.reload)
        layout.addWidget(self._monthly_input)
        return tab

    def _build_custom_tab(self) -> QWidget:
        tab = QWidget()
        layout = QHBoxLayout(tab)
        today_iso = report_service.today_business_date(self._conn).isoformat()
        layout.addWidget(QLabel(ar.REPORTS_FROM_LABEL))
        self._custom_from_input = QLineEdit(today_iso)
        self._custom_from_input.editingFinished.connect(self.reload)
        layout.addWidget(self._custom_from_input)
        layout.addWidget(QLabel(ar.REPORTS_TO_LABEL))
        self._custom_to_input = QLineEdit(today_iso)
        self._custom_to_input.editingFinished.connect(self.reload)
        layout.addWidget(self._custom_to_input)
        return tab

    def current_range(self):
        index = self._tabs.currentIndex()
        if index == 0:
            day = date.fromisoformat(self._daily_input.text().strip())
            return day, day
        if index == 1:
            return _month_bounds(self._monthly_input.text().strip())
        start = date.fromisoformat(self._custom_from_input.text().strip())
        end = date.fromisoformat(self._custom_to_input.text().strip())
        return start, end

    # --- rendering -----------------------------------------------------

    def reload(self) -> None:
        try:
            start_date, end_date = self.current_range()
        except ValueError:
            return
        self._report = report_service.build_report(self._conn, start_date, end_date)
        self._render()

    def _render(self) -> None:
        report = self._report
        if report.open_orders_count or report.running_sessions_count:
            self._warning_label.setText(
                ar.REPORTS_WARNING_OPEN_ORDERS.format(
                    open_orders=report.open_orders_count, running_sessions=report.running_sessions_count
                )
            )
        else:
            self._warning_label.setText("")

        self._summary_label.setText(
            "{net}: {net_v}  —  {disc}: {disc_v}  —  {inv}: {inv_v}  —  {avg_inv}: {avg_inv_v}  —  "
            "{avg_day}: {avg_day_v}  —  {exp}: {exp_v}  —  {profit}: {profit_v}".format(
                net=ar.REPORTS_SUMMARY_NET_SALES, net_v=format_egp(report.net_sales_piasters),
                disc=ar.REPORTS_SUMMARY_DISCOUNTS, disc_v=format_egp(report.discount_total_piasters),
                inv=ar.REPORTS_SUMMARY_INVOICE_COUNT, inv_v=report.invoice_count,
                avg_inv=ar.REPORTS_SUMMARY_AVERAGE_INVOICE, avg_inv_v=format_egp(report.average_invoice_piasters),
                avg_day=ar.REPORTS_SUMMARY_AVERAGE_PER_DAY, avg_day_v=format_egp(report.average_per_day_piasters),
                exp=ar.REPORTS_SUMMARY_EXPENSES, exp_v=format_egp(report.expenses_total_piasters),
                profit=ar.REPORTS_SUMMARY_PROFIT, profit_v=format_egp(report.profit_piasters),
            )
        )

        self._fill_table(
            self._payment_table,
            [
                [_PAYMENT_METHOD_LABELS[method], str(stat.count), format_egp(stat.total_piasters)]
                for method, stat in report.payment_methods.items()
            ],
        )
        self._render_top_items()
        self._fill_table(self._category_table, [[c.category, format_egp(c.total_piasters)] for c in report.sales_by_category])
        self._fill_table(
            self._ps_table,
            [[d.device_name, format_egp(d.revenue_piasters), _hours_minutes(d.minutes)] for d in report.ps_devices],
        )
        share = (report.ps_total_revenue_piasters / report.net_sales_piasters * 100) if report.net_sales_piasters else 0
        self._ps_share_label.setText(ar.REPORTS_PS_SHARE_LABEL.format(percent="{0:.1f}".format(share)))
        self._fill_table(
            self._expenses_table, [[c.category, format_egp(c.total_piasters)] for c in report.expenses_by_category]
        )
        self._fill_table(
            self._per_day_table,
            [
                [d.day.isoformat(), str(d.invoice_count), format_egp(d.net_sales_piasters), format_egp(d.expenses_piasters), format_egp(d.profit_piasters)]
                for d in report.per_day
            ],
        )

    def _render_top_items(self) -> None:
        if self._report is None:
            return
        items = self._report.top_items_by_qty if self._top_items_toggle.currentData() == "qty" else self._report.top_items_by_revenue
        self._fill_table(self._top_items_table, [[item.name, str(item.qty), format_egp(item.revenue_piasters)] for item in items])

    @staticmethod
    def _fill_table(table: QTableWidget, rows) -> None:
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                make_item = right_item if column_index == 0 else centered_item
                table.setItem(row_index, column_index, make_item(value))

    # --- export --------------------------------------------------------

    def _default_filename_stem(self) -> str:
        if self._report is None:
            return "تقرير"
        return "تقرير_{0}_{1}".format(self._report.start_date.isoformat(), self._report.end_date.isoformat())

    def _export_csv(self, path) -> None:
        export_report_csv(self._report, path)

    def _export_xlsx(self, path) -> None:
        export_report_xlsx(self._report, path)

    def _export_pdf(self, path) -> None:
        cafe_name = settings_repo.get(self._conn, "cafe_name", "") or "ديربي"
        generated_at_cairo = to_cairo(utc_now())
        export_report_pdf(self._report, cafe_name, generated_at_cairo, path)
