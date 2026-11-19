"""`python -m derby --selftest` must run from source, print one JSON
object with every check, and exit 0 when everything passes -- this is
the same mechanism a frozen build's --selftest run uses (Part B1/B3)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

EXPECTED_CHECK_NAMES = {
    "migrations_from_scratch",
    "fonts_and_arabic_shaping",
    "brand_assets_present",
    "timezone_resolves",
    "owner_setup_and_pin_login",
    "category_product_addon",
    "order_pay_cash_invoice_number",
    "ps_session_fake_clock_pricing",
    "expense_with_receipt_image_resize",
    "daily_report",
    "csv_xlsx_pdf_exports",
    "backup_and_verify",
    "staged_restore_simulation",
    "closing_text",
    "whatsapp_url_builder_no_launch",
    "update_manifest_parsing_no_network",
    "main_window_builds_for_owner_and_cashier",
}


def test_selftest_subprocess_exits_zero_with_every_check_passing(tmp_path):
    env = {
        "DERBY_DATA_DIR": str(tmp_path / "appdata"),
        "DERBY_DOCS_DIR": str(tmp_path / "documents"),
        "QT_QPA_PLATFORM": "offscreen",
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "PATH": os.environ.get("PATH", ""),
    }
    result = subprocess.run(
        [sys.executable, "-m", "derby", "--selftest"],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    names = {item["name"] for item in payload["checks"]}
    assert names == EXPECTED_CHECK_NAMES
    assert all(item["passed"] for item in payload["checks"]), payload


def test_run_selftest_in_process_returns_every_expected_check():
    from derby.core import selftest

    results = selftest.run_selftest()
    names = {item["name"] for item in results.items}
    assert names == EXPECTED_CHECK_NAMES
    assert results.all_passed(), results.items
