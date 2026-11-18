"""Pure CSV text parsing for menu import/export -- no database, no Qt, so
it's trivially unit-testable. derby/features/menu/csv_importer.py is the
layer that turns these raw rows into database writes.
"""
from __future__ import annotations

import csv
import io
from collections import namedtuple
from typing import List

REQUIRED_COLUMNS = ("category", "name_ar", "name_en", "price", "currency", "image_file")

RawCsvRow = namedtuple(
    "RawCsvRow", ["line_number", "category", "name_ar", "name_en", "price", "currency", "image_file"]
)


class CsvFormatError(ValueError):
    """Raised when the CSV header is missing required columns."""


def _strip_bom(text: str) -> str:
    if text.startswith("﻿"):
        return text[1:]
    return text


def parse_csv_text(text: str) -> List[RawCsvRow]:
    text = _strip_bom(text)
    reader = csv.DictReader(io.StringIO(text), restval="")

    fieldnames = reader.fieldnames or []
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in fieldnames]
    if missing_columns:
        raise CsvFormatError("missing columns: {0}".format(", ".join(missing_columns)))

    rows = []
    for line_number, raw_row in enumerate(reader, start=2):  # header is line 1
        rows.append(
            RawCsvRow(
                line_number=line_number,
                category=(raw_row.get("category") or "").strip(),
                name_ar=(raw_row.get("name_ar") or "").strip(),
                name_en=(raw_row.get("name_en") or "").strip(),
                price=(raw_row.get("price") or "").strip(),
                currency=(raw_row.get("currency") or "").strip(),
                image_file=(raw_row.get("image_file") or "").strip(),
            )
        )
    return rows


def write_csv_text(rows) -> str:
    """rows: iterable of (category, name_ar, name_en, price_text, currency, image_file)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(REQUIRED_COLUMNS)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()
