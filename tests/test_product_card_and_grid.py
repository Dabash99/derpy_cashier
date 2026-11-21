"""Covers the redesigned cashier product cards (derby/features/pos/
product_card.py) and the grid that lays them out (product_grid.py),
offscreen per the project's working rules.
"""
from __future__ import annotations

from PySide2.QtGui import QFont, QFontMetrics, QImage

from derby.core.db import categories_repo, products_repo
from derby.features.pos.product_card import ProductCard, wrap_to_lines


def test_wrap_to_lines_never_exceeds_two_lines_and_elides_with_ellipsis(qapp):
    metrics = QFontMetrics(QFont("Arial", 10))
    long_name = "آيس أمريكان كوفي حليب بالكراميل وقطع الشوكولاتة الفاخرة جدا جدا جدا"
    lines = wrap_to_lines(long_name, metrics, 150)
    assert len(lines) <= 2
    assert lines[-1].endswith("…")


def test_wrap_to_lines_short_name_fits_on_one_line_no_ellipsis(qapp):
    metrics = QFontMetrics(QFont("Arial", 10))
    lines = wrap_to_lines("قهوة", metrics, 150)
    assert len(lines) == 1
    assert not lines[0].endswith("…")


def test_wrap_to_lines_handles_a_single_very_long_word_with_no_spaces(qapp):
    metrics = QFontMetrics(QFont("Arial", 10))
    word = "سوبر" * 20
    lines = wrap_to_lines(word, metrics, 150)
    assert len(lines) <= 2
    assert lines[-1].endswith("…")


def test_product_card_with_no_image_shows_placeholder(qapp):
    card = ProductCard("قهوة", 2500, None)
    assert not card._image_label.pixmap().isNull()


def test_product_card_with_missing_image_file_falls_back_to_placeholder(qapp):
    card = ProductCard("قهوة", 2500, "does-not-exist.jpg")
    card.load_image()
    assert not card._image_label.pixmap().isNull()


def test_product_card_with_huge_and_tiny_images_render_at_fixed_card_size(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr("derby.features.menu.images.app_data_dir", lambda: tmp_path)
    from derby.features.menu import images

    huge_source = tmp_path / "huge.png"
    huge_image = QImage(4000, 3000, QImage.Format_RGB32)
    huge_image.fill(0xFF0000)
    huge_image.save(str(huge_source), "PNG")
    huge_file = images.save_product_image(huge_source)

    tiny_source = tmp_path / "tiny.png"
    tiny_image = QImage(4, 4, QImage.Format_RGB32)
    tiny_image.fill(0x00FF00)
    tiny_image.save(str(tiny_source), "PNG")
    tiny_file = images.save_product_image(tiny_source)

    from derby.features.pos.product_card import CARD_WIDTH, IMAGE_HEIGHT

    for file_name in (huge_file, tiny_file):
        card = ProductCard("منتج", 1000, file_name)
        card.load_image()
        pixmap = card._image_label.pixmap()
        assert not pixmap.isNull()
        assert pixmap.width() == CARD_WIDTH
        assert pixmap.height() == IMAGE_HEIGHT


def test_product_card_name_label_never_clips_a_very_long_arabic_name(qapp):
    long_name = "جالكسي حجم كبير مع إضافات كريمة وشوكولاتة ورقائق بسكويت فاخرة جدا"
    card = ProductCard(long_name, 2500, None)
    text = card._name_label.text()
    assert text.count("\n") <= 1  # at most 2 lines


def test_product_card_long_price_renders_without_error(qapp):
    card = ProductCard("منتج", 99999999, None)
    assert "ج.م" in card._price_label.text()


def test_product_grid_builds_with_many_category_chips(qapp, db_conn):
    for index in range(15):
        categories_repo.create_category(db_conn, "قسم {0}".format(index))
    from derby.features.pos.product_grid import ProductGrid

    grid = ProductGrid(db_conn)
    assert grid._chips_layout.count() >= 16  # 15 categories + "الكل" (+ stretch)


def test_product_grid_handles_products_with_edge_case_names_and_prices(qapp, db_conn):
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    products_repo.create_product(db_conn, category_id, "آيس أمريكان كوفي حليب", "", 2500)
    products_repo.create_product(db_conn, category_id, "جالكسي حجم كبير", "", 15000)
    products_repo.create_product(
        db_conn, category_id, "اسم طويل جدا جدا جدا جدا جدا جدا جدا جدا جدا جدا جدا", "", 99999999
    )

    from derby.features.pos.product_grid import ProductGrid

    grid = ProductGrid(db_conn)
    assert len(grid._cards) == 3


def test_product_grid_click_emits_product_id(qapp, db_conn):
    category_id = categories_repo.create_category(db_conn, "مشروبات")
    product_id = products_repo.create_product(db_conn, category_id, "قهوة", "", 2500)

    from derby.features.pos.product_grid import ProductGrid

    grid = ProductGrid(db_conn)
    received = []
    grid.product_clicked.connect(received.append)
    grid._cards[0].clicked.emit()
    assert received == [product_id]
