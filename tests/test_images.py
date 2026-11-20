"""Image pipeline tests. Must run under QT_QPA_PLATFORM=offscreen (set by
pytest.ini / the environment, see conftest) since there is no real display
in CI; QImage/QPixmap both work fine headless with that platform plugin.
"""
from __future__ import annotations

import pytest
from PySide2.QtCore import Qt
from PySide2.QtGui import QImage

from derby.features.menu import images


@pytest.fixture()
def fake_appdata(tmp_path, monkeypatch):
    monkeypatch.setattr("derby.features.menu.images.app_data_dir", lambda: tmp_path)
    return tmp_path


def _make_test_image(path, width, height, color=Qt.red):
    image = QImage(width, height, QImage.Format_RGB32)
    image.fill(color)
    assert image.save(str(path), "PNG")


def test_save_product_image_resizes_large_image(qapp, fake_appdata, tmp_path):
    source = tmp_path / "source.png"
    _make_test_image(source, 2000, 1000)

    file_name = images.save_product_image(source)

    full_path = images.images_dir() / file_name
    thumb_path = images.thumbs_dir() / file_name
    assert full_path.exists()
    assert thumb_path.exists()

    full_image = QImage(str(full_path))
    assert max(full_image.width(), full_image.height()) <= images.FULL_IMAGE_MAX_DIMENSION

    thumb_image = QImage(str(thumb_path))
    assert max(thumb_image.width(), thumb_image.height()) <= images.THUMBNAIL_MAX_DIMENSION


def test_save_product_image_does_not_upscale_small_image(qapp, fake_appdata, tmp_path):
    source = tmp_path / "small.png"
    _make_test_image(source, 50, 50)

    file_name = images.save_product_image(source)
    full_image = QImage(str(images.images_dir() / file_name))
    assert full_image.width() == 50
    assert full_image.height() == 50


def test_save_product_image_never_trusts_original_file_name(qapp, fake_appdata, tmp_path):
    source = tmp_path / "../../etc/passwd.png"
    source.parent.mkdir(parents=True, exist_ok=True)
    _make_test_image(source, 10, 10)

    file_name = images.save_product_image(source)
    assert "passwd" not in file_name
    assert ".." not in file_name


def test_rejects_non_image_file(qapp, fake_appdata, tmp_path):
    bogus = tmp_path / "not_an_image.jpg"
    bogus.write_bytes(b"this is not an image, just text bytes")

    with pytest.raises(images.InvalidImageError):
        images.save_product_image(bogus)


def test_delete_product_image_removes_both_files(qapp, fake_appdata, tmp_path):
    source = tmp_path / "source.png"
    _make_test_image(source, 100, 100)
    file_name = images.save_product_image(source)

    assert (images.images_dir() / file_name).exists()
    assert (images.thumbs_dir() / file_name).exists()

    images.delete_product_image(file_name)

    assert not (images.images_dir() / file_name).exists()
    assert not (images.thumbs_dir() / file_name).exists()


def test_load_thumbnail_pixmap_returns_none_for_missing_file(qapp, fake_appdata):
    assert images.load_thumbnail_pixmap(None) is None
    assert images.load_thumbnail_pixmap("does_not_exist.jpg") is None


def test_load_thumbnail_pixmap_caches(qapp, fake_appdata, tmp_path):
    source = tmp_path / "source.png"
    _make_test_image(source, 100, 100)
    file_name = images.save_product_image(source)

    first = images.load_thumbnail_pixmap(file_name)
    second = images.load_thumbnail_pixmap(file_name)
    assert first is not None
    assert first is second  # served from cache, not reloaded from disk
