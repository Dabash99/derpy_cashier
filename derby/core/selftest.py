"""`python -m derby --selftest` (source and frozen): proves a build can
actually do the things that matter, end to end, without touching real
user data or the network. Prints one JSON object to stdout and exits 0
if every check passed, 1 otherwise.

Every path is sandboxed: if DERBY_DATA_DIR/DERBY_DOCS_DIR are not
already set by the caller, this creates its own temp directories and
sets them for the duration of the run -- never %APPDATA%\\Derby, never
Documents\\Derby. QT_QPA_PLATFORM defaults to offscreen so this also
works on a machine/CI runner with no display.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, List

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_SELFTEST_WORK_DIR = None


def _ensure_sandboxed_env() -> Path:
    global _SELFTEST_WORK_DIR
    work_dir = Path(tempfile.mkdtemp(prefix="derby_selftest_"))
    _SELFTEST_WORK_DIR = work_dir
    os.environ.setdefault("DERBY_DATA_DIR", str(work_dir / "appdata" / "Derby"))
    os.environ.setdefault("DERBY_DOCS_DIR", str(work_dir / "documents" / "Derby"))
    return work_dir


class _Results:
    def __init__(self) -> None:
        self.items: List[dict] = []

    def check(self, name: str, fn: Callable[[], None]) -> None:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 -- a selftest check failing is data, not a crash
            self.items.append({"name": name, "passed": False, "error": "{0}: {1}".format(type(exc).__name__, exc)})
        else:
            self.items.append({"name": name, "passed": True, "error": None})

    def all_passed(self) -> bool:
        return all(item["passed"] for item in self.items)


def run_selftest() -> _Results:
    _ensure_sandboxed_env()
    results = _Results()
    ctx: dict = {}

    def check_migrations_from_scratch():
        from derby.core.db.connection import connect
        from derby.core.db.migrations import MIGRATIONS, run_pending_migrations

        db_path = _SELFTEST_WORK_DIR / "selftest.db"
        conn = connect(db_path)
        run_pending_migrations(conn)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
        ctx["conn"] = conn
        ctx["db_path"] = db_path

    def check_fonts_and_arabic_shaping():
        from PySide2.QtGui import QFont, QFontDatabase, QFontInfo, QFontMetrics
        from PySide2.QtWidgets import QApplication

        from derby.core.theme import fonts

        app = QApplication.instance() or QApplication([])
        ctx["app"] = app
        fonts.load_bundled_fonts()
        assert fonts.CAIRO_FAMILY in QFontDatabase().families()
        info = QFontInfo(QFont(fonts.CAIRO_FAMILY, 15))
        assert info.family() == fonts.CAIRO_FAMILY
        metrics = QFontMetrics(QFont(fonts.CAIRO_FAMILY, 15))
        assert metrics.horizontalAdvance("ديربي") > 0
        # Montserrat is allowed to be absent (see fonts.py); only assert
        # it does not crash either way.
        _ = fonts.montserrat_available()

    def check_brand_assets_present():
        from derby.core.utils.resource_path import resource_path

        must_exist = [
            resource_path("assets", "brand", "logo-full-transparent-256.png"),
            resource_path("assets", "brand", "icon-mark-mono-black-256.png"),
            resource_path("assets", "fonts", "Cairo-Regular.ttf"),
        ]
        for path in must_exist:
            assert path.exists() and path.stat().st_size > 0, "missing: {0}".format(path)

    def check_timezone_resolves():
        from derby.core.utils.time_utils import CAIRO_TZ

        now_cairo = datetime(2026, 6, 1, 12, 0, tzinfo=CAIRO_TZ)
        assert now_cairo.utcoffset() is not None

    def check_owner_setup_and_pin_login():
        from derby.core.db import settings_repo, users_repo

        conn = ctx["conn"]
        settings_repo.ensure_defaults(conn)
        owner_id = users_repo.create_user(conn, "Selftest Owner", users_repo.ROLE_OWNER, "1111")
        found = users_repo.find_active_user_by_pin(conn, "1111")
        assert found is not None and found["id"] == owner_id
        ctx["owner_id"] = owner_id
        ctx["owner"] = users_repo.get_user(conn, owner_id)

    def check_category_product_addon():
        from derby.core.db import addons_repo, categories_repo, products_repo

        conn = ctx["conn"]
        category_id = categories_repo.create_category(conn, "مشروبات")
        product_id = products_repo.create_product(conn, category_id, "قهوة", "", 2500)
        group_id = addons_repo.create_group(conn, "الحجم")
        addons_repo.create_addon(conn, group_id, "كبير", 500)
        addons_repo.set_product_addon_groups(conn, product_id, [group_id])
        assert addons_repo.get_product_group_ids(conn, product_id) == [group_id]
        ctx["product_id"] = product_id

    def check_order_pay_cash_invoice_number():
        from derby.core.db import orders_repo

        conn = ctx["conn"]
        order_id = orders_repo.create_order(conn, None, ctx["owner_id"])
        orders_repo.create_order_item(conn, order_id, "product", ctx["product_id"], "قهوة", 2500, 1, 2500)
        orders_repo.update_order_totals(conn, order_id, 2500, 0, 2500)
        invoice_no = orders_repo.next_invoice_no(conn)
        today = date(2026, 6, 1).isoformat()
        orders_repo.mark_order_paid(conn, order_id, invoice_no, ctx["owner_id"], today, "cash")
        paid = orders_repo.get_order(conn, order_id)
        assert paid["status"] == "paid" and paid["invoice_no"] == invoice_no
        ctx["order_id"] = order_id
        ctx["business_date"] = today

    def check_ps_session_fake_clock_pricing():
        from derby.core.db import ps_devices_repo
        from derby.features.playstation import ps_service

        conn = ctx["conn"]
        device = ps_devices_repo.list_devices(conn)[0]
        ps_devices_repo.set_rates(conn, device["id"], 4000, 6000)  # 40/60 EGP per hour
        start = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
        stop = start + timedelta(minutes=37)
        ps_service.start_session(conn, device["id"], "single", ctx["owner_id"], now=start)
        stopped = ps_service.stop_session(conn, device["id"], ctx["owner_id"], now=stop)
        # 40 EGP/hour * 37 min = 24.666 EGP -> rounds to 25 EGP (2500 piasters)
        assert stopped["price_piasters"] == 2500, stopped["price_piasters"]

    def check_expense_with_receipt_image_resize():
        from PySide2.QtGui import QColor, QImage

        from derby.core.db import expense_categories_repo, expenses_repo
        from derby.features.expenses import receipts

        conn = ctx["conn"]
        source_path = _SELFTEST_WORK_DIR / "fake_receipt.png"
        image = QImage(640, 480, QImage.Format_RGB32)
        image.fill(QColor("white"))
        image.save(str(source_path), "PNG")

        file_name = receipts.save_receipt_image(source_path)  # resizes + saves as JPEG -- proves the Qt JPEG plugin is bundled
        saved_path = receipts.receipts_dir() / file_name
        assert saved_path.exists() and saved_path.stat().st_size > 0

        category = expense_categories_repo.list_categories(conn)[0]
        expenses_repo.create_expense(
            conn, category["id"], 15000, ctx["business_date"], "فاتورة اختبار", ctx["owner_id"], receipt_file=file_name
        )

    def check_daily_report():
        from derby.features.reports import report_service

        conn = ctx["conn"]
        report = report_service.build_report(
            conn, date(2026, 6, 1), date(2026, 6, 1), today=date(2026, 6, 1)
        )
        assert report.invoice_count >= 1
        ctx["report"] = report

    def check_csv_xlsx_pdf_exports():
        import openpyxl

        from derby.features.reports import export_service

        report = ctx["report"]
        csv_path = _SELFTEST_WORK_DIR / "report.csv"
        xlsx_path = _SELFTEST_WORK_DIR / "report.xlsx"
        pdf_path = _SELFTEST_WORK_DIR / "report.pdf"
        export_service.export_report_csv(report, csv_path)
        export_service.export_report_xlsx(report, xlsx_path)
        export_service.export_report_pdf(report, "ديربي", datetime(2026, 6, 1, 12, 0), pdf_path)

        assert csv_path.exists() and csv_path.stat().st_size > 0
        openpyxl.load_workbook(str(xlsx_path))  # must reopen without error
        assert pdf_path.read_bytes().startswith(b"%PDF")

    def check_backup_and_verify():
        from derby.features.closing import backup_service

        conn = ctx["conn"]
        snapshot = backup_service.take_snapshot(conn)
        dest = _SELFTEST_WORK_DIR / "backups" / "derby-selftest.db"
        backup_service.backup_to_file(ctx["db_path"], dest)
        backup_service.verify_backup(dest, snapshot)  # raises on failure
        ctx["backup_path"] = dest

    def check_staged_restore_simulation():
        from derby.features.closing import restore_service

        fake_app_data_dir = _SELFTEST_WORK_DIR / "restore_sim_appdata"
        fake_app_data_dir.mkdir(parents=True, exist_ok=True)
        (fake_app_data_dir / "derby.db").write_bytes(b"old-db-placeholder")
        primary_backup_dir = _SELFTEST_WORK_DIR / "backups"

        restore_service.stage_restore(ctx["backup_path"], fake_app_data_dir, primary_backup_dir, datetime(2026, 6, 1))
        result = restore_service.apply_pending_restore(fake_app_data_dir)
        assert result is not None and result["status"] == "ok"
        restored_bytes = (fake_app_data_dir / "derby.db").read_bytes()
        assert restored_bytes != b"old-db-placeholder"

    def check_closing_text():
        from derby.features.closing import closing_service

        conn = ctx["conn"]
        closure, _already_existed = closing_service.close_today_manually(
            conn, ctx["db_path"], datetime(2026, 6, 1, 23, 50), "ديربي", None, None, 30
        )
        assert closure["report_text"]
        ctx["closing_text"] = closure["report_text"]

    def check_whatsapp_url_builder_no_launch():
        from derby.core.integrations import whatsapp

        ok, cleaned = whatsapp.validate_number("201234567890")
        assert ok
        url = whatsapp.build_desktop_url(cleaned, ctx["closing_text"])
        assert url.startswith("whatsapp://send?")
        web_url = whatsapp.build_web_url(cleaned, ctx["closing_text"])
        assert web_url.startswith("https://wa.me/")

    def check_update_manifest_parsing_no_network():
        from derby.core.updates import version_logic

        manifest = version_logic.parse_manifest(
            '{"version": "0.2.0", '
            '"download_url": "https://github.com/example/derby/releases/download/v0.2.0/Derby-Setup-0.2.0.exe", '
            '"notes": "test", '
            '"sha256": "' + ("a" * 64) + '"}'
        )
        assert manifest["version"] == "0.2.0"
        assert version_logic.is_newer("0.1.0", "0.2.0") is True

    def check_main_window_builds_for_owner_and_cashier():
        from derby.core.db import users_repo
        from derby.core.theme.stylesheet import build_stylesheet
        from derby.features.shell.idle_filter import IdleTimer
        from derby.features.shell.main_window import MainWindow

        conn = ctx["conn"]
        app = ctx["app"]
        app.setStyleSheet(build_stylesheet())
        cashier_id = users_repo.create_user(conn, "Selftest Cashier", users_repo.ROLE_CASHIER, "2222")
        owner_window = MainWindow(conn, ctx["owner"], IdleTimer(), ctx["db_path"])
        cashier_window = MainWindow(conn, users_repo.get_user(conn, cashier_id), IdleTimer(), ctx["db_path"])
        assert owner_window is not None and cashier_window is not None

    results.check("migrations_from_scratch", check_migrations_from_scratch)
    results.check("fonts_and_arabic_shaping", check_fonts_and_arabic_shaping)
    results.check("brand_assets_present", check_brand_assets_present)
    results.check("timezone_resolves", check_timezone_resolves)
    results.check("owner_setup_and_pin_login", check_owner_setup_and_pin_login)
    results.check("category_product_addon", check_category_product_addon)
    results.check("order_pay_cash_invoice_number", check_order_pay_cash_invoice_number)
    results.check("ps_session_fake_clock_pricing", check_ps_session_fake_clock_pricing)
    results.check("expense_with_receipt_image_resize", check_expense_with_receipt_image_resize)
    results.check("daily_report", check_daily_report)
    results.check("csv_xlsx_pdf_exports", check_csv_xlsx_pdf_exports)
    results.check("backup_and_verify", check_backup_and_verify)
    results.check("staged_restore_simulation", check_staged_restore_simulation)
    results.check("closing_text", check_closing_text)
    results.check("whatsapp_url_builder_no_launch", check_whatsapp_url_builder_no_launch)
    results.check("update_manifest_parsing_no_network", check_update_manifest_parsing_no_network)
    results.check("main_window_builds_for_owner_and_cashier", check_main_window_builds_for_owner_and_cashier)

    return results


def main() -> int:
    results = run_selftest()
    payload = {"passed": results.all_passed(), "checks": results.items}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if results.all_passed() else 1


if __name__ == "__main__":
    sys.exit(main())
