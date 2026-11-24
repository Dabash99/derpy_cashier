"""The Reports screen (owner only): daily / monthly / custom-range views
sharing one render of report_service.ReportResult -- summary, payment
methods, top items (qty/revenue toggle), sales by category, PlayStation
per device, expenses by category, a per-day table, and CSV/Excel/PDF
export. Kept light: plain QTableWidgets, no chart libraries.

The whole report (several small tables stacked under five stat tiles)
is taller than the window at 1024x680, so everything below the tabs
lives in its own QScrollArea -- without it, a plain QVBoxLayout
squeezes every table down toward its near-zero minimum size hint
instead of its real row count, which is what used to show nothing but
clipped headers and stray internal scrollbars.
"""
from __future__ import annotations

import calendar
import sqlite3
from datetime import date
from typing import List

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from derby.core.db import settings_repo
from derby.core.i18n import ar
from derby.core.theme import icons
from derby.core.theme.stat_tile import StatTile
from derby.core.theme.styled import enable_styled_background
from derby.core.theme.tab_bar import configure_tab_widget
from derby.core.theme.table_style import centered_item, configure_table, fit_table_height, right_item
from derby.core.utils.money import format_egp
from derby.core.utils.screen_refresh import RefreshOnChangeMixin
from derby.core.utils.time_utils import to_cairo, utc_now
from derby.features.reports import report_service
from derby.features.reports.export_panel import ExportPanel
from derby.features.reports.export_service import export_report_csv, export_report_pdf, export_report_xlsx

_PAYMENT_METHOD_LABELS = {"cash": "نقدي", "instapay": "إنستاباي", "credit": ar.PAYMENT_METHOD_CREDIT}


def _month_bounds(year_month: str):
    year, month = (int(part) for part in year_month.split("-"))
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _hours_minutes(minutes: int) -> str:
    return "{0:02d}:{1:02d}".format(minutes // 60, minutes % 60)


class _TableSection:
    """One "section title [+ extra widget] / table / empty-state label"
    block. Kept as a tiny holder rather than a bag of loose attributes
    on ReportsScreen, since there are six of these."""

    def __init__(self, table: QTableWidget, empty_label: QLabel) -> None:
        self.table = table
        self.empty_label = empty_label

    def fill(self, rows: List[list]) -> None:
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                make_item = right_item if column_index == 0 else centered_item
                self.table.setItem(row_index, column_index, make_item(value))
        fit_table_height(self.table)
        self.table.setVisible(bool(rows))
        self.empty_label.setVisible(not rows)


class ReportsScreen(RefreshOnChangeMixin, QWidget):
    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._report = None
        self._build_ui()
        self.reload()
        self._init_refresh_on_change()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        title = QLabel(ar.REPORTS_TITLE)
        title.setProperty("role", "title")
        outer.addWidget(title)

        self._tabs = QTabWidget()
        configure_tab_widget(self._tabs)
        self._tabs.addTab(self._build_daily_tab(), ar.REPORTS_TAB_DAILY)
        self._tabs.addTab(self._build_monthly_tab(), ar.REPORTS_TAB_MONTHLY)
        self._tabs.addTab(self._build_custom_tab(), ar.REPORTS_TAB_CUSTOM)
        self._tabs.currentChanged.connect(self.reload)
        outer.addWidget(self._tabs)

        self._warning_banner, self._warning_label = self._build_warning_banner()
        outer.addWidget(self._warning_banner)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content_host = QWidget()
        content_layout = QVBoxLayout(content_host)
        scroll_area.setWidget(content_host)
        outer.addWidget(scroll_area, 1)

        content_layout.addLayout(self._build_primary_stat_tiles())
        content_layout.addLayout(self._build_secondary_stat_tiles())

        self._payment_section = self._add_section(
            content_layout, ar.REPORTS_PAYMENT_METHODS_TITLE,
            [ar.REPORTS_COLUMN_METHOD, ar.REPORTS_COLUMN_COUNT, ar.REPORTS_COLUMN_TOTAL],
        )

        self._top_items_toggle = QComboBox()
        self._top_items_toggle.addItem(ar.REPORTS_TOP_ITEMS_BY_QTY_TAB, "qty")
        self._top_items_toggle.addItem(ar.REPORTS_TOP_ITEMS_BY_REVENUE_TAB, "revenue")
        self._top_items_toggle.currentIndexChanged.connect(self._render_top_items)
        self._top_items_section = self._add_section(
            content_layout,
            "{0} {1}".format(ar.REPORTS_TOP_ITEMS_TITLE, ar.REPORTS_TOP_ITEMS_GROSS_NOTE),
            [ar.REPORTS_COLUMN_ITEM_NAME, ar.REPORTS_COLUMN_QTY, ar.REPORTS_COLUMN_REVENUE],
            extra_header_widget=self._top_items_toggle,
        )

        self._category_section = self._add_section(
            content_layout, ar.REPORTS_SALES_BY_CATEGORY_TITLE, [ar.REPORTS_COLUMN_CATEGORY, ar.REPORTS_COLUMN_REVENUE]
        )

        self._ps_section = self._add_section(
            content_layout, ar.REPORTS_PS_TITLE,
            [ar.REPORTS_COLUMN_DEVICE, ar.REPORTS_COLUMN_REVENUE, ar.REPORTS_COLUMN_HOURS],
        )
        self._ps_share_label = QLabel("")
        content_layout.addWidget(self._ps_share_label)

        self._expenses_section = self._add_section(
            content_layout, ar.REPORTS_EXPENSES_BY_CATEGORY_TITLE, [ar.REPORTS_COLUMN_CATEGORY, ar.REPORTS_COLUMN_TOTAL]
        )

        self._per_day_section = self._add_section(
            content_layout, ar.REPORTS_PER_DAY_TITLE,
            [ar.REPORTS_COLUMN_DATE, ar.REPORTS_COLUMN_INVOICES, ar.REPORTS_COLUMN_NET_SALES, ar.REPORTS_COLUMN_EXPENSES, ar.REPORTS_COLUMN_PROFIT],
        )

        profit_title = QLabel(ar.REPORTS_TAB_PROFIT)
        profit_title.setProperty("role", "title")
        content_layout.addWidget(profit_title)
        content_layout.addLayout(self._build_profit_stat_tiles())
        self._top_by_profit_section = self._add_section(
            content_layout, ar.PROFIT_TOP_BY_PROFIT_TITLE,
            [ar.REPORTS_COLUMN_ITEM_NAME, ar.REPORTS_COLUMN_REVENUE, ar.PROFIT_GROSS_LABEL],
        )
        self._low_margin_section = self._add_section(
            content_layout, ar.PROFIT_LOW_MARGIN_TITLE,
            [ar.REPORTS_COLUMN_ITEM_NAME, ar.REPORTS_COLUMN_REVENUE, ar.PROFIT_GROSS_LABEL],
        )

        content_layout.addStretch(1)

        self._export_panel = ExportPanel(self._default_filename_stem)
        self._export_panel.set_exporters(csv_fn=self._export_csv, xlsx_fn=self._export_xlsx, pdf_fn=self._export_pdf)
        outer.addWidget(self._export_panel)

    def _build_warning_banner(self):
        banner = QWidget()
        banner.setProperty("variant", "banner")
        enable_styled_background(banner)
        row = QHBoxLayout(banner)
        icon_label = QLabel()
        icon_label.setPixmap(icons.icon("warning", variant="dark").pixmap(20, 20))
        row.addWidget(icon_label)
        warning_label = QLabel("")
        warning_label.setWordWrap(True)
        row.addWidget(warning_label, 1)
        banner.setVisible(False)
        return banner, warning_label

    def _build_primary_stat_tiles(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._tile_net_sales = StatTile(ar.REPORTS_SUMMARY_NET_SALES)
        self._tile_discounts = StatTile(ar.REPORTS_SUMMARY_DISCOUNTS)
        self._tile_invoice_count = StatTile(ar.REPORTS_SUMMARY_INVOICE_COUNT)
        self._tile_average_invoice = StatTile(ar.REPORTS_SUMMARY_AVERAGE_INVOICE)
        self._tile_average_per_day = StatTile(ar.REPORTS_SUMMARY_AVERAGE_PER_DAY)
        for tile in (
            self._tile_net_sales, self._tile_discounts, self._tile_invoice_count,
            self._tile_average_invoice, self._tile_average_per_day,
        ):
            row.addWidget(tile)
        return row

    def _build_secondary_stat_tiles(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._tile_expenses = StatTile(ar.REPORTS_SUMMARY_EXPENSES)
        self._tile_profit = StatTile(ar.REPORTS_SUMMARY_PROFIT)
        row.addWidget(self._tile_expenses)
        row.addWidget(self._tile_profit)
        row.addStretch(1)
        return row

    def _build_profit_stat_tiles(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self._tile_cogs = StatTile(ar.PROFIT_COGS_LABEL)
        self._tile_gross_profit = StatTile(ar.PROFIT_GROSS_LABEL)
        self._tile_operating_expenses = StatTile(ar.PROFIT_OPERATING_EXPENSES_LABEL)
        self._tile_net_profit = StatTile(ar.PROFIT_NET_LABEL)
        self._tile_food_revenue = StatTile(ar.PROFIT_FOOD_REVENUE_LABEL)
        self._tile_ps_revenue = StatTile(ar.PROFIT_PS_REVENUE_LABEL)
        self._tile_waste_cost = StatTile(ar.PROFIT_WASTE_COST_LABEL)
        for tile in (
            self._tile_cogs, self._tile_gross_profit, self._tile_operating_expenses, self._tile_net_profit,
            self._tile_food_revenue, self._tile_ps_revenue, self._tile_waste_cost,
        ):
            row.addWidget(tile)
        return row

    def _add_section(self, content_layout: QVBoxLayout, title_text: str, headers, extra_header_widget: QWidget = None) -> _TableSection:
        header_row = QHBoxLayout()
        label = QLabel(title_text)
        label.setProperty("role", "subtitle")
        header_row.addWidget(label)
        header_row.addStretch(1)
        if extra_header_widget is not None:
            header_row.addWidget(extra_header_widget)
        content_layout.addLayout(header_row)

        table = self._build_table(headers)
        content_layout.addWidget(table)

        empty_label = QLabel(ar.REPORTS_EMPTY_STATE)
        empty_label.setWordWrap(True)
        empty_label.setVisible(False)
        content_layout.addWidget(empty_label)

        return _TableSection(table, empty_label)

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
            self._warning_banner.setVisible(True)
        else:
            self._warning_label.setText("")
            self._warning_banner.setVisible(False)

        self._tile_net_sales.set_value(format_egp(report.net_sales_piasters))
        self._tile_discounts.set_value(format_egp(report.discount_total_piasters))
        self._tile_invoice_count.set_value(str(report.invoice_count))
        self._tile_average_invoice.set_value(format_egp(report.average_invoice_piasters))
        self._tile_average_per_day.set_value(format_egp(report.average_per_day_piasters))
        self._tile_expenses.set_value(format_egp(report.expenses_total_piasters))
        self._tile_profit.set_value(format_egp(report.profit_piasters))

        self._payment_section.fill(
            [
                [_PAYMENT_METHOD_LABELS[method], str(stat.count), format_egp(stat.total_piasters)]
                for method, stat in report.payment_methods.items()
            ]
        )
        self._render_top_items()
        self._category_section.fill([[c.category, format_egp(c.total_piasters)] for c in report.sales_by_category])
        self._ps_section.fill(
            [[d.device_name, format_egp(d.revenue_piasters), _hours_minutes(d.minutes)] for d in report.ps_devices]
        )
        share = (report.ps_total_revenue_piasters / report.net_sales_piasters * 100) if report.net_sales_piasters else 0
        self._ps_share_label.setText(ar.REPORTS_PS_SHARE_LABEL.format(percent="{0:.1f}".format(share)))
        self._expenses_section.fill([[c.category, format_egp(c.total_piasters)] for c in report.expenses_by_category])
        self._per_day_section.fill(
            [
                [d.day.isoformat(), str(d.invoice_count), format_egp(d.net_sales_piasters), format_egp(d.expenses_piasters), format_egp(d.profit_piasters)]
                for d in report.per_day
            ]
        )

        self._tile_cogs.set_value(format_egp(report.cogs_piasters))
        self._tile_gross_profit.set_value(format_egp(report.gross_profit_piasters))
        self._tile_operating_expenses.set_value(format_egp(report.operating_expenses_piasters))
        self._tile_net_profit.set_value(format_egp(report.net_profit_piasters))
        self._tile_food_revenue.set_value(format_egp(report.food_drinks_revenue_piasters))
        self._tile_ps_revenue.set_value(format_egp(report.ps_total_revenue_piasters))
        self._tile_waste_cost.set_value(format_egp(report.waste_cost_piasters))
        self._top_by_profit_section.fill(
            [[item.name, format_egp(item.revenue_piasters), format_egp(item.profit_piasters)] for item in report.top_items_by_profit]
        )
        if report.low_margin_items:
            self._low_margin_section.fill(
                [[item.name, format_egp(item.revenue_piasters), format_egp(item.profit_piasters)] for item in report.low_margin_items]
            )
        else:
            self._low_margin_section.fill([])
            self._low_margin_section.empty_label.setText(ar.PROFIT_EMPTY_LOW_MARGIN)

    def _render_top_items(self) -> None:
        if self._report is None:
            return
        items = self._report.top_items_by_qty if self._top_items_toggle.currentData() == "qty" else self._report.top_items_by_revenue
        self._top_items_section.fill([[item.name, str(item.qty), format_egp(item.revenue_piasters)] for item in items])

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
