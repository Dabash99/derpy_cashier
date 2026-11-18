"""Loads the bundled Cairo font from disk — never from the internet.

Qt's variable-font support is inconsistent on Windows 7's font backend, so
we ship static weight files (Regular/SemiBold/Bold) instead of the newer
variable-font release of Cairo.
"""
from __future__ import annotations

from pathlib import Path

from PySide2.QtGui import QFontDatabase

_FONT_FILES = ("Cairo-Regular.ttf", "Cairo-SemiBold.ttf", "Cairo-Bold.ttf")
FONT_FAMILY = "Cairo"


def _assets_fonts_dir() -> Path:
    # derby/core/theme/fonts.py -> project root is three parents up.
    return Path(__file__).resolve().parents[3] / "assets" / "fonts"


def load_bundled_fonts() -> None:
    fonts_dir = _assets_fonts_dir()
    for file_name in _FONT_FILES:
        font_path = fonts_dir / file_name
        if font_path.exists():
            QFontDatabase.addApplicationFont(str(font_path))
