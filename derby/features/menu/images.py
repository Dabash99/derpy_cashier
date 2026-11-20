"""Product image storage: resize with Qt only (no Pillow dependency),
store full images and thumbnails under %APPDATA%\\Derby\\images, and never
trust the original file name (always generate our own).
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from PySide2.QtCore import Qt
from PySide2.QtGui import QImage, QPixmap

from derby.core.utils.paths import app_data_dir

FULL_IMAGE_MAX_DIMENSION = 800
THUMBNAIL_MAX_DIMENSION = 160
JPEG_QUALITY = 85

_thumbnail_cache: "dict[str, QPixmap]" = {}
_THUMBNAIL_CACHE_MAX_ITEMS = 64


class InvalidImageError(ValueError):
    """Raised when a chosen file is not a readable image."""


def images_dir() -> Path:
    folder = app_data_dir() / "images"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def thumbs_dir() -> Path:
    folder = images_dir() / "thumbs"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _scaled_down_to(image: QImage, max_dimension: int) -> QImage:
    longest_side = max(image.width(), image.height())
    if longest_side <= max_dimension:
        return image
    if image.width() >= image.height():
        return image.scaledToWidth(max_dimension, Qt.SmoothTransformation)
    return image.scaledToHeight(max_dimension, Qt.SmoothTransformation)


def save_product_image(source_path: Path) -> str:
    """Resizes and stores a chosen image, returning the generated file name.

    Raises InvalidImageError if the file can't be read as an image.
    """
    image = QImage(str(source_path))
    if image.isNull():
        raise InvalidImageError("not a readable image: {0}".format(source_path))

    file_name = "{0}.jpg".format(uuid.uuid4().hex)

    full_image = _scaled_down_to(image, FULL_IMAGE_MAX_DIMENSION)
    full_image.save(str(images_dir() / file_name), "JPG", JPEG_QUALITY)

    thumbnail = _scaled_down_to(image, THUMBNAIL_MAX_DIMENSION)
    thumbnail.save(str(thumbs_dir() / file_name), "JPG", JPEG_QUALITY)

    return file_name


def delete_product_image(file_name: Optional[str]) -> None:
    if not file_name:
        return
    full_path = images_dir() / file_name
    thumb_path = thumbs_dir() / file_name
    if full_path.exists():
        full_path.unlink()
    if thumb_path.exists():
        thumb_path.unlink()
    _thumbnail_cache.pop(file_name, None)


def load_thumbnail_pixmap(file_name: Optional[str]) -> Optional[QPixmap]:
    """Loads a thumbnail lazily, with a small LRU-ish cache so scrolling a
    long product table doesn't keep hitting the disk."""
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
