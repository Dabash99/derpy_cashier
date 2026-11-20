from __future__ import annotations

import pytest

from derby.features.menu.csv_parser import CsvFormatError, parse_csv_text, write_csv_text


def test_parse_basic_rows():
    text = "category,name_ar,name_en,price,currency,image_file\n" "مشروبات,قهوة,Coffee,25,EGP,coffee.jpg\n"
    rows = parse_csv_text(text)
    assert len(rows) == 1
    row = rows[0]
    assert row.line_number == 2
    assert row.category == "مشروبات"
    assert row.name_ar == "قهوة"
    assert row.name_en == "Coffee"
    assert row.price == "25"
    assert row.currency == "EGP"
    assert row.image_file == "coffee.jpg"


def test_parse_handles_bom():
    text = "﻿category,name_ar,name_en,price,currency,image_file\nمشروبات,قهوة,,25,EGP,\n"
    rows = parse_csv_text(text)
    assert len(rows) == 1
    assert rows[0].category == "مشروبات"


def test_parse_handles_quotes_commas_and_newlines():
    text = (
        'category,name_ar,name_en,price,currency,image_file\n'
        '"مشروبات, ساقع","قهوة ""خاصة""","Coffee, Special",25,EGP,\n'
    )
    rows = parse_csv_text(text)
    assert rows[0].category == "مشروبات, ساقع"
    assert rows[0].name_ar == 'قهوة "خاصة"'
    assert rows[0].name_en == "Coffee, Special"


def test_parse_strips_extra_spaces():
    text = "category,name_ar,name_en,price,currency,image_file\n  مشروبات ,  قهوة  ,,  25 ,EGP,\n"
    rows = parse_csv_text(text)
    assert rows[0].category == "مشروبات"
    assert rows[0].name_ar == "قهوة"
    assert rows[0].price == "25"


def test_missing_required_column_raises():
    text = "category,name_ar,price,currency,image_file\nمشروبات,قهوة,25,EGP,\n"
    with pytest.raises(CsvFormatError):
        parse_csv_text(text)


def test_write_csv_text_round_trips():
    rows = [("مشروبات", "قهوة", "Coffee", "25.00", "EGP", "coffee.jpg")]
    csv_text = write_csv_text(rows)
    parsed = parse_csv_text(csv_text)
    assert len(parsed) == 1
    assert parsed[0].category == "مشروبات"
    assert parsed[0].name_ar == "قهوة"
    assert parsed[0].price == "25.00"
