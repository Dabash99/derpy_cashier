"""Receipt image storage: same Qt-only resize approach as the menu's
product images (derby/features/menu/images.py), just a different folder
and a bigger max dimension since a receipt needs to stay legible.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from PySide2.QtCore import Qt
from PySide2.QtGui import QImage, QPixmap

from derby.core.utils.paths import app_data_dir

FULL_IMAGE_MAX_DIMENSION = 1600
THUMBNAIL_MAX_DIMENSION = 160
JPEG_QUALITY = 85

_thumbnail_cache: "dict[str, QPixmap]" = {}
_THUMBNAIL_CACHE_MAX_ITEMS = 64


class InvalidImageError(ValueError):
    """Raised when a chosen file is not a readable image."""


def receipts_dir() -> Path:
    folder = app_data_dir() / "receipts"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def thumbs_dir() -> Path:
    folder = receipts_dir() / "thumbs"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _scaled_down_to(image: QImage, max_dimension: int) -> QImage:
    longest_side = max(image.width(), image.height())
    if longest_side <= max_dimension:
        return image
    if image.width() >= image.height():
        return image.scaledToWidth(max_dimension, Qt.SmoothTransformation)
    return image.scaledToHeight(max_dimension, Qt.SmoothTransformation)


def save_receipt_image(source_path: Path) -> str:
    """Resizes and stores a chosen receipt photo, returning the generated
    file name (never the original -- the original name is never trusted).

    Raises InvalidImageError if the file can't be read as an image.
    """
    image = QImage(str(source_path))
    if image.isNull():
        raise InvalidImageError("not a readable image: {0}".format(source_path))

    file_name = "{0}.jpg".format(uuid.uuid4().hex)

    full_image = _scaled_down_to(image, FULL_IMAGE_MAX_DIMENSION)
    full_image.save(str(receipts_dir() / file_name), "JPG", JPEG_QUALITY)

    thumbnail = _scaled_down_to(image, THUMBNAIL_MAX_DIMENSION)
    thumbnail.save(str(thumbs_dir() / file_name), "JPG", JPEG_QUALITY)

    return file_name


def load_thumbnail_pixmap(file_name: Optional[str]) -> Optional[QPixmap]:
    if not file_name:
        return None
    cached = _thumbnail_cache.get(file_name)
    if cached is not None:
        return cached

    path = thumbs_dir() / file_name
    if not path.exists():
        return None
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return None

    if len(_thumbnail_cache) >= _THUMBNAIL_CACHE_MAX_ITEMS:
        _thumbnail_cache.pop(next(iter(_thumbnail_cache)))
    _thumbnail_cache[file_name] = pixmap
    return pixmap


def load_full_pixmap(file_name: Optional[str]) -> Optional[QPixmap]:
    if not file_name:
        return None
    path = receipts_dir() / file_name
    if not path.exists():
        return None
    pixmap = QPixmap(str(path))
    return pixmap if not pixmap.isNull() else None
