"""Dev-time ONLY visual check (Part A4). Builds each screen/dialog with
SYNTHETIC data (a throwaway temp SQLite DB seeded with fake Arabic rows
via the real repo/service layer -- same technique the GUI test suite
already uses, never real user data) under offscreen Qt, and saves a PNG
of each via widget.grab() to build/preview/ (gitignored). Not part of
the shipped app; never imports anything the shipped app doesn't already
use at runtime (no QtSvg here -- PNGs only).

Every path is explicit: a tmp directory this script creates itself, via
DERBY_DATA_DIR/DERBY_DOCS_DIR -- never %APPDATA%, never Documents\\Derby.

Usage:
    .venv\\Scripts\\python.exe tools\\preview_screens.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

_work_dir = Path(tempfile.mkdtemp(prefix="derby_preview_"))
os.environ["DERBY_DATA_DIR"] = str(_work_dir / "appdata" / "Derby")
os.environ["DERBY_DOCS_DIR"] = str(_work_dir / "documents_derby" / "Derby")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "build" / "preview"
sys.path.insert(0, str(PROJECT_ROOT))

from PySide2.QtWidgets import QApplication  # noqa: E402

from derby.core.db import (  # noqa: E402
    addons_repo,
    categories_repo,
    expense_categories_repo,
    expenses_repo,
    orders_repo,
    products_repo,
    ps_devices_repo,
    settings_repo,
    tables_repo,
    users_repo,
)
from derby.core.db.connection import connect  # noqa: E402
from derby.core.db.migrations import run_pending_migrations  # noqa: E402
from derby.core.theme.fonts import load_bundled_fonts  # noqa: E402
from derby.core.theme.stylesheet import build_stylesheet  # noqa: E402
from derby.features.auth.login_screen import LoginScreen  # noqa: E402
from derby.features.auth.setup_screen import SetupScreen  # noqa: E402
from derby.features.expenses.expenses_screen import ExpensesScreen  # noqa: E402
from derby.features.expenses.expenses_service import today_business_date  # noqa: E402
from derby.features.menu.menu_screen import MenuScreen  # noqa: E402
from derby.features.playstation import ps_service  # noqa: E402
from derby.features.playstation.playstation_screen import PlaystationScreen  # noqa: E402
from derby.features.pos.addon_dialog import AddonDialog  # noqa: E402
from derby.features.pos.discount_dialog import DiscountDialog  # noqa: E402
from derby.features.pos.invoice_dialog import InvoiceDialog  # noqa: E402
from derby.features.pos.payment_dialog import PaymentDialog  # noqa: E402
from derby.features.pos.pos_screen import PosScreen  # noqa: E402
from derby.features.pos.sales_log_screen import SalesLogScreen  # noqa: E402
from derby.features.reports.reports_screen import ReportsScreen  # noqa: E402
from derby.features.settings.settings_screen import SettingsScreen  # noqa: E402
from derby.features.shell.idle_filter import IdleTimer  # noqa: E402
from derby.features.shell.main_window import MainWindow  # noqa: E402
from derby.features.tables.tables_screen import TablesScreen  # noqa: E402

FAILURES = []
ATTEMPTED = []


def _seed(conn) -> dict:
    settings_repo.ensure_defaults(conn)
    settings_repo.set_value(conn, "cafe_name", "ديربي")

    owner_id = users_repo.create_user(conn, "محمد المالك", users_repo.ROLE_OWNER, "1111")
    cashier_id = users_repo.create_user(conn, "أحمد الكاشير", users_repo.ROLE_CASHIER, "2222")

    drinks_id = categories_repo.create_category(conn, "مشروبات ساخنة")
    categories_repo.create_category(conn, "مشروبات باردة")
    coffee_id = products_repo.create_product(conn, drinks_id, "قهوة تركي", "", 2500)
    products_repo.create_product(conn, drinks_id, "كابتشينو", "", 3500)
    products_repo.create_product(conn, drinks_id, "اسم منتج طويل جدًا جدًا يتجاوز العرض المتاح للبطاقة", "", 4000)
    addon_group = addons_repo.create_group(conn, "الحجم")
    addons_repo.create_addon(conn, addon_group, "كبير", 500)
    addons_repo.set_product_addon_groups(conn, coffee_id, [addon_group])

    # A busy table: open an order on the first table (tables themselves
    # are already seeded by migrations).
    table = tables_repo.list_tables(conn, active_only=True)[0]
    busy_order_id = orders_repo.create_order(conn, table["id"], cashier_id)
    orders_repo.create_order_item(conn, busy_order_id, "product", coffee_id, "قهوة تركي", 2500, 2, 5000)
    orders_repo.update_order_totals(conn, busy_order_id, 5000, 0, 5000)

    # A paid order, for sales log / reports / invoice preview.
    paid_order_id = orders_repo.create_order(conn, None, cashier_id)
    orders_repo.create_order_item(conn, paid_order_id, "product", coffee_id, "قهوة تركي", 2500, 1, 2500)
    orders_repo.update_order_totals(conn, paid_order_id, 2500, 0, 2500)
    invoice_no = orders_repo.next_invoice_no(conn)
    today = today_business_date(conn).isoformat()
    orders_repo.mark_order_paid(conn, paid_order_id, invoice_no, owner_id, today, "cash")

    # A running PlayStation session.
    device = ps_devices_repo.list_devices(conn)[0]
    ps_devices_repo.set_rates(conn, device["id"], 4000, 6000)
    ps_service.start_session(conn, device["id"], "single", owner_id)

    expense_category = expense_categories_repo.list_categories(conn)[0]
    expenses_repo.create_expense(conn, expense_category["id"], 15000, today, "فاتورة كهرباء", owner_id)

    return {
        "owner_id": owner_id,
        "cashier_id": cashier_id,
        "paid_order_id": paid_order_id,
        "busy_order_id": busy_order_id,
        "table_id": table["id"],
        "coffee_id": coffee_id,
    }


def _save(widget, name: str, size=(1100, 720)) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    widget.resize(*size)
    widget.show()
    app = QApplication.instance()
    for _ in range(50):
        app.processEvents()
    widget.repaint()
    for _ in range(20):
        app.processEvents()
    pixmap = widget.grab()
    path = OUT_DIR / "{0}.png".format(name)
    pixmap.save(str(path), "PNG")
    print("wrote {0} ({1}x{2})".format(path.relative_to(PROJECT_ROOT), pixmap.width(), pixmap.height()))
    widget.close()


def _try(label: str, build_fn) -> None:
    ATTEMPTED.append(label)
    try:
        widget = build_fn()
        if widget is not None:
            _save(widget, label)
    except Exception:
        FAILURES.append(label)
        print("FAILED: {0}".format(label))
        traceback.print_exc()


def _try_shell_chrome(label_prefix: str, conn, user, db_path) -> None:
    """MainWindow's own widget.grab()/render() silently drops the header
    and inactive sidebar buttons' content under the offscreen platform --
    confirmed by grabbing each sub-widget directly, which renders
    correctly every time; this looks like an offscreen-compositor
    limitation with a QMainWindow that owns a QStackedWidget holding many
    large sibling screens, not an application bug (every screen's own
    content, including the active sidebar item, renders fine). Preview
    the header and sidebar directly instead of the whole window."""
    ATTEMPTED.append(label_prefix)
    try:
        app = QApplication.instance()
        mw = MainWindow(conn, user, IdleTimer(), db_path)
        mw.resize(1100, 720)
        mw.show()
        for _ in range(30):
            app.processEvents()
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        for part_name, part_widget in (("header", mw._header), ("sidebar", mw._sidebar)):
            pixmap = part_widget.grab()
            path = OUT_DIR / "{0}_{1}.png".format(label_prefix, part_name)
            pixmap.save(str(path), "PNG")
            print("wrote {0} ({1}x{2})".format(path.relative_to(PROJECT_ROOT), pixmap.width(), pixmap.height()))
        mw.close()
    except Exception:
        FAILURES.append(label_prefix)
        print("FAILED: {0}".format(label_prefix))
        traceback.print_exc()


def main() -> int:
    app = QApplication.instance() or QApplication([])
    load_bundled_fonts()
    app.setStyleSheet(build_stylesheet())

    db_path = _work_dir / "preview.db"
    conn = connect(db_path)
    run_pending_migrations(conn)
    ids = _seed(conn)
    owner = users_repo.get_user(conn, ids["owner_id"])
    cashier = users_repo.get_user(conn, ids["cashier_id"])

    # Empty-db setup screen (first run) uses its own connection.
    empty_db_path = _work_dir / "empty.db"
    empty_conn = connect(empty_db_path)
    run_pending_migrations(empty_conn)
    settings_repo.ensure_defaults(empty_conn)
    _try("auth_setup_screen", lambda: SetupScreen(empty_conn))

    _try("auth_login_screen", lambda: LoginScreen(conn))
    _try_shell_chrome("shell_owner", conn, owner, db_path)
    _try_shell_chrome("shell_cashier", conn, cashier, db_path)
    _try("pos_screen", lambda: PosScreen(conn, cashier))
    _try("tables_screen", lambda: TablesScreen(conn, owner))
    _try("playstation_screen", lambda: PlaystationScreen(conn, owner))
    _try("menu_screen", lambda: MenuScreen(conn, owner["id"]))
    _try("expenses_screen", lambda: ExpensesScreen(conn, owner))
    _try("reports_screen", lambda: ReportsScreen(conn, owner))
    _try("sales_log_screen", lambda: SalesLogScreen(conn, owner))
    _try("settings_screen", lambda: SettingsScreen(conn, owner, db_path))
    _try("invoice_dialog", lambda: InvoiceDialog(conn, ids["paid_order_id"], is_copy=False))
    _try("payment_dialog", lambda: PaymentDialog(conn, orders_repo.get_order(conn, ids["paid_order_id"]), owner))
    _try("discount_dialog", lambda: DiscountDialog(conn, ids["busy_order_id"], owner))
    _try("addon_dialog", lambda: AddonDialog(conn, ids["coffee_id"], "قهوة تركي"))

    conn.close()
    empty_conn.close()

    print()
    print("Screens attempted: {0}, failed: {1}".format(len(ATTEMPTED), len(FAILURES)))
    if FAILURES:
        print("Failed: {0}".format(", ".join(FAILURES)))
    print("Preview dir: {0}".format(OUT_DIR))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
