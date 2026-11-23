"""Dev-time ONLY (Phase 11 review aid). Renders the main new Phase 11
screens to PNGs for manual review, under offscreen Qt against a
throwaway temp SQLite DB -- same technique as tools/preview_screens.py
and tools/render_phase10_previews.py, never real user data.

Usage:
    .venv\\Scripts\\python.exe tools\\render_phase11_previews.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from pathlib import Path

_work_dir = Path(tempfile.mkdtemp(prefix="derby_phase11_preview_"))
os.environ["DERBY_DATA_DIR"] = str(_work_dir / "appdata" / "Derby")
os.environ["DERBY_DOCS_DIR"] = str(_work_dir / "documents_derby" / "Derby")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "docs" / "ui"
sys.path.insert(0, str(PROJECT_ROOT))

from PySide2.QtCore import Qt  # noqa: E402
from PySide2.QtGui import QFont  # noqa: E402
from PySide2.QtWidgets import QApplication  # noqa: E402

from derby.core import audit_service  # noqa: E402
from derby.core.db import (  # noqa: E402
    categories_repo,
    products_repo,
    settings_repo,
    stock_items_repo,
    suppliers_repo,
    tables_repo,
    users_repo,
)
from derby.core.db.connection import connect  # noqa: E402
from derby.core.db.migrations import run_pending_migrations  # noqa: E402
from derby.core.theme.fonts import CAIRO_FAMILY, load_bundled_fonts  # noqa: E402
from derby.core.theme.stylesheet import build_stylesheet  # noqa: E402
from derby.core.utils.time_utils import utc_now  # noqa: E402
from derby.features.audit.audit_log_screen import AuditLogScreen  # noqa: E402
from derby.features.closing import closing_service  # noqa: E402
from derby.features.closing.backup_closing_panel import BackupClosingPanel  # noqa: E402
from derby.features.customers import customer_service  # noqa: E402
from derby.features.customers.customers_screen import CustomersScreen  # noqa: E402
from derby.features.dashboard.daily_stats_screen import DailyStatsScreen  # noqa: E402
from derby.features.inventory import stock_service  # noqa: E402
from derby.features.inventory.reorder_list_dialog import ReorderListDialog  # noqa: E402
from derby.features.pos import orders_service  # noqa: E402
from derby.features.shifts import shift_service  # noqa: E402
from derby.features.shifts.shifts_employees_screen import ShiftsEmployeesScreen  # noqa: E402


def _seed(conn, db_path: Path) -> dict:
    settings_repo.ensure_defaults(conn)
    settings_repo.set_value(conn, "cafe_name", "ديربي")

    owner_id = users_repo.create_user(conn, "محمد المالك", users_repo.ROLE_OWNER, "1111")
    users_repo.create_user(conn, "أحمد الكاشير", users_repo.ROLE_CASHIER, "2222")
    owner = users_repo.get_user(conn, owner_id)

    category_id = categories_repo.create_category(conn, "مشروبات ساخنة")
    coffee_id = products_repo.create_product(conn, category_id, "قهوة تركي", "", 2500)

    # A couple of paid sales (cash + instapay) for سجل العمليات and
    # الرئيسية to have something real to show.
    table = tables_repo.list_tables(conn)[0]
    order = orders_service.get_or_create_table_order(conn, table["id"], owner_id)
    orders_service.add_item(conn, order["id"], coffee_id, 2, [], None, owner_id)
    paid = orders_service.pay(conn, order["id"], "cash", owner)
    orders_service.void(conn, paid["id"], "عرض توضيحي", owner)

    # Customers + a credit sale, for العملاء and the shift/report figures.
    customer = customer_service.create_customer(conn, "عميل دائم", "01000000000", None, 5000, owner)
    order2 = orders_service.get_or_create_table_order(conn, table["id"], owner_id)
    orders_service.add_item(conn, order2["id"], coffee_id, 1, [], None, owner_id)
    customer_service.credit_sale(conn, order2["id"], customer["id"], owner)
    customer_service.create_customer(conn, "عميل آخر", "01000000001", None, None, owner)

    # A closed shift (for the shifts tab/report) and stock items (for
    # النسخ الاحتياطي's own backup + reorder list).
    shift = shift_service.open_shift(conn, owner, 10000)
    shift_service.close_shift(conn, shift, 12500, "عرض توضيحي", owner)

    supplier_id = suppliers_repo.create_supplier(conn, "مورد البن", None, None)
    stock_items_repo.create_stock_item(conn, "بن", "kg", min_qty=10)
    item = stock_items_repo.find_by_name(conn, "بن")
    stock_service.record_purchase(
        conn, supplier_id, date.today().isoformat(), [{"stock_item_id": item["id"], "qty": 3, "unit_cost_piasters": 10000}],
        True, owner_id,
    )

    closing_service.close_today_manually(conn, db_path, utc_now(), "ديربي", _work_dir / "backups", None, 30)

    audit_service.log(conn, "settings_changed", user=owner, summary_ar="عرض توضيحي لسجل العمليات")
    return {"owner_id": owner_id}


def _capture(widget, name: str, size=(1280, 900)) -> None:
    widget.resize(*size)
    widget.show()
    for _ in range(30):
        QApplication.processEvents()
    pixmap = widget.grab()
    path = OUT_DIR / "{0}.png".format(name)
    pixmap.save(str(path), "PNG")
    print("Saved {0}".format(path))


def main() -> int:
    app = QApplication.instance() or QApplication([])
    app.setLayoutDirection(Qt.RightToLeft)
    load_bundled_fonts()
    app.setFont(QFont(CAIRO_FAMILY, 10))
    app.setStyleSheet(build_stylesheet())

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    db_path = _work_dir / "preview.db"
    conn = connect(db_path)
    run_pending_migrations(conn)
    seed = _seed(conn, db_path)
    owner = users_repo.get_user(conn, seed["owner_id"])

    _capture(DailyStatsScreen(conn, owner), "phase11_home_alerts")
    _capture(AuditLogScreen(conn, owner), "phase11_audit_log")
    _capture(CustomersScreen(conn, owner), "phase11_customers")
    _capture(ShiftsEmployeesScreen(conn, owner), "phase11_shifts_employees")
    _capture(ReorderListDialog(conn), "phase11_reorder_list", size=(640, 440))
    _capture(BackupClosingPanel(conn, owner, db_path), "phase11_backups")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
