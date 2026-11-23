"""سجل الورديات (owner only): every shift, open or closed."""
from __future__ import annotations

import sqlite3

from PySide2.QtWidgets import QTableWidget, QVBoxLayout, QWidget

from derby.core.db import shifts_repo, users_repo
from derby.core.i18n import ar
from derby.core.theme.table_style import centered_item, configure_table, right_item
from derby.core.utils.money import format_egp
from derby.core.utils.time_utils import parse_utc_iso, to_cairo


class ShiftsHistoryPanel(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            [
                ar.SHIFTS_HISTORY_COLUMN_USER, ar.SHIFTS_HISTORY_COLUMN_OPENED, ar.SHIFTS_HISTORY_COLUMN_CLOSED,
                ar.SHIFTS_HISTORY_COLUMN_DIFFERENCE, ar.SHIFTS_HISTORY_COLUMN_STATUS,
            ]
        )
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        configure_table(self._table, stretch_columns=(0,), fixed_widths={1: 140, 2: 140, 3: 90, 4: 80})
        layout.addWidget(self._table)

    def reload(self) -> None:
        rows = shifts_repo.list_shifts(self._conn)
        self._table.setRowCount(len(rows))
        for row_index, shift in enumerate(rows):
            user = users_repo.get_user(self._conn, shift["user_id"])
            opened = to_cairo(parse_utc_iso(shift["opened_at_utc"])).strftime("%Y-%m-%d %H:%M")
            closed = to_cairo(parse_utc_iso(shift["closed_at_utc"])).strftime("%Y-%m-%d %H:%M") if shift["closed_at_utc"] else ""
            difference = format_egp(shift["difference_piasters"]) if shift["difference_piasters"] is not None else ""
            status = ar.SHIFTS_STATUS_OPEN if shift["status"] == "open" else ar.SHIFTS_STATUS_CLOSED
            makers = [right_item, centered_item, centered_item, centered_item, centered_item]
            for column, (value, make_item) in enumerate(
                zip([user["name"] if user else "", opened, closed, difference, status], makers)
            ):
                self._table.setItem(row_index, column, make_item(value))
