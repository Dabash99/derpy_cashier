"""إعدادات التنبيهات (owner only, inside الإعدادات): per-type toggles for
the الرئيسية alerts center, plus the thresholds they use.
"""
from __future__ import annotations

import sqlite3

from PySide2.QtWidgets import QCheckBox, QFormLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget

from derby.core import audit_service
from derby.core.db import settings_repo
from derby.core.i18n import ar

_TOGGLE_KEYS = (
    ("alert_ps_long_session_enabled", "جلسات بلايستيشن طويلة"),
    ("alert_customer_overdue_enabled", "عملاء متأخرون في السداد"),
    ("alert_backup_overdue_enabled", "تأخر النسخة الاحتياطية الخارجية"),
    ("alert_low_stock_enabled", "عناصر مخزون ناقصة"),
    ("alert_drawer_not_opened_enabled", "الدرج لم يُفتح اليوم"),
    ("alert_shift_left_open_enabled", "وردية مفتوحة من يوم سابق"),
    ("alert_unpaid_supplier_invoices_enabled", "فواتير موردين غير مدفوعة"),
)


class AlertsSettingsPanel(QWidget):
    def __init__(self, conn: sqlite3.Connection, user: sqlite3.Row, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = user
        self._checkboxes = {}
        self._build_ui()
        self.reload()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel(ar.ALERTS_SETTINGS_TITLE)
        title.setProperty("role", "title")
        layout.addWidget(title)

        for key, label in _TOGGLE_KEYS:
            checkbox = QCheckBox(label)
            self._checkboxes[key] = checkbox
            layout.addWidget(checkbox)

        # The form lives inside its OWN QWidget container, not a bare
        # QFormLayout handed straight to the outer QVBoxLayout -- see
        # shift_panel.py's comment on the same fix for the same bug
        # class (confirmed by tests/test_ui_sweep.py).
        form_host = QWidget()
        form = QFormLayout(form_host)
        self._ps_hours_input = QSpinBox()
        self._ps_hours_input.setRange(1, 24)
        form.addRow("ساعات جلسة البلايستيشن الطويلة", self._ps_hours_input)
        self._overdue_days_input = QSpinBox()
        self._overdue_days_input.setRange(1, 90)
        form.addRow("أيام تأخر العميل", self._overdue_days_input)
        self._supplier_days_input = QSpinBox()
        self._supplier_days_input.setRange(1, 90)
        form.addRow("أيام تأخر فاتورة المورد", self._supplier_days_input)
        layout.addWidget(form_host)

        save_button = QPushButton(ar.GENERIC_SAVE)
        save_button.clicked.connect(self._on_save)
        layout.addWidget(save_button)

    def reload(self) -> None:
        values = settings_repo.get_all(self._conn)
        for key, checkbox in self._checkboxes.items():
            checkbox.setChecked(values.get(key, "1") == "1")
        self._ps_hours_input.setValue(int(values.get("ps_long_session_alert_hours") or "6"))
        self._overdue_days_input.setValue(int(values.get("customer_overdue_days") or "14"))
        self._supplier_days_input.setValue(int(values.get("supplier_invoice_overdue_days") or "14"))

    def _on_save(self) -> None:
        for key, checkbox in self._checkboxes.items():
            settings_repo.set_value(self._conn, key, "1" if checkbox.isChecked() else "0")
        settings_repo.set_value(self._conn, "ps_long_session_alert_hours", str(self._ps_hours_input.value()))
        settings_repo.set_value(self._conn, "customer_overdue_days", str(self._overdue_days_input.value()))
        settings_repo.set_value(self._conn, "supplier_invoice_overdue_days", str(self._supplier_days_input.value()))
        audit_service.log(
            self._conn, "alert_setting_changed", user=self._user, entity_type="settings",
            summary_ar="تعديل إعدادات تنبيهات الرئيسية",
        )
