"""Code-level checks for A2's RTL/typography requirements: the bundled
Cairo font actually registers (not silently falling back to a system
font with no Arabic glyphs), and Arabic text has real width/shaping
through it. A pixel-level render check lives in tools/preview_screens.py
(A4); this is the part that can run in every `pytest` invocation."""
from __future__ import annotations

from PySide2.QtGui import QFont, QFontDatabase, QFontInfo, QFontMetrics

from derby.core.theme import fonts

ARABIC_SAMPLE = "مرحباً بك في ديربي"  # has initial/medial/final letterforms + a hamza


def test_cairo_registers_as_its_own_family(qapp):
    fonts.load_bundled_fonts()
    assert fonts.CAIRO_FAMILY in QFontDatabase().families()


def test_cairo_font_exact_match_and_renders_arabic_with_nonzero_width(qapp):
    fonts.load_bundled_fonts()
    font = QFont(fonts.CAIRO_FAMILY, 15)
    info = QFontInfo(font)
    assert info.family() == fonts.CAIRO_FAMILY, "Cairo did not register as an exact match -- Qt substituted another font"

    metrics = QFontMetrics(font)
    rect = metrics.boundingRect(ARABIC_SAMPLE)
    assert rect.width() > 0
    assert metrics.horizontalAdvance(ARABIC_SAMPLE) > 0


def test_app_sets_right_to_left_layout_direction():
    import inspect

    from derby import app as app_module

    source = inspect.getsource(app_module.main)
    assert "Qt.RightToLeft" in source
