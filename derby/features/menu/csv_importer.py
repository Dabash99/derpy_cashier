"""Classifies parsed CSV rows against the database (NEW / EXISTS / INVALID)
and applies an import as one SQL transaction. The actual threading lives
in import_dialog.py -- this module is plain functions so it's directly
testable.
"""
from __future__ import annotations

from collections import namedtuple
from pathlib import Path
from typing import Callable, List, Optional

from derby.core.db import categories_repo, products_repo
from derby.features.menu import images
from derby.features.menu.csv_parser import RawCsvRow
from derby.features.menu.price_parsing import parse_product_price

STATUS_NEW = "new"
STATUS_EXISTS = "exists"
STATUS_INVALID = "invalid"

EXISTS_ACTION_SKIP = "skip"
EXISTS_ACTION_UPDATE = "update"

ImportRow = namedtuple(
    "ImportRow",
    [
        "line_number",
        "category_name",
        "name_ar",
        "name_en",
        "price_piasters",
        "image_file",
        "status",
        "note",
        "missing_image",
        "existing_product_id",
    ],
)


def _invalid(raw: RawCsvRow, reason: str) -> ImportRow:
    return ImportRow(
        line_number=raw.line_number,
        category_name=raw.category,
        name_ar=raw.name_ar,
        name_en=raw.name_en,
        price_piasters=None,
        image_file=raw.image_file or None,
        status=STATUS_INVALID,
        note=reason,
        missing_image=False,
        existing_product_id=None,
    )


def classify_row(conn, raw: RawCsvRow, images_folder: Path) -> ImportRow:
    if raw.currency.strip().upper() != "EGP":
        return _invalid(raw, "عملة غير مدعومة (يجب أن تكون EGP)")
    if not raw.category:
        return _invalid(raw, "القسم مطلوب")
    if not raw.name_ar:
        return _invalid(raw, "الاسم بالعربي مطلوب")
    try:
        price_piasters = parse_product_price(raw.price)
    except ValueError:
        return _invalid(raw, "السعر غير صحيح: {0!r}".format(raw.price))

    existing_category = categories_repo.get_category_by_name(conn, raw.category)
    existing_product_id = None
    status = STATUS_NEW
    if existing_category is not None:
        existing_product = products_repo.find_product_by_name(conn, existing_category["id"], raw.name_ar)
        if existing_product is not None:
            status = STATUS_EXISTS
            existing_product_id = existing_product["id"]

    missing_image = False
    note = ""
    if raw.image_file:
        if not (images_folder / raw.image_file).exists():
            missing_image = True
            note = "الصورة غير موجودة: {0}".format(raw.image_file)

    return ImportRow(
        line_number=raw.line_number,
        category_name=raw.category,
        name_ar=raw.name_ar,
        name_en=raw.name_en,
        price_piasters=price_piasters,
        image_file=raw.image_file or None,
        status=status,
        note=note,
        missing_image=missing_image,
        existing_product_id=existing_product_id,
    )


def classify_rows(conn, raw_rows: List[RawCsvRow], images_folder: Path) -> List[ImportRow]:
    return [classify_row(conn, raw, images_folder) for raw in raw_rows]


def _save_row_image(row: ImportRow, images_folder: Path) -> Optional[str]:
    if not row.image_file or row.missing_image:
        return None
    try:
        return images.save_product_image(images_folder / row.image_file)
    except images.InvalidImageError:
        return None


def apply_import(
    conn,
    rows: List[ImportRow],
    images_folder: Path,
    exists_action: str = EXISTS_ACTION_SKIP,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> dict:
    """Applies a classified import as one SQL transaction. Re-running the
    same CSV is a no-op for rows already imported (idempotent) as long as
    exists_action is "skip" (the default)."""
    counts = {"new": 0, "updated": 0, "skipped": 0, "invalid": 0, "missing_images": 0}
    category_id_by_name = {}
    total = len(rows)

    conn.execute("BEGIN")
    try:
        for index, row in enumerate(rows, start=1):
            if row.status == STATUS_INVALID:
                counts["invalid"] += 1
            else:
                if row.missing_image:
                    counts["missing_images"] += 1

                category_id = category_id_by_name.get(row.category_name)
                if category_id is None:
                    existing_category = categories_repo.get_category_by_name(conn, row.category_name)
                    if existing_category is not None:
                        category_id = existing_category["id"]
                    else:
                        category_id = categories_repo.create_category(conn, row.category_name, commit=False)
                    category_id_by_name[row.category_name] = category_id

                saved_image_file = _save_row_image(row, images_folder)

                if row.status == STATUS_NEW:
                    products_repo.create_product(
                        conn,
                        category_id,
                        row.name_ar,
                        row.name_en,
                        row.price_piasters,
                        image_file=saved_image_file,
                        needs_price_review=True,
                        commit=False,
                    )
                    counts["new"] += 1
                elif row.status == STATUS_EXISTS:
                    if exists_action == EXISTS_ACTION_UPDATE:
                        products_repo.set_price_from_import(
                            conn, row.existing_product_id, row.price_piasters, saved_image_file, commit=False
                        )
                        counts["updated"] += 1
                    else:
                        counts["skipped"] += 1

            if progress_callback is not None:
                progress_callback(index, total)
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return counts
