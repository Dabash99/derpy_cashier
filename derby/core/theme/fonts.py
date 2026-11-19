"""Loads the bundled Cairo and Montserrat fonts from disk — never from the
internet.

Qt's variable-font support is inconsistent on Windows 7's font backend, so
we ship static weight files instead of variable-font releases.

Montserrat's TTF files are NOT fetched by any automated step in this
project (no network access is permitted at all, build-time or runtime).
If they are missing, `load_bundled_fonts()` simply does not register
them -- `montserrat_available()` reports that, and the theme falls back
to Cairo (which does carry Latin glyphs, just not Montserrat's letterforms)
for any Latin/brand text. The app must not crash or look broken either way.
"""
from __future__ import annotations

from pathlib import Path
from typing import Tuple

from PySide2.QtGui import QFont, QFontDatabase

from derby.core.utils.resource_path import resource_path

_CAIRO_FILES = ("Cairo-Regular.ttf", "Cairo-SemiBold.ttf", "Cairo-Bold.ttf")
# Static (non-variable) weights only -- see module docstring.
_MONTSERRAT_FILES = (
    "Montserrat-Regular.ttf",
    "Montserrat-Medium.ttf",
    "Montserrat-SemiBold.ttf",
    "Montserrat-Bold.ttf",
)

CAIRO_FAMILY = "Cairo"
MONTSERRAT_FAMILY = "Montserrat"

# What callers should pass to QFont.setFamilies() for brand/Latin/numeric
# text: Montserrat first, Cairo as the fallback so Arabic text mixed into
# the same label still shapes correctly, then the platform's own default.
LATIN_FONT_FALLBACK_CHAIN = (MONTSERRAT_FAMILY, CAIRO_FAMILY)
ARABIC_FONT_FALLBACK_CHAIN = (CAIRO_FAMILY,)

_montserrat_available = False


def _assets_fonts_dir() -> Path:
    return resource_path("assets", "fonts")


def montserrat_available() -> bool:
    """True once load_bundled_fonts() has found and registered at least
    one Montserrat weight. Lets callers (and tests) assert the real
    typeface is in use rather than silently falling back to Cairo."""
    return _montserrat_available


def missing_montserrat_files() -> Tuple[str, ...]:
    """Which Montserrat files are not present, for a one-time startup log
    line/Settings notice -- never a hard error, since the app must still
    run (with Cairo covering Latin text) if they were never placed."""
    fonts_dir = _assets_fonts_dir()
    return tuple(name for name in _MONTSERRAT_FILES if not (fonts_dir / name).exists())


def latin_numeric_font(point_size: int = -1, bold: bool = True) -> QFont:
    """For big numeric displays (totals, prices, timers) and Latin
    headings: Montserrat first, with Cairo as the fallback family for
    any Arabic glyphs mixed into the same label (e.g. "الإجمالي: 50.00")
    so they still shape correctly even though Montserrat itself carries
    no Arabic glyphs. Works whether or not Montserrat's files are
    actually present -- see the module docstring.

    `point_size` defaults to -1 (leave size untouched), so this can be
    combined with a QSS role like role="title" that already sets the
    size -- only the font family/weight changes here.
    """
    font = QFont()
    font.setFamilies(list(LATIN_FONT_FALLBACK_CHAIN))
    if point_size > 0:
        font.setPointSize(point_size)
    font.setBold(bold)
    return font


def load_bundled_fonts() -> None:
    global _montserrat_available
    fonts_dir = _assets_fonts_dir()
    for file_name in _CAIRO_FILES:
        font_path = fonts_dir / file_name
        if font_path.exists():
            QFontDatabase.addApplicationFont(str(font_path))

    loaded_any_montserrat = False
    for file_name in _MONTSERRAT_FILES:
        font_path = fonts_dir / file_name
        if font_path.exists():
            if QFontDatabase.addApplicationFont(str(font_path)) != -1:
                loaded_any_montserrat = True
    _montserrat_available = loaded_any_montserrat
