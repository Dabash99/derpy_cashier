"""Strict EGP price parsing for the product dialog: accepts Arabic-Indic
digits, up to 2 decimal places, rejects negatives/empty/too-many-decimals.

This is stricter than derby/core/utils/money.parse_egp_input (which
silently truncates extra decimals) because a mistyped product price is a
real mistake the owner should be told about, not quietly rounded away.
"""
from __future__ import annotations

import re

from derby.core.utils.money import PIASTERS_PER_EGP

_ARABIC_INDIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_WESTERN_DIGITS = "0123456789"
_DIGIT_TRANSLATION = str.maketrans(_ARABIC_INDIC_DIGITS, _WESTERN_DIGITS)

_PRICE_PATTERN = re.compile(r"^\d+(\.\d{1,2})?$")


def normalize_digits(text: str) -> str:
    return text.translate(_DIGIT_TRANSLATION)


def parse_product_price(text: str) -> int:
    """Parses a price like "25", "25.5", "٢٥.٥٠" into piasters.

    Raises ValueError for empty input, negative numbers, non-numeric text,
    or more than 2 decimal places.
    """
    normalized = normalize_digits(text.strip()).replace(",", ".")
    if not normalized:
        raise ValueError("empty price")
    if not _PRICE_PATTERN.match(normalized):
        raise ValueError("invalid price format: {0!r}".format(text))

    if "." in normalized:
        egp_part, fraction_part = normalized.split(".")
        fraction_part = fraction_part.ljust(2, "0")
    else:
        egp_part, fraction_part = normalized, "00"

    return int(egp_part) * PIASTERS_PER_EGP + int(fraction_part)
