"""Writes the menu back out as a CSV the owner can edit in Excel and
re-import -- same column layout csv_parser.py reads, UTF-8 with a BOM
(Excel on Windows needs the BOM to show Arabic text correctly).
"""
from __future__ import annotations

from pathlib import Path

from derby.core.db import categories_repo, products_repo
from derby.core.utils.money import piasters_to_plain_text
from derby.features.menu.csv_parser import write_csv_text


def export_menu_csv(conn, path: Path) -> None:
    rows = []
    for category in categories_repo.list_categories(conn):
        for product in products_repo.list_products(conn, category_id=category["id"]):
            rows.append(
                (
                    category["name"],
                    product["name_ar"],
                    product["name_en"] or "",
                    piasters_to_plain_text(product["price_piasters"]),
                    "EGP",
                    product["image_file"] or "",
                )
            )
    csv_text = write_csv_text(rows)
    path.write_text(csv_text, encoding="utf-8-sig")
