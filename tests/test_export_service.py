"""Export file verification: xlsx re-opened with openpyxl, CSV BOM +
Arabic round-trip, PDF non-empty and starts with %PDF. No screenshots --
file-content assertions only, per the working rules.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from derby.core.db import categories_repo, expense_categories_repo, expenses_repo, products_repo, users_repo
from derby.features.reports import export_service, report_service


@pytest.fixture()
def sample_report(db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    products_repo.create_product(db_conn, category_id, "قهوة", "", 2500)

    from derby.core.db import orders_repo

    order_id = orders_repo.create_order(db_conn, None, owner_id)
    orders_repo.create_order_item(db_conn, order_id, "product", None, "قهوة", 2500, 2, 5000)
    orders_repo.update_order_totals(db_conn, order_id, 5000, 0, 5000)
    orders_repo.mark_order_paid(db_conn, order_id, orders_repo.next_invoice_no(db_conn), owner_id, "2026-01-10", "cash")

    expense_category = expense_categories_repo.list_categories(db_conn)[0]
    expenses_repo.create_expense(db_conn, expense_category["id"], 1000, "2026-01-10", "فاتورة", owner_id)

    return report_service.build_report(db_conn, date(2026, 1, 10), date(2026, 1, 10), today=date(2026, 1, 10))


def test_csv_export_has_bom_and_round_trips_arabic(tmp_path, sample_report):
    path = tmp_path / "report.csv"
    export_service.export_report_csv(sample_report, path)

    raw_bytes = path.read_bytes()
    assert raw_bytes.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM, Excel needs it for Arabic

    text = path.read_text(encoding="utf-8-sig")
    assert "الملخص المالي" in text
    assert "إجمالي المبيعات" in text
    assert "5000.00" not in text  # money is piasters-rendered, never a raw float
    assert "50.00" in text  # 5000 piasters -> 50.00 EGP


def test_xlsx_export_reopens_with_correct_numbers_and_rtl(tmp_path, sample_report):
    import openpyxl

    path = tmp_path / "report.xlsx"
    export_service.export_report_xlsx(sample_report, path)
    assert path.exists() and path.stat().st_size > 0

    workbook = openpyxl.load_workbook(str(path))
    assert "الملخص المالي" in workbook.sheetnames
    sheet = workbook["الملخص المالي"]
    assert sheet.sheet_view.rightToLeft is True

    values = {row[0].value: row[1].value for row in sheet.iter_rows(min_row=2)}
    assert values["إجمالي المبيعات"] == pytest.approx(50.0)
    assert values["إجمالي المصروفات"] == pytest.approx(10.0)
    assert values["الربح"] == pytest.approx(40.0)

    count_sheet = workbook["عدد الفواتير"]
    assert count_sheet.cell(row=2, column=1).value == 1


def test_pdf_export_is_non_empty_and_valid_header(qapp, tmp_path, sample_report):
    path = tmp_path / "report.pdf"
    export_service.export_report_pdf(sample_report, "ديربي", datetime(2026, 1, 10, 12, 0), path)

    raw_bytes = path.read_bytes()
    assert len(raw_bytes) > 1000
    assert raw_bytes.startswith(b"%PDF")


def test_export_of_an_empty_period_works(qapp, tmp_path, db_conn):
    empty_report = report_service.build_report(db_conn, date(2026, 3, 1), date(2026, 3, 1), today=date(2026, 3, 1))
    csv_path, xlsx_path, pdf_path = tmp_path / "e.csv", tmp_path / "e.xlsx", tmp_path / "e.pdf"

    export_service.export_report_csv(empty_report, csv_path)
    export_service.export_report_xlsx(empty_report, xlsx_path)
    export_service.export_report_pdf(empty_report, "ديربي", datetime(2026, 3, 1, 9, 0), pdf_path)

    assert csv_path.exists() and xlsx_path.exists() and pdf_path.exists()
    assert pdf_path.read_bytes().startswith(b"%PDF")


def test_expenses_export_csv_and_xlsx(tmp_path, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    category = expense_categories_repo.list_categories(db_conn)[0]
    expenses_repo.create_expense(db_conn, category["id"], 2000, "2026-01-10", "فاتورة كهرباء", owner_id)
    rows = expenses_repo.list_expenses(db_conn)
    names_by_id = {c["id"]: c["name"] for c in expense_categories_repo.list_categories(db_conn)}

    csv_path = tmp_path / "expenses.csv"
    export_service.export_expenses_csv(rows, names_by_id, csv_path)
    text = csv_path.read_text(encoding="utf-8-sig")
    assert "فاتورة كهرباء" in text
    assert category["name"] in text

    import openpyxl

    xlsx_path = tmp_path / "expenses.xlsx"
    export_service.export_expenses_xlsx(rows, names_by_id, xlsx_path)
    workbook = openpyxl.load_workbook(str(xlsx_path))
    sheet = workbook["المصروفات"]
    assert sheet.cell(row=2, column=4).value == pytest.approx(20.0)  # 2000 piasters -> 20.00 EGP
