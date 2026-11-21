from __future__ import annotations

import openpyxl

from derby.core.db import drawer_repo, purchases_repo, stock_items_repo, suppliers_repo, users_repo
from derby.features.inventory import drawer_service, stock_service
from derby.features.reports import export_service


def _owner(db_conn):
    user_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    return users_repo.get_user(db_conn, user_id)


def test_export_stock_csv_and_xlsx(tmp_path, db_conn):
    owner = _owner(db_conn)
    flour_id = stock_items_repo.create_stock_item(db_conn, "دقيق", "g", min_qty=500)
    stock_service.record_purchase(
        db_conn, None, "2026-01-01", [{"stock_item_id": flour_id, "qty": 1000, "unit_cost_piasters": 10}], False, owner["id"]
    )
    items = stock_items_repo.list_stock_items(db_conn)

    csv_path = tmp_path / "stock.csv"
    export_service.export_stock_csv(items, csv_path)
    text = csv_path.read_text(encoding="utf-8-sig")
    assert "دقيق" in text

    xlsx_path = tmp_path / "stock.xlsx"
    export_service.export_stock_xlsx(items, xlsx_path)
    workbook = openpyxl.load_workbook(str(xlsx_path))
    sheet = workbook[workbook.sheetnames[0]]
    assert sheet.cell(row=2, column=1).value == "دقيق"


def test_export_purchases_csv_and_xlsx(tmp_path, db_conn):
    owner = _owner(db_conn)
    supplier_id = suppliers_repo.create_supplier(db_conn, "مورد الدقيق", None, None)
    flour_id = stock_items_repo.create_stock_item(db_conn, "دقيق", "g")
    stock_service.record_purchase(
        db_conn, supplier_id, "2026-01-01", [{"stock_item_id": flour_id, "qty": 100, "unit_cost_piasters": 10}], True, owner["id"]
    )
    purchases = purchases_repo.list_purchases(db_conn)
    supplier_names = {supplier_id: "مورد الدقيق"}

    csv_path = tmp_path / "purchases.csv"
    export_service.export_purchases_csv(purchases, supplier_names, csv_path)
    text = csv_path.read_text(encoding="utf-8-sig")
    assert "مورد الدقيق" in text
    assert "مدفوع" in text


def test_export_drawer_csv_and_xlsx(tmp_path, db_conn):
    owner = _owner(db_conn)
    drawer_service.open_drawer(db_conn, 5000, owner["id"])
    drawer_service.record_count(db_conn, 5000, owner["id"])
    entries = drawer_repo.list_entries(db_conn)
    counts = drawer_service.count_history(db_conn)

    csv_path = tmp_path / "drawer.csv"
    export_service.export_drawer_csv(entries, counts, csv_path)
    text = csv_path.read_text(encoding="utf-8-sig")
    assert "سجل الحركة" in text
    assert "سجل الجرد" in text

    xlsx_path = tmp_path / "drawer.xlsx"
    export_service.export_drawer_xlsx(entries, counts, xlsx_path)
    workbook = openpyxl.load_workbook(str(xlsx_path))
    assert len(workbook.sheetnames) == 2


def test_report_sections_include_profit_figures(db_conn):
    owner = _owner(db_conn)
    from derby.core.db import categories_repo, products_repo
    from derby.features.pos import orders_service
    from derby.features.reports import report_service

    table = __import__("derby.core.db.tables_repo", fromlist=["x"]).list_tables(db_conn)[0]
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 2500)

    order = orders_service.get_or_create_table_order(db_conn, table["id"], owner["id"])
    orders_service.add_item(db_conn, order["id"], product_id, 1, [], None, owner["id"])
    orders_service.pay(db_conn, order["id"], "cash", owner)

    today = report_service.today_business_date(db_conn)
    report = report_service.build_report(db_conn, today, today)
    sections = export_service.report_sections(report)
    summary = next(s for s in sections if s.title == "الملخص المالي")
    labels = [row[0] for row in summary.rows]
    assert "الربح الإجمالي" in labels
    assert "الربح الصافي" in labels
