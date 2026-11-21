"""Dev-time ONLY (Phase 10 review aid). Renders the new Home screen (with
sample open orders) and the redesigned cashier product grid to PNGs for
manual review, under offscreen Qt against a throwaway temp SQLite DB --
same technique as tools/preview_screens.py, never real user data.

Usage:
    .venv\\Scripts\\python.exe tools\\render_phase10_previews.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_work_dir = Path(tempfile.mkdtemp(prefix="derby_phase10_preview_"))
os.environ["DERBY_DATA_DIR"] = str(_work_dir / "appdata" / "Derby")
os.environ["DERBY_DOCS_DIR"] = str(_work_dir / "documents_derby" / "Derby")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "docs" / "ui"
sys.path.insert(0, str(PROJECT_ROOT))

from PySide2.QtCore import Qt  # noqa: E402
from PySide2.QtGui import QFont  # noqa: E402
from PySide2.QtWidgets import QApplication  # noqa: E402

from derby.core.db import (  # noqa: E402
    categories_repo,
    products_repo,
    ps_devices_repo,
    settings_repo,
    tables_repo,
    users_repo,
)
from derby.core.db.connection import connect  # noqa: E402
from derby.core.db.migrations import run_pending_migrations  # noqa: E402
from derby.core.theme.fonts import CAIRO_FAMILY, load_bundled_fonts  # noqa: E402
from derby.core.theme.stylesheet import build_stylesheet  # noqa: E402
from derby.features.dashboard.daily_stats_screen import DailyStatsScreen  # noqa: E402
from derby.features.playstation import ps_service  # noqa: E402
from derby.features.pos import orders_service  # noqa: E402
from derby.features.pos.pos_screen import PosScreen  # noqa: E402


def _seed(conn) -> dict:
    settings_repo.ensure_defaults(conn)
    settings_repo.set_value(conn, "cafe_name", "ديربي")

    owner_id = users_repo.create_user(conn, "محمد المالك", users_repo.ROLE_OWNER, "1111")

    drinks_id = categories_repo.create_category(conn, "مشروبات ساخنة")
    categories_repo.create_category(conn, "مشروبات باردة")
    categories_repo.create_category(conn, "حلويات")
    coffee_id = products_repo.create_product(conn, drinks_id, "قهوة تركي", "", 2500)
    products_repo.create_product(conn, drinks_id, "كابتشينو", "", 3500)
    products_repo.create_product(conn, drinks_id, "آيس أمريكان كوفي حليب بالكراميل", "", 4500)
    products_repo.create_product(conn, drinks_id, "جالكسي حجم كبير مع إضافات شوكولاتة", "", 9000)
    products_repo.create_product(conn, drinks_id, "شاي", "", 1000)
    products_repo.create_product(conn, drinks_id, "نسكافيه", "", 2000)

    # Two busy tables + a takeaway draft, for the Home screen's open-orders grid.
    tables = tables_repo.list_tables(conn, active_only=True)
    order1 = orders_service.get_or_create_table_order(conn, tables[0]["id"], owner_id)
    orders_service.add_item(conn, order1["id"], coffee_id, 2, [], None, owner_id)
    order2 = orders_service.get_or_create_table_order(conn, tables[1]["id"], owner_id)
    orders_service.add_item(conn, order2["id"], coffee_id, 1, [], None, owner_id)

    takeaway = orders_service.create_takeaway_order(conn, owner_id, label="تيك أواي أحمد")
    orders_service.add_item(conn, takeaway["id"], coffee_id, 3, [], None, owner_id)

    device = ps_devices_repo.list_devices(conn)[0]
    ps_devices_repo.set_rates(conn, device["id"], 4000, 6000)
    ps_service.start_session(conn, device["id"], "single", owner_id)

    # A third, otherwise-untouched table for the product-grid screenshot.
    menu_order = orders_service.get_or_create_table_order(conn, tables[2]["id"], owner_id)

    return {"owner_id": owner_id, "menu_order_id": menu_order["id"]}


def _capture(widget, name: str, size=(1280, 1400)) -> None:
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

    conn = connect(_work_dir / "preview.db")
    run_pending_migrations(conn)
    seed = _seed(conn)
    owner = users_repo.get_user(conn, seed["owner_id"])

    home = DailyStatsScreen(conn, owner)
    _capture(home, "phase10_home")

    pos = PosScreen(conn, owner)
    pos.open_order(seed["menu_order_id"])
    _capture(pos, "phase10_menu_cards")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
