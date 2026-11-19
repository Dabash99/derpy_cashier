"""Montserrat is not fetched over the network (see docs/BRAND.md) and is
currently absent from assets/fonts/ -- load_bundled_fonts() must degrade
gracefully rather than error, and report accurately via
montserrat_available()/missing_montserrat_files() either way."""
from __future__ import annotations

import shutil

from derby.core.theme import fonts


def test_cairo_family_and_fallback_chains_are_sane():
    assert fonts.CAIRO_FAMILY == "Cairo"
    assert fonts.MONTSERRAT_FAMILY == "Montserrat"
    assert fonts.LATIN_FONT_FALLBACK_CHAIN == (fonts.MONTSERRAT_FAMILY, fonts.CAIRO_FAMILY)
    assert fonts.ARABIC_FONT_FALLBACK_CHAIN == (fonts.CAIRO_FAMILY,)


def test_load_bundled_fonts_does_not_raise_when_montserrat_is_absent(qapp):
    # Current repo state: Montserrat TTFs were never fetched (no network
    # access is permitted) -- loading must still succeed for Cairo.
    fonts._montserrat_available = False
    fonts.load_bundled_fonts()
    assert fonts.missing_montserrat_files() == (
        "Montserrat-Regular.ttf",
        "Montserrat-Medium.ttf",
        "Montserrat-SemiBold.ttf",
        "Montserrat-Bold.ttf",
    )
    assert fonts.montserrat_available() is False


def test_latin_numeric_font_uses_fallback_chain_and_leaves_size_alone_by_default(qapp):
    font = fonts.latin_numeric_font()
    assert list(font.families()) == list(fonts.LATIN_FONT_FALLBACK_CHAIN)
    assert font.bold() is True


def test_latin_numeric_font_applies_explicit_point_size_when_given(qapp):
    font = fonts.latin_numeric_font(18, bold=False)
    assert font.pointSize() == 18
    assert font.bold() is False


def test_montserrat_available_becomes_true_once_files_are_present(qapp, tmp_path, monkeypatch):
    # Reuse a real, already-bundled TTF (valid font data, just not
    # actually Montserrat) to exercise the registration code path without
    # needing network access to fetch the real typeface.
    fake_fonts_dir = tmp_path / "fonts"
    fake_fonts_dir.mkdir()
    real_cairo_regular = fonts._assets_fonts_dir() / "Cairo-Regular.ttf"
    shutil.copyfile(real_cairo_regular, fake_fonts_dir / "Montserrat-Regular.ttf")

    monkeypatch.setattr(fonts, "_assets_fonts_dir", lambda: fake_fonts_dir)

    fonts._montserrat_available = False
    fonts.load_bundled_fonts()

    assert fonts.montserrat_available() is True
    assert "Montserrat-Regular.ttf" not in fonts.missing_montserrat_files()
    assert set(fonts.missing_montserrat_files()) == {
        "Montserrat-Medium.ttf",
        "Montserrat-SemiBold.ttf",
        "Montserrat-Bold.ttf",
    }
