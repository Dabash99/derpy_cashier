"""Receipt image pipeline tests, same synthetic-image approach as
tests/test_images.py (no real photos, offscreen Qt)."""
from __future__ import annotations

import pytest
from PySide2.QtCore import Qt
from PySide2.QtGui import QImage

from derby.features.expenses import receipts


@pytest.fixture()
def fake_appdata(tmp_path, monkeypatch):
    monkeypatch.setattr("derby.features.expenses.receipts.app_data_dir", lambda: tmp_path)
    return tmp_path


def _make_test_image(path, width, height, color=Qt.blue):
    image = QImage(width, height, QImage.Format_RGB32)
    image.fill(color)
    assert image.save(str(path), "PNG")


def test_save_receipt_image_resizes_to_1600(qapp, fake_appdata, tmp_path):
    source = tmp_path / "source.png"
    _make_test_image(source, 4000, 2000)

    file_name = receipts.save_receipt_image(source)

    full_path = receipts.receipts_dir() / file_name
    thumb_path = receipts.thumbs_dir() / file_name
    assert full_path.exists()
    assert thumb_path.exists()

    full_image = QImage(str(full_path))
    assert max(full_image.width(), full_image.height()) <= receipts.FULL_IMAGE_MAX_DIMENSION

    thumb_image = QImage(str(thumb_path))
    assert max(thumb_image.width(), thumb_image.height()) <= receipts.THUMBNAIL_MAX_DIMENSION


def test_save_receipt_image_never_trusts_original_file_name(qapp, fake_appdata, tmp_path):
    source = tmp_path / "source.png"
    _make_test_image(source, 100, 100)
    file_name = receipts.save_receipt_image(source)
    assert file_name != "source.png"
    assert file_name.endswith(".jpg")


def test_rejects_non_image_file(qapp, fake_appdata, tmp_path):
    bogus = tmp_path / "not_an_image.jpg"
    bogus.write_bytes(b"this is not an image, just text bytes")
    with pytest.raises(receipts.InvalidImageError):
        receipts.save_receipt_image(bogus)


def test_load_full_pixmap_returns_none_for_missing_file(qapp, fake_appdata):
    assert receipts.load_full_pixmap(None) is None
    assert receipts.load_full_pixmap("does_not_exist.jpg") is None


def test_load_full_pixmap_after_save(qapp, fake_appdata, tmp_path):
    source = tmp_path / "source.png"
    _make_test_image(source, 100, 100)
    file_name = receipts.save_receipt_image(source)
    pixmap = receipts.load_full_pixmap(file_name)
    assert pixmap is not None
    assert not pixmap.isNull()
