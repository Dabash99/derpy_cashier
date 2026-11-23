"""إحصائيات اليوم: a read-only, single-business-day dashboard, visible
to both roles (profit/expenses figures gated to the owner). Refreshes
on show and every 30s while visible -- the QTimer starts/stops with
showEvent/hideEvent so a hidden dashboard never polls. Every figure
comes from daily_stats_service.build_daily_stats(), itself built on
report_service.build_report() -- no duplicated sales/PS math here.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import timedelta
from pathlib import Path

from PySide2.QtCore import Qt, QTimer, Signal
from PySide2.QtGui import QHideEvent, QShowEvent
from PySide2.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from derby.core.db import settings_repo, stock_items_repo
from derby.core.i18n import ar
from derby.core.theme.stat_tile import StatTile
from derby.core.theme.styled import enable_styled_background
from derby.core.utils import error_log
from derby.core.utils.money import format_egp
from derby.core.utils.time_utils import utc_now
from derby.features.auth import permissions
from derby.features.closing import backup_service
from derby.features.dashboard import daily_stats_service
from derby.features.dashboard.alerts_center import AlertsCenter
from derby.features.dashboard.hourly_bar_chart import HourlyBarChart
from derby.features.dashboard.open_orders_panel import OpenOrdersPanel
from derby.features.inventory import drawer_service
from derby.features.reports import report_service

_EXTERNAL_BACKUP_LABELS = {
    "ok": ar.DASHBOARD_EXTERNAL_BACKUP_OK,
    "warning": ar.DASHBOARD_EXTERNAL_BACKUP_WARNING,
    "missing": ar.DASHBOARD_EXTERNAL_BACKUP_MISSING,
}
_EXTERNAL_BACKUP_ROLES = {"ok": "success", "warning": "warning", "missing": "error"}

_REFRESH_INTERVAL_MS = 30_000
_TOP_ITEMS_LIMIT = 5
_BAR_STRETCH_TOTAL = 100


def _build_bar_row(label_text: str, value_text: str, fraction: float, accent: bool = False) -> QWidget:
    """One proportional horizontal bar: a name, a track+fill bar sized by
    layout stretch factors (not a fixed pixel width, so it stays correct
    at any container width), and the value. No QtCharts, no animation."""
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.addWidget(QLabel(label_text))

    track = QWidget()
    track.setProperty("variant", "barTrack")
    enable_styled_background(track)
    track.setFixedHeight(16)
    track_layout = QHBoxLayout(track)
    track_layout.setContentsMargins(0, 0, 0, 0)
    track_layout.setSpacing(0)

    fraction = max(0.0, min(1.0, fraction))
    fill_stretch = max(1, int(_BAR_STRETCH_TOTAL * fraction))
    remainder_stretch = max(0, _BAR_STRETCH_TOTAL - fill_stretch)
    fill = QWidget()
    fill.setProperty("variant", "barFillAccent" if accent else "barFill")
    enable_styled_background(fill)
    track_layout.addWidget(fill, fill_stretch)
    if remainder_stretch:
        track_layout.addStretch(remainder_stretch)
    layout.addWidget(track, 1)

    value_label = QLabel(value_text)
    layout.addWidget(value_label)
    return row


def _comparison_text_and_role(stat) -> "tuple[str, str]":
    if not stat.has_data:
        return ar.DASHBOARD_NO_COMPARISON_DATA, "subtitle"
    arrow = "▲" if stat.percent_change >= 0 else "▼"
    sign = "+" if stat.percent_change >= 0 else ""
    text = "{0} {1}{2:.0f}%".format(arrow, sign, stat.percent_change)
    return text, ("success" if stat.percent_change >= 0 else "error")


class _NewInvoiceTypeDialog(QDialog):
    """The "فاتورة بيع جديدة" chooser: تيك أواي starts a fresh takeaway
    order directly (same hand-off the Tables screen's own takeaway
    button uses); ترابيزة/بلايستيشن just navigate to the Tables/
    PlayStation screens, which already show live busy/free status and
    attach to an existing open bill or start a new one -- reusing that
    flow instead of rebuilding table/device picking here."""

    TAKEAWAY = "takeaway"
    TABLE = "table"
    PLAYSTATION = "playstation"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.choice = None
        self.setWindowTitle(ar.DASHBOARD_CHOOSE_ORDER_TYPE_TITLE)
        layout = QVBoxLayout(self)
        for label, choice in (
            (ar.DASHBOARD_TYPE_TAKEAWAY, self.TAKEAWAY),
            (ar.DASHBOARD_TYPE_TABLE, self.TABLE),
            (ar.DASHBOARD_TYPE_PLAYSTATION, self.PLAYSTATION),
        ):
            button = QPushButton(label)
            button.setProperty("variant", "primary")
            button.clicked.connect(lambda _c=False, ch=choice: self._on_choose(ch))
            layout.addWidget(button)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Cancel).setText(ar.GENERIC_CANCEL)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_choose(self, choice: str) -> None:
        self.choice = choice
        self.accept()


class DailyStatsScreen(QWidget):
    # Mirrors tables_screen.py's own signals -- MainWindow wires both to
    # the same handlers, so a takeaway/table/device started from here
    # behaves exactly like one started from the Tables/PlayStation screens.
    takeaway_requested = Signal(str)
    navigate_requested = Signal(str)
    # A card in the "الطلبات المفتوحة" section was tapped -- same contract
    # as TablesScreen/PlaystationScreen's own order_opened signal.
    order_opened = Signal(int)

    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._is_owner = permissions.view_reports(user["role"])
        self._selected_date = report_service.today_business_date(conn)

        self._timer = QTimer(self)
        self._timer.setInterval(_REFRESH_INTERVAL_MS)
        self._timer.timeout.connect(self.reload)

        self._build_ui()
        self.reload()

    # --- construction ----------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        title = QLabel(ar.DASHBOARD_TITLE)
        title.setProperty("role", "title")
        outer.addWidget(title)

        self._new_invoice_button = QPushButton(ar.DASHBOARD_NEW_INVOICE_BUTTON)
        self._new_invoice_button.setProperty("variant", "primary")
        self._new_invoice_button.clicked.connect(self._on_new_invoice)
        outer.addWidget(self._new_invoice_button)

        self._alerts_center = None
        if self._is_owner:
            self._alerts_center = AlertsCenter(self._conn)
            self._alerts_center.navigate_requested.connect(self.navigate_requested.emit)
            outer.addWidget(self._alerts_center)

        date_row = QHBoxLayout()
        self._prev_button = QPushButton(ar.DASHBOARD_PREV_DAY_BUTTON)
        self._prev_button.clicked.connect(self._on_prev_day)
        date_row.addWidget(self._prev_button)
        self._date_label = QLabel("")
        self._date_label.setProperty("role", "subtitle")
        date_row.addWidget(self._date_label)
        self._next_button = QPushButton(ar.DASHBOARD_NEXT_DAY_BUTTON)
        self._next_button.clicked.connect(self._on_next_day)
        date_row.addWidget(self._next_button)
        date_row.addStretch(1)
        outer.addLayout(date_row)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        scroll_area.setWidget(content)
        outer.addWidget(scroll_area, 1)

        self._tiles_row = QHBoxLayout()
        content_layout.addLayout(self._tiles_row)
        self._tile_net_sales = StatTile(ar.REPORTS_SUMMARY_NET_SALES)
        self._tile_invoice_count = StatTile(ar.REPORTS_SUMMARY_INVOICE_COUNT)
        self._tile_average_invoice = StatTile(ar.REPORTS_SUMMARY_AVERAGE_INVOICE)
        self._tile_discounts = StatTile(ar.REPORTS_SUMMARY_DISCOUNTS)
        self._tile_cash = StatTile(ar.PAYMENT_METHOD_CASH)
        self._tile_instapay = StatTile(ar.PAYMENT_METHOD_INSTAPAY)
        self._tile_credit = StatTile(ar.PAYMENT_METHOD_CREDIT)
        for tile in (
            self._tile_net_sales, self._tile_invoice_count, self._tile_average_invoice,
            self._tile_discounts, self._tile_cash, self._tile_instapay, self._tile_credit,
        ):
            self._tiles_row.addWidget(tile)

        self._owner_tiles_row = QHBoxLayout()
        content_layout.addLayout(self._owner_tiles_row)
        self._tile_expenses = StatTile(ar.REPORTS_SUMMARY_EXPENSES)
        self._tile_net_today = StatTile(ar.DASHBOARD_NET_TODAY_LABEL)
        self._tile_gross_profit = StatTile(ar.DASHBOARD_GROSS_PROFIT_TODAY_LABEL)
        self._tile_external_backup = StatTile(ar.DASHBOARD_EXTERNAL_BACKUP_LABEL)
        self._owner_tiles_row.addWidget(self._tile_expenses)
        self._owner_tiles_row.addWidget(self._tile_net_today)
        self._owner_tiles_row.addWidget(self._tile_gross_profit)
        self._owner_tiles_row.addWidget(self._tile_external_backup)
        self._owner_tiles_row.addStretch(1)
        self._tile_expenses.setVisible(self._is_owner)
        self._tile_net_today.setVisible(self._is_owner)
        self._tile_gross_profit.setVisible(self._is_owner)
        self._tile_external_backup.setVisible(self._is_owner)

        # Both roles: a quick operational pulse -- neither tile exposes
        # costs, so there is no permission gate here (see view_cost_data).
        self._pulse_tiles_row = QHBoxLayout()
        content_layout.addLayout(self._pulse_tiles_row)
        self._tile_cash_in_drawer = StatTile(ar.DASHBOARD_CASH_IN_DRAWER_LABEL)
        self._tile_low_stock = StatTile(ar.DASHBOARD_LOW_STOCK_LABEL)
        self._pulse_tiles_row.addWidget(self._tile_cash_in_drawer)
        self._pulse_tiles_row.addWidget(self._tile_low_stock)
        self._pulse_tiles_row.addStretch(1)

        self._tables_status_label = QLabel("")
        content_layout.addWidget(self._tables_status_label)

        self._open_orders_panel = OpenOrdersPanel(self._conn)
        self._open_orders_panel.order_opened.connect(self.order_opened.emit)
        content_layout.addWidget(self._open_orders_panel)

        # Everything below here is hidden in favor of one friendly
        # sentence when the day has no sales at all.
        self._charts_container = QWidget()
        charts_layout = QVBoxLayout(self._charts_container)
        charts_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(self._charts_container)

        hourly_title = QLabel(ar.DASHBOARD_HOURLY_SALES_TITLE)
        hourly_title.setProperty("role", "subtitle")
        charts_layout.addWidget(hourly_title)
        self._hourly_chart = HourlyBarChart()
        charts_layout.addWidget(self._hourly_chart)

        top_items_title = QLabel(ar.DASHBOARD_TOP_ITEMS_TITLE)
        top_items_title.setProperty("role", "subtitle")
        charts_layout.addWidget(top_items_title)
        self._top_items_layout = QVBoxLayout()
        charts_layout.addLayout(self._top_items_layout)

        category_title = QLabel(ar.DASHBOARD_CATEGORY_SPLIT_TITLE)
        category_title.setProperty("role", "subtitle")
        charts_layout.addWidget(category_title)
        self._category_layout = QVBoxLayout()
        charts_layout.addLayout(self._category_layout)

        ps_vs_cafe_title = QLabel(ar.DASHBOARD_PS_VS_CAFE_TITLE)
        ps_vs_cafe_title.setProperty("role", "subtitle")
        charts_layout.addWidget(ps_vs_cafe_title)
        self._ps_vs_cafe_layout = QVBoxLayout()
        charts_layout.addLayout(self._ps_vs_cafe_layout)

        comparison_row = QHBoxLayout()
        self._vs_yesterday_label = QLabel("")
        comparison_row.addWidget(self._vs_yesterday_label)
        self._vs_last_week_label = QLabel("")
        comparison_row.addWidget(self._vs_last_week_label)
        comparison_row.addStretch(1)
        charts_layout.addLayout(comparison_row)

        self._empty_state_label = QLabel(ar.DASHBOARD_EMPTY_STATE)
        self._empty_state_label.setWordWrap(True)
        self._empty_state_label.setVisible(False)
        content_layout.addWidget(self._empty_state_label)

        content_layout.addStretch(1)

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

    # --- live refresh -------------------------------------------------------

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 -- Qt override
        super().showEvent(event)
        self.reload()
        self._timer.start()

    def hideEvent(self, event: QHideEvent) -> None:  # noqa: N802 -- Qt override
        super().hideEvent(event)
        self._timer.stop()

    def _safe(self, fn):
        """Runs a tile's data lookup in isolation: one failing tile (e.g.
        a drawer/stock query hitting an unexpected schema state) must
        never take down the whole dashboard right after login -- it logs
        the error the same way the app's global crash handler would and
        the caller falls back to a placeholder instead of crashing."""
        try:
            return fn()
        except Exception:
            error_log.log_exception(*sys.exc_info())
            return None

    # --- new-invoice flow ----------------------------------------------

    def _on_new_invoice(self) -> None:
        dialog = _NewInvoiceTypeDialog(self)
        if dialog.exec_() != QDialog.Accepted:
            return
        if dialog.choice == _NewInvoiceTypeDialog.TAKEAWAY:
            self.takeaway_requested.emit("")
        elif dialog.choice == _NewInvoiceTypeDialog.TABLE:
            self.navigate_requested.emit("tables")
        elif dialog.choice == _NewInvoiceTypeDialog.PLAYSTATION:
            self.navigate_requested.emit("playstation")

    # --- date switcher (last 7 business days) -------------------------------

    def _on_prev_day(self) -> None:
        earliest = daily_stats_service.earliest_selectable_date(self._conn)
        if self._selected_date - timedelta(days=1) >= earliest:
            self._selected_date -= timedelta(days=1)
            self.reload()

    def _on_next_day(self) -> None:
        today = report_service.today_business_date(self._conn)
        if self._selected_date + timedelta(days=1) <= today:
            self._selected_date += timedelta(days=1)
            self.reload()

    # --- rendering -----------------------------------------------------

    def reload(self) -> None:
        if self._alerts_center is not None:
            self._safe(self._alerts_center.reload)
        today = report_service.today_business_date(self._conn)
        stats = daily_stats_service.build_daily_stats(self._conn, self._selected_date, today=today)
        report = stats.report

        self._date_label.setText(
            "{0} ({1})".format(ar.DASHBOARD_TODAY_BADGE, today.isoformat())
            if self._selected_date == today
            else self._selected_date.isoformat()
        )
        earliest = daily_stats_service.earliest_selectable_date(self._conn, today=today)
        self._prev_button.setEnabled(self._selected_date > earliest)
        self._next_button.setEnabled(self._selected_date < today)

        self._tile_net_sales.set_value(format_egp(report.net_sales_piasters))
        self._tile_invoice_count.set_value(str(report.invoice_count))
        self._tile_average_invoice.set_value(format_egp(report.average_invoice_piasters))
        self._tile_discounts.set_value(format_egp(report.discount_total_piasters))
        cash_stat = report.payment_methods.get("cash")
        instapay_stat = report.payment_methods.get("instapay")
        credit_stat = report.payment_methods.get("credit")
        self._tile_cash.set_value(format_egp(cash_stat.total_piasters if cash_stat else 0))
        self._tile_instapay.set_value(format_egp(instapay_stat.total_piasters if instapay_stat else 0))
        self._tile_credit.set_value(format_egp(credit_stat.total_piasters if credit_stat else 0))

        if self._is_owner:
            self._tile_expenses.set_value(format_egp(report.expenses_total_piasters))
            self._tile_net_today.set_value(format_egp(report.profit_piasters))
            self._tile_gross_profit.set_value(format_egp(report.gross_profit_piasters))
            self._refresh_external_backup_tile()

        cash_in_drawer = self._safe(lambda: drawer_service.expected_cash_piasters(self._conn))
        self._tile_cash_in_drawer.set_value(
            format_egp(cash_in_drawer) if isinstance(cash_in_drawer, int) else ar.DASHBOARD_DRAWER_NOT_OPENED
        )
        low_stock_count = self._safe(lambda: len(stock_items_repo.list_low_stock(self._conn)))
        self._tile_low_stock.set_value(str(low_stock_count) if low_stock_count is not None else "—")

        self._tables_status_label.setText(
            ar.DASHBOARD_TABLES_STATUS_LABEL.format(busy=stats.tables_busy_count, free=stats.tables_free_count)
        )

        is_empty = report.invoice_count == 0
        self._charts_container.setVisible(not is_empty)
        self._empty_state_label.setVisible(is_empty)
        if not is_empty:
            self._render_charts(report)

        vs_yesterday_text, vs_yesterday_role = _comparison_text_and_role(stats.vs_yesterday)
        self._vs_yesterday_label.setText("{0}: {1}".format(ar.DASHBOARD_VS_YESTERDAY_LABEL, vs_yesterday_text))
        self._vs_yesterday_label.setProperty("role", vs_yesterday_role)
        self._vs_yesterday_label.style().unpolish(self._vs_yesterday_label)
        self._vs_yesterday_label.style().polish(self._vs_yesterday_label)

        vs_last_week_text, vs_last_week_role = _comparison_text_and_role(stats.vs_last_week_same_weekday)
        self._vs_last_week_label.setText("{0}: {1}".format(ar.DASHBOARD_VS_LAST_WEEK_LABEL, vs_last_week_text))
        self._vs_last_week_label.setProperty("role", vs_last_week_role)
        self._vs_last_week_label.style().unpolish(self._vs_last_week_label)
        self._vs_last_week_label.style().polish(self._vs_last_week_label)

    def _refresh_external_backup_tile(self) -> None:
        def _status():
            values = settings_repo.get_all(self._conn)
            secondary_text = values.get("backup_folder_secondary") or ""
            secondary_dir = Path(secondary_text) if secondary_text else None
            warning_days = int(values.get("backup_warning_days") or "2")
            return backup_service.external_backup_status(self._conn, utc_now(), secondary_dir, warning_days)

        status = self._safe(_status) or "missing"
        self._tile_external_backup.set_value(
            _EXTERNAL_BACKUP_LABELS.get(status, status), role=_EXTERNAL_BACKUP_ROLES.get(status, "title")
        )

    def _render_charts(self, report) -> None:
        self._hourly_chart.set_values(
            report_service.sales_by_hour(self._conn, self._selected_date)
        )

        self._clear_layout(self._top_items_layout)
        top_items = report.top_items_by_qty[:_TOP_ITEMS_LIMIT]
        if not top_items:
            self._top_items_layout.addWidget(QLabel(ar.REPORTS_EMPTY_STATE))
        for item in top_items:
            self._top_items_layout.addWidget(
                QLabel("{0} — {1} — {2}".format(item.name, item.qty, format_egp(item.revenue_piasters)))
            )

        self._clear_layout(self._category_layout)
        category_total = sum(category.total_piasters for category in report.sales_by_category) or 1
        for category in report.sales_by_category:
            fraction = category.total_piasters / category_total
            self._category_layout.addWidget(
                _build_bar_row(category.category, format_egp(category.total_piasters), fraction)
            )

        self._clear_layout(self._ps_vs_cafe_layout)
        cafe_revenue = report.net_sales_piasters - report.ps_total_revenue_piasters
        combined = report.net_sales_piasters or 1
        self._ps_vs_cafe_layout.addWidget(
            _build_bar_row(
                ar.DASHBOARD_PS_REVENUE_LABEL, format_egp(report.ps_total_revenue_piasters),
                report.ps_total_revenue_piasters / combined, accent=True,
            )
        )
        self._ps_vs_cafe_layout.addWidget(
            _build_bar_row(ar.DASHBOARD_CAFE_REVENUE_LABEL, format_egp(cafe_revenue), cafe_revenue / combined)
        )
