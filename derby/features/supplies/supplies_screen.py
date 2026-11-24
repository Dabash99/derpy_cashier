"""The supplies (shopping list) screen: quick-add row, a filtered/searched
list of items (urgent first), and a WhatsApp/clipboard hand-off for the
still-needed list -- not a stock/inventory system.
"""
from __future__ import annotations

import sqlite3

from PySide2.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from derby.core.db import settings_repo, supplies_repo, users_repo
from derby.core.i18n import ar
from derby.core.integrations import whatsapp
from derby.core.theme.styled import enable_styled_background
from derby.core.utils.money import format_egp
from derby.core.utils.screen_refresh import RefreshOnChangeMixin
from derby.core.utils.time_utils import parse_utc_iso, to_cairo
from derby.features.auth import permissions
from derby.features.supplies import supplies_service
from derby.features.supplies.exceptions import SupplyNameRequiredError
from derby.features.supplies.supply_dialogs import ConvertToExpenseDialog, SupplyEditDialog

_FILTER_NEEDED = "needed"
_FILTER_BOUGHT = "bought"
_FILTER_ALL = "all"


def _user_name(conn: sqlite3.Connection, user_id) -> str:
    if not user_id:
        return ""
    user = users_repo.get_user(conn, user_id)
    return user["name"] if user is not None else ""


class SuppliesScreen(RefreshOnChangeMixin, QWidget):
    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._build_ui()
        self.reload()
        self._init_refresh_on_change()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel(ar.SUPPLIES_TITLE)
        title.setProperty("role", "title")
        layout.addWidget(title)

        quick_add_row = QHBoxLayout()
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText(ar.SUPPLIES_NAME_PLACEHOLDER)
        self._name_input.returnPressed.connect(self._on_add)
        quick_add_row.addWidget(self._name_input, 2)
        self._quantity_input = QLineEdit()
        self._quantity_input.setPlaceholderText(ar.SUPPLIES_QUANTITY_PLACEHOLDER)
        self._quantity_input.returnPressed.connect(self._on_add)
        quick_add_row.addWidget(self._quantity_input, 1)
        self._priority_input = QComboBox()
        self._priority_input.addItem(ar.SUPPLIES_PRIORITY_NORMAL, supplies_service.PRIORITY_NORMAL)
        self._priority_input.addItem(ar.SUPPLIES_PRIORITY_URGENT, supplies_service.PRIORITY_URGENT)
        quick_add_row.addWidget(self._priority_input)
        add_button = QPushButton(ar.SUPPLIES_ADD_BUTTON)
        add_button.setProperty("variant", "primary")
        add_button.clicked.connect(self._on_add)
        quick_add_row.addWidget(add_button)
        layout.addLayout(quick_add_row)

        filters_row = QHBoxLayout()
        self._filter_input = QComboBox()
        self._filter_input.addItem(ar.SUPPLIES_FILTER_NEEDED, _FILTER_NEEDED)
        self._filter_input.addItem(ar.SUPPLIES_FILTER_BOUGHT, _FILTER_BOUGHT)
        self._filter_input.addItem(ar.SUPPLIES_FILTER_ALL, _FILTER_ALL)
        self._filter_input.currentIndexChanged.connect(self.reload)
        filters_row.addWidget(self._filter_input)
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(ar.SUPPLIES_SEARCH_PLACEHOLDER)
        self._search_input.textChanged.connect(self.reload)
        filters_row.addWidget(self._search_input, 1)
        layout.addLayout(filters_row)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        self._rows_host = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_host)
        scroll_area.setWidget(self._rows_host)
        layout.addWidget(scroll_area)

        actions_row = QHBoxLayout()
        copy_button = QPushButton(ar.SUPPLIES_COPY_LIST_BUTTON)
        copy_button.clicked.connect(self._on_copy_list)
        actions_row.addWidget(copy_button)
        whatsapp_button = QPushButton(ar.SUPPLIES_SEND_WHATSAPP_BUTTON)
        whatsapp_button.clicked.connect(self._on_send_whatsapp)
        actions_row.addWidget(whatsapp_button)
        layout.addLayout(actions_row)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

    # --- listing ---------------------------------------------------------

    def reload(self) -> None:
        status = self._filter_input.currentData()
        supplies = supplies_service.list_for_display(self._conn, status=None if status == _FILTER_ALL else status)
        search_text = self._search_input.text().strip()
        if search_text:
            supplies = [s for s in supplies if search_text in s["name"]]

        self._clear_layout(self._rows_layout)
        if not supplies:
            empty_label = QLabel(ar.SUPPLIES_EMPTY_STATE)
            empty_label.setWordWrap(True)
            self._rows_layout.addWidget(empty_label)
        for supply in supplies:
            self._rows_layout.addWidget(self._build_row(supply))
        self._rows_layout.addStretch(1)

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

    def _build_row(self, supply: sqlite3.Row) -> QWidget:
        row = QWidget()
        row.setProperty("variant", "card")
        enable_styled_background(row)
        outer = QVBoxLayout(row)

        header_row = QHBoxLayout()
        title_text = supply["name"]
        if supply["quantity_note"]:
            title_text = "{0} — {1}".format(title_text, supply["quantity_note"])
        name_label = QLabel(title_text)
        name_label.setProperty("role", "title")
        header_row.addWidget(name_label)
        header_row.addStretch(1)
        if supply["priority"] == supplies_service.PRIORITY_URGENT:
            priority_label = QLabel(ar.SUPPLIES_PRIORITY_URGENT)
            priority_label.setProperty("variant", "badge")
            header_row.addWidget(priority_label)
        outer.addLayout(header_row)

        if supply["note"]:
            outer.addWidget(QLabel(supply["note"]))

        added_cairo = to_cairo(parse_utc_iso(supply["added_at_utc"]))
        info_label = QLabel(
            ar.SUPPLIES_ADDED_BY_LABEL.format(
                name=_user_name(self._conn, supply["added_by"]), time=added_cairo.strftime("%Y-%m-%d %H:%M")
            )
        )
        info_label.setProperty("role", "subtitle")
        outer.addWidget(info_label)

        buttons_row = QHBoxLayout()
        if supply["status"] == supplies_service.STATUS_NEEDED:
            bought_button = QPushButton(ar.SUPPLIES_MARK_BOUGHT_BUTTON)
            bought_button.setProperty("variant", "primary")
            bought_button.clicked.connect(lambda: self._on_mark_bought(supply["id"]))
            buttons_row.addWidget(bought_button)
            edit_button = QPushButton(ar.SUPPLIES_EDIT_BUTTON)
            edit_button.clicked.connect(lambda: self._on_edit(supply["id"]))
            buttons_row.addWidget(edit_button)
            cancel_button = QPushButton(ar.SUPPLIES_CANCEL_BUTTON)
            cancel_button.setProperty("danger", "true")
            cancel_button.clicked.connect(lambda: self._on_cancel(supply["id"]))
            buttons_row.addWidget(cancel_button)
        elif supply["status"] == supplies_service.STATUS_BOUGHT:
            bought_cairo = to_cairo(parse_utc_iso(supply["bought_at_utc"])) if supply["bought_at_utc"] else None
            bought_label = QLabel(
                ar.SUPPLIES_BOUGHT_BY_LABEL.format(
                    name=_user_name(self._conn, supply["bought_by"]),
                    time=bought_cairo.strftime("%Y-%m-%d %H:%M") if bought_cairo else "",
                )
            )
            buttons_row.addWidget(bought_label)
            buttons_row.addStretch(1)
            if supply["expense_id"]:
                buttons_row.addWidget(QLabel("{0} — {1}".format(ar.SUPPLIES_ALREADY_CONVERTED_LABEL, format_egp(supply["cost_piasters"] or 0))))
            elif permissions.manage_supplies_costs(self._user["role"]):
                convert_button = QPushButton(ar.SUPPLIES_CONVERT_TO_EXPENSE_BUTTON)
                convert_button.clicked.connect(lambda: self._on_convert(supply["id"]))
                buttons_row.addWidget(convert_button)
        outer.addLayout(buttons_row)

        return row

    # --- actions ----------------------------------------------------------

    def _on_add(self) -> None:
        try:
            supplies_service.add_supply(
                self._conn, self._name_input.text(), self._quantity_input.text(),
                self._priority_input.currentData(), None, self._user["id"],
            )
        except SupplyNameRequiredError:
            self._status_label.setText(ar.SUPPLIES_ERROR_NAME_REQUIRED)
            return
        self._name_input.clear()
        self._quantity_input.clear()
        self._priority_input.setCurrentIndex(0)
        self._status_label.setText("")
        self.reload()

    def _on_mark_bought(self, supply_id: int) -> None:
        supplies_service.mark_bought(self._conn, supply_id, self._user["id"])
        self.reload()

    def _on_edit(self, supply_id: int) -> None:
        supply = supplies_repo.get_supply(self._conn, supply_id)
        if supply is None:
            return
        dialog = SupplyEditDialog(self._conn, supply, self._user, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self.reload()

    def _on_cancel(self, supply_id: int) -> None:
        confirmed = QMessageBox.question(self, ar.SUPPLIES_CANCEL_CONFIRM_TITLE, ar.SUPPLIES_CANCEL_CONFIRM_MESSAGE)
        if confirmed != QMessageBox.Yes:
            return
        supplies_service.cancel_supply(self._conn, supply_id, self._user["id"])
        self.reload()

    def _on_convert(self, supply_id: int) -> None:
        supply = supplies_repo.get_supply(self._conn, supply_id)
        if supply is None:
            return
        dialog = ConvertToExpenseDialog(self._conn, supply, self._user, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            self.reload()

    def _on_copy_list(self) -> None:
        text = supplies_service.copy_list_as_text(self._conn)
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
        self._status_label.setText(ar.SUPPLIES_COPIED_MESSAGE)

    def _on_send_whatsapp(self) -> None:
        text = supplies_service.copy_list_as_text(self._conn)
        method = settings_repo.get(self._conn, "whatsapp_method", whatsapp.METHOD_DESKTOP) or whatsapp.METHOD_DESKTOP
        number = settings_repo.get(self._conn, "whatsapp_number", "") or ""
        result = whatsapp.open_report(method, number, text)
        self._status_label.setText(result.message)
