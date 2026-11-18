"""Arabic-friendly search: a cashier typing "قهوه" should still find "قهوة",
and "احمد" should find "أحمد". We normalize alef/ya/ta-marbuta variants and
strip diacritics (tashkeel) before comparing, on both sides.
"""
from __future__ import annotations

import re

_TASHKEEL_PATTERN = re.compile(r"[ؗ-ًؚ-ْٰـ]")

_CHARACTER_NORMALIZATION = {
    "أ": "ا",
    "إ": "ا",
    "آ": "ا",
    "ٱ": "ا",
    "ى": "ي",
    "ة": "ه",
}


def normalize_arabic_text(text: str) -> str:
    text = _TASHKEEL_PATTERN.sub("", text or "")
    for original, replacement in _CHARACTER_NORMALIZATION.items():
        text = text.replace(original, replacement)
    return text.strip().lower()


def search_matches(query: str, *candidates: str) -> bool:
    if not query.strip():
        return True
    normalized_query = normalize_arabic_text(query)
    return any(normalized_query in normalize_arabic_text(candidate) for candidate in candidates)


def filter_products_by_search(products, query: str):
    if not query.strip():
        return list(products)
    return [
        product
        for product in products
        if search_matches(query, product["name_ar"] or "", product["name_en"] or "")
    ]
