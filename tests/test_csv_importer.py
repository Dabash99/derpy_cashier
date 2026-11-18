from __future__ import annotations

from PySide2.QtGui import QImage

from derby.core.db import categories_repo, products_repo
from derby.features.menu.csv_export import export_menu_csv
from derby.features.menu.csv_importer import (
    EXISTS_ACTION_SKIP,
    EXISTS_ACTION_UPDATE,
    STATUS_EXISTS,
    STATUS_INVALID,
    STATUS_NEW,
    apply_import,
    classify_row,
    classify_rows,
)
from derby.features.menu.csv_parser import RawCsvRow


def _raw(line_number=2, category="مشروبات", name_ar="قهوة", name_en="Coffee", price="25", currency="EGP", image_file=""):
    return RawCsvRow(
        line_number=line_number,
        category=category,
        name_ar=name_ar,
        name_en=name_en,
        price=price,
        currency=currency,
        image_file=image_file,
    )


def test_classify_new_row(db_conn, tmp_path):
    row = classify_row(db_conn, _raw(), tmp_path)
    assert row.status == STATUS_NEW
    assert row.price_piasters == 2500


def test_classify_invalid_currency(db_conn, tmp_path):
    row = classify_row(db_conn, _raw(currency="USD"), tmp_path)
    assert row.status == STATUS_INVALID


def test_classify_invalid_missing_category(db_conn, tmp_path):
    row = classify_row(db_conn, _raw(category=""), tmp_path)
    assert row.status == STATUS_INVALID


def test_classify_invalid_missing_name(db_conn, tmp_path):
    row = classify_row(db_conn, _raw(name_ar=""), tmp_path)
    assert row.status == STATUS_INVALID


def test_classify_invalid_price(db_conn, tmp_path):
    row = classify_row(db_conn, _raw(price="25.555"), tmp_path)
    assert row.status == STATUS_INVALID

    row = classify_row(db_conn, _raw(price="not a number"), tmp_path)
    assert row.status == STATUS_INVALID


def test_classify_exists_row(db_conn, tmp_path):
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    products_repo.create_product(db_conn, category_id, "قهوة", "Coffee", 2000)

    row = classify_row(db_conn, _raw(), tmp_path)
    assert row.status == STATUS_EXISTS


def test_classify_missing_image_is_a_warning_not_invalid(db_conn, tmp_path):
    row = classify_row(db_conn, _raw(image_file="does_not_exist.jpg"), tmp_path)
    assert row.status == STATUS_NEW
    assert row.missing_image is True


def test_classify_existing_image_is_not_missing(qapp, db_conn, tmp_path):
    image_path = tmp_path / "coffee.jpg"
    image = QImage(50, 50, QImage.Format_RGB32)
    image.save(str(image_path), "JPG")

    row = classify_row(db_conn, _raw(image_file="coffee.jpg"), tmp_path)
    assert row.missing_image is False


def test_apply_import_creates_new_products_with_needs_review(qapp, db_conn, tmp_path, monkeypatch):
    monkeypatch.setattr("derby.features.menu.images.app_data_dir", lambda: tmp_path / "appdata")
    rows = classify_rows(db_conn, [_raw()], tmp_path)
    counts = apply_import(db_conn, rows, tmp_path)

    assert counts == {"new": 1, "updated": 0, "skipped": 0, "invalid": 0, "missing_images": 0}
    products = products_repo.list_products(db_conn)
    assert len(products) == 1
    assert products[0]["needs_price_review"] == 1
    assert products[0]["price_piasters"] == 2500


def test_apply_import_is_idempotent_with_skip(qapp, db_conn, tmp_path, monkeypatch):
    monkeypatch.setattr("derby.features.menu.images.app_data_dir", lambda: tmp_path / "appdata")
    raw_rows = [_raw()]

    rows = classify_rows(db_conn, raw_rows, tmp_path)
    apply_import(db_conn, rows, tmp_path, exists_action=EXISTS_ACTION_SKIP)

    # Re-running the same CSV: the row is now EXISTS, and with skip (default)
    # it must not create a duplicate.
    rows_again = classify_rows(db_conn, raw_rows, tmp_path)
    counts = apply_import(db_conn, rows_again, tmp_path, exists_action=EXISTS_ACTION_SKIP)

    assert counts["new"] == 0
    assert counts["skipped"] == 1
    products = products_repo.list_products(db_conn)
    assert len(products) == 1


def test_apply_import_update_option_updates_existing(qapp, db_conn, tmp_path, monkeypatch):
    monkeypatch.setattr("derby.features.menu.images.app_data_dir", lambda: tmp_path / "appdata")
    raw_rows = [_raw(price="25")]
    rows = classify_rows(db_conn, raw_rows, tmp_path)
    apply_import(db_conn, rows, tmp_path)

    updated_raw_rows = [_raw(price="30")]
    rows_again = classify_rows(db_conn, updated_raw_rows, tmp_path)
    counts = apply_import(db_conn, rows_again, tmp_path, exists_action=EXISTS_ACTION_UPDATE)

    assert counts["updated"] == 1
    products = products_repo.list_products(db_conn)
    assert len(products) == 1
    assert products[0]["price_piasters"] == 3000
    assert products[0]["needs_price_review"] == 1


def test_apply_import_counts_invalid_rows(db_conn, tmp_path):
    rows = classify_rows(db_conn, [_raw(currency="USD"), _raw(name_ar="شاي")], tmp_path)
    counts = apply_import(db_conn, rows, tmp_path)
    assert counts["invalid"] == 1
    assert counts["new"] == 1


def test_export_then_reimport_round_trip_is_idempotent(qapp, db_conn, tmp_path, monkeypatch):
    monkeypatch.setattr("derby.features.menu.images.app_data_dir", lambda: tmp_path / "appdata")

    rows = classify_rows(db_conn, [_raw(name_ar="قهوة", price="25"), _raw(name_ar="شاي", price="15")], tmp_path)
    apply_import(db_conn, rows, tmp_path)
    assert len(products_repo.list_products(db_conn)) == 2

    export_dir = tmp_path / "export"
    export_dir.mkdir()
    export_path = export_dir / "menu.csv"
    export_menu_csv(db_conn, export_path)

    exported_text = export_path.read_text(encoding="utf-8-sig")
    assert "قهوة" in exported_text
    assert "شاي" in exported_text

    from derby.features.menu.csv_parser import parse_csv_text

    raw_rows_from_export = parse_csv_text(exported_text)
    reimport_rows = classify_rows(db_conn, raw_rows_from_export, export_dir / "images")
    counts = apply_import(db_conn, reimport_rows, export_dir / "images")

    assert counts["new"] == 0
    assert counts["skipped"] == 2
    assert len(products_repo.list_products(db_conn)) == 2


def test_apply_import_auto_creates_category(db_conn, tmp_path):
    assert categories_repo.list_categories(db_conn) == []
    rows = classify_rows(db_conn, [_raw(category="عصائر")], tmp_path)
    apply_import(db_conn, rows, tmp_path)

    categories = categories_repo.list_categories(db_conn)
    assert len(categories) == 1
    assert categories[0]["name"] == "عصائر"
