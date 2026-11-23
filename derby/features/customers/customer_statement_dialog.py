"""كشف حساب: every ledger entry for one customer with a running balance."""
from __future__ import annotations

import sqlite3

from PySide2.QtWidgets import QDialog, QTableWidget, QVBoxLayout

from derby.core.db import customer_ledger_repo, customers_repo
from derby.core.i18n import ar
from derby.core.theme.table_style import centered_item, configure_table, right_item
from derby.core.utils.money import format_egp
from derby.core.utils.time_utils import parse_utc_iso, to_cairo

_TYPE_LABELS = {
    "charge": ar.CUSTOMERS_LEDGER_TYPE_CHARGE,
    "payment": ar.CUSTOMERS_LEDGER_TYPE_PAYMENT,
    "adjustment": ar.CUSTOMERS_LEDGER_TYPE_ADJUSTMENT,
    "reversal": ar.CUSTOMERS_LEDGER_TYPE_REVERSAL,
}


class CustomerStatementDialog(QDialog):
    def __init__(self, conn: sqlite3.Connection, customer_id: int, parent=None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._customer_id = customer_id
        customer = customers_repo.get_customer(conn, customer_id)
        self.setWindowTitle(ar.CUSTOMERS_STATEMENT_TITLE.format(name=customer["name"] if customer else ""))
        self.resize(560, 420)
        layout = QVBoxLayout(self)
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(
            [
                ar.CUSTOMERS_STATEMENT_COLUMN_DATE, ar.CUSTOMERS_STATEMENT_COLUMN_TYPE,
                ar.CUSTOMERS_STATEMENT_COLUMN_AMOUNT, ar.CUSTOMERS_STATEMENT_COLUMN_BALANCE,
            ]
        )
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        configure_table(self._table, stretch_columns=(1,), fixed_widths={0: 110, 2: 110, 3: 110})
        layout.addWidget(self._table)
        self.reload()

    def reload(self) -> None:
        entries = customer_ledger_repo.list_for_customer(self._conn, self._customer_id)
        self._table.setRowCount(len(entries))
        running_balance = 0
        for row_index, entry in enumerate(entries):
            running_balance += entry["amount_piasters"]
            cairo_date = to_cairo(parse_utc_iso(entry["created_at_utc"])).strftime("%Y-%m-%d %H:%M")
            type_label = _TYPE_LABELS.get(entry["entry_type"], entry["entry_type"])
            makers = [centered_item, right_item, centered_item, centered_item]
            values = [cairo_date, type_label, format_egp(entry["amount_piasters"]), format_egp(running_balance)]
            for column, (value, make_item) in enumerate(zip(values, makers)):
                self._table.setItem(row_index, column, make_item(value))
