"""The Expenses screen (owner only): a month/category-filtered list,
add/void-replace/view-receipt actions, and two management tabs
(categories, recurring templates). Opening the screen checks for any
recurring template due this month and offers the confirm/skip prompt.
"""
from __future__ import annotations

import calendar
import sqlite3
from datetime import date

from PySide2.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from derby.core.db import expense_categories_repo, expenses_repo
from derby.core.i18n import ar
from derby.core.theme.tab_bar import configure_tab_widget
from derby.core.theme.table_style import centered_item, configure_table, right_item
from derby.core.utils.money import format_egp, piasters_to_plain_text
from derby.core.utils.screen_refresh import RefreshOnChangeMixin
from derby.features.expenses import expenses_service
from derby.features.expenses.expense_categories_panel import ExpenseCategoriesPanel
from derby.features.expenses.expense_dialog import ExpenseDialog
from derby.features.expenses.receipt_viewer_dialog import ReceiptViewerDialog
from derby.features.expenses.recurring_due_dialog import RecurringDueDialog
from derby.features.expenses.recurring_management_panel import RecurringManagementPanel
from derby.features.reports.export_panel import ExportPanel
from derby.features.reports.export_service import export_expenses_csv, export_expenses_xlsx

_ALL_CATEGORIES = None


def _month_bounds(year_month: str):
    year, month = (int(part) for part in year_month.split("-"))
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1).isoformat(), date(year, month, last_day).isoformat()


class ExpensesScreen(RefreshOnChangeMixin, QWidget):
    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._rows_by_table_row = []
        self._build_ui()
        self.reload()
        self._init_refresh_on_change()
        self.check_recurring_due()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel(ar.EXPENSES_TITLE)
        title.setProperty("role", "title")
        layout.addWidget(title)

        tabs = QTabWidget()
        configure_tab_widget(tabs)
        tabs.addTab(self._build_list_tab(), ar.EXPENSES_TITLE)
        self._categories_panel = ExpenseCategoriesPanel(self._conn, self._user)
        self._categories_panel.categories_changed.connect(self.reload)
        tabs.addTab(self._categories_panel, ar.EXPENSE_CATEGORIES_TITLE)
        self._recurring_panel = RecurringManagementPanel(self._conn, self._user)
        tabs.addTab(self._recurring_panel, ar.RECURRING_TITLE)
        layout.addWidget(tabs)

    def _build_list_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        filters_row = QHBoxLayout()
        filters_row.addWidget(QLabel(ar.EXPENSES_MONTH_LABEL))
        self._month_input = QLineEdit(expenses_service.today_business_date(self._conn).strftime("%Y-%m"))
        self._month_input.editingFinished.connect(self.reload)
        filters_row.addWidget(self._month_input)

        filters_row.addWidget(QLabel(ar.EXPENSES_CATEGORY_FILTER_LABEL))
        self._category_filter = QComboBox()
        self._category_filter.currentIndexChanged.connect(self.reload)
        filters_row.addWidget(self._category_filter)
        layout.addLayout(filters_row)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            [
                ar.EXPENSES_COLUMN_DATE, ar.EXPENSES_COLUMN_CATEGORY, ar.EXPENSES_COLUMN_DESCRIPTION,
                ar.EXPENSES_COLUMN_AMOUNT, ar.EXPENSES_COLUMN_RECEIPT, ar.EXPENSES_COLUMN_STATUS,
            ]
        )
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        configure_table(
            self._table,
            stretch_columns=(1, 2),  # category, description
            fixed_widths={0: 100, 3: 110, 4: 90, 5: 90},
        )
        layout.addWidget(self._table)

        actions_row = QHBoxLayout()
        add_button = QPushButton(ar.EXPENSES_ADD_BUTTON)
        add_button.clicked.connect(self._on_add)
        actions_row.addWidget(add_button)
        void_replace_button = QPushButton(ar.EXPENSES_VOID_REPLACE_BUTTON)
        void_replace_button.clicked.connect(self._on_void_replace)
        actions_row.addWidget(void_replace_button)
        view_receipt_button = QPushButton(ar.EXPENSES_VIEW_RECEIPT_BUTTON)
        view_receipt_button.clicked.connect(self._on_view_receipt)
        actions_row.addWidget(view_receipt_button)
        recurring_button = QPushButton(ar.EXPENSES_RECURRING_BUTTON)
        recurring_button.clicked.connect(lambda: self.check_recurring_due(force=True))
        actions_row.addWidget(recurring_button)
        layout.addLayout(actions_row)

        self._totals_label = QLabel("")
        self._totals_label.setWordWrap(True)
        layout.addWidget(self._totals_label)

        self._export_panel = ExportPanel(lambda: "مصروفات_{0}".format(self._month_input.text().strip()))
        self._export_panel.set_exporters(csv_fn=self._export_csv, xlsx_fn=self._export_xlsx)
        layout.addWidget(self._export_panel)

        return tab

    # --- data ----------------------------------------------------------

    def _selected_category_id(self):
        return self._category_filter.currentData()

    def reload(self) -> None:
        previously_selected = self._category_filter.currentData() if self._category_filter.count() else _ALL_CATEGORIES
        self._category_filter.blockSignals(True)
        self._category_filter.clear()
        self._category_filter.addItem(ar.SALES_LOG_FILTER_ALL, _ALL_CATEGORIES)
        for category in expense_categories_repo.list_categories(self._conn):
            self._category_filter.addItem(category["name"], category["id"])
        restore_index = self._category_filter.findData(previously_selected)
        self._category_filter.setCurrentIndex(restore_index if restore_index >= 0 else 0)
        self._category_filter.blockSignals(False)

        try:
            start_date, end_date = _month_bounds(self._month_input.text().strip())
        except ValueError:
            return

        rows = expenses_repo.list_expenses(self._conn, start_date=start_date, end_date=end_date)
        category_id = self._selected_category_id()
        if category_id is not None:
            rows = [row for row in rows if row["category_id"] == category_id]

        self._rows_by_table_row = rows
        self._table.setRowCount(len(rows))
        category_name_by_id = {c["id"]: c["name"] for c in expense_categories_repo.list_categories(self._conn)}
        for row_index, expense in enumerate(rows):
            self._populate_row(row_index, expense, category_name_by_id)

        self._update_totals(start_date, end_date, category_name_by_id)

    def _populate_row(self, row_index: int, expense: sqlite3.Row, category_name_by_id) -> None:
        values = [
            expense["expense_date"],
            category_name_by_id.get(expense["category_id"], ""),
            expense["description"] or "",
            piasters_to_plain_text(expense["amount_piasters"]),
            ar.EXPENSES_RECEIPT_HAS_ONE if expense["receipt_file"] else "",
            ar.EXPENSES_STATUS_VOID if expense["status"] == "void" else ar.EXPENSES_STATUS_ACTIVE,
        ]
        makers = [centered_item, right_item, right_item, centered_item, centered_item, centered_item]
        for column, (value, make_item) in enumerate(zip(values, makers)):
            self._table.setItem(row_index, column, make_item(value))

    def _update_totals(self, start_date: str, end_date: str, category_name_by_id) -> None:
        active_rows = expenses_repo.list_expenses(self._conn, start_date=start_date, end_date=end_date, status="active")
        month_total = sum(row["amount_piasters"] for row in active_rows)
        self._totals_label.setText(ar.EXPENSES_MONTH_TOTAL_LABEL.format(total=format_egp(month_total)))

    def _selected_expense(self):
        row = self._table.currentRow()
        if row < 0 or row >= len(self._rows_by_table_row):
            return None
        return self._rows_by_table_row[row]

    # --- actions ---------------------------------------------------------

    def _on_add(self) -> None:
        dialog = ExpenseDialog(self._conn, self._user, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self.reload()

    def _on_void_replace(self) -> None:
        expense = self._selected_expense()
        if expense is None or expense["status"] != "active":
            return
        dialog = ExpenseDialog(self._conn, self._user, existing_expense=expense, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self.reload()

    def _on_view_receipt(self) -> None:
        expense = self._selected_expense()
        if expense is None:
            return
        ReceiptViewerDialog(expense["receipt_file"], parent=self).exec_()

    def check_recurring_due(self, force: bool = False) -> None:
        today = expenses_service.today_business_date(self._conn)
        due = expenses_service.due_templates_for_month(self._conn, today)
        if due or force:
            RecurringDueDialog(self._conn, self._user, today, parent=self).exec_()
            self.reload()

    # --- export ------------------------------------------------------------

    def _export_csv(self, path) -> None:
        category_name_by_id = {c["id"]: c["name"] for c in expense_categories_repo.list_categories(self._conn)}
        export_expenses_csv(self._rows_by_table_row, category_name_by_id, path)

    def _export_xlsx(self, path) -> None:
        category_name_by_id = {c["id"]: c["name"] for c in expense_categories_repo.list_categories(self._conn)}
        export_expenses_xlsx(self._rows_by_table_row, category_name_by_id, path)
