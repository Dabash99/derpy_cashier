from __future__ import annotations

import pytest

from derby.features.menu.price_parsing import parse_product_price


def test_parse_whole_number():
    assert parse_product_price("25") == 2500


def test_parse_one_decimal():
    assert parse_product_price("25.5") == 2550


def test_parse_two_decimals():
    assert parse_product_price("25.50") == 2550


def test_parse_arabic_indic_digits():
    assert parse_product_price("٢٥.٥٠") == 2550
    assert parse_product_price("١٠٠") == 10000


def test_rejects_three_decimals():
    with pytest.raises(ValueError):
        parse_product_price("25.555")


def test_rejects_negative():
    with pytest.raises(ValueError):
        parse_product_price("-5")


def test_rejects_empty():
    with pytest.raises(ValueError):
        parse_product_price("")
    with pytest.raises(ValueError):
        parse_product_price("   ")


def test_rejects_non_numeric():
    with pytest.raises(ValueError):
        parse_product_price("abc")
    with pytest.raises(ValueError):
        parse_product_price("25.5.5")
