"""Sanity checks for the generated assets/brand/ pipeline output -- not a
re-render (that needs QtSvg and tools/render_assets.py, dev-time only),
just proof the committed PNGs exist, are non-empty, and are the sizes the
UI expects. If this fails, re-run:
    .venv\\Scripts\\python.exe tools\\render_assets.py
"""
from __future__ import annotations

from pathlib import Path

from PySide2.QtGui import QImage

from tools.icon_defs import ICONS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BRAND_DIR = PROJECT_ROOT / "assets" / "brand"
ICONS_DIR = BRAND_DIR / "icons"

LOGO_FULL_SIZES = (256, 512, 1024)
LOGO_FULL_VARIANTS = ("transparent", "on-cream", "on-black", "on-amber")
ICON_MARK_SIZES = (32, 48, 64, 128, 256, 512)
ICON_MARK_VARIANTS = ("transparent", "mono-black", "mono-white")
HAND_ICON_SIZES = (24, 32)
HAND_ICON_VARIANTS = ("dark", "light")
HAND_ICON_SCALES = ("1x", "2x")


def _assert_png_ok(path: Path, expected_longest_side: int) -> None:
    assert path.exists(), "missing generated asset: {0}".format(path.relative_to(PROJECT_ROOT))
    assert path.stat().st_size > 0, "{0} is empty".format(path.relative_to(PROJECT_ROOT))
    image = QImage(str(path))
    assert not image.isNull(), "{0} failed to load as an image".format(path.relative_to(PROJECT_ROOT))
    assert max(image.width(), image.height()) == expected_longest_side


def test_logo_full_variants_present_at_every_size():
    for size in LOGO_FULL_SIZES:
        for variant in LOGO_FULL_VARIANTS:
            _assert_png_ok(BRAND_DIR / "logo-full-{0}-{1}.png".format(variant, size), size)


def test_icon_mark_variants_present_at_every_size():
    for size in ICON_MARK_SIZES:
        for variant in ICON_MARK_VARIANTS:
            _assert_png_ok(BRAND_DIR / "icon-mark-{0}-{1}.png".format(variant, size), size)


def test_icon_mark_is_wider_than_tall_and_not_clipped():
    """The icon mark is the viewfinder-bracket crop, not the full square
    lockup -- it should be noticeably wider than the full logo's 1:1
    aspect ratio, and must not be a degenerate (near-zero) crop."""
    image = QImage(str(BRAND_DIR / "icon-mark-transparent-512.png"))
    assert image.width() > 0 and image.height() > 0
    aspect = image.width() / image.height()
    assert 1.0 < aspect < 1.6, "icon mark aspect ratio {0:.2f} looks like a bad crop".format(aspect)


def test_hand_drawn_icon_set_present_for_every_name_variant_size_scale():
    for name in ICONS:
        for variant in HAND_ICON_VARIANTS:
            for size in HAND_ICON_SIZES:
                for scale_label, scale in (("1x", 1), ("2x", 2)):
                    path = ICONS_DIR / "{0}-{1}-{2}-{3}.png".format(name, variant, size, scale_label)
                    _assert_png_ok(path, size * scale)


def test_login_texture_present():
    path = BRAND_DIR / "login-texture-bean-tile.png"
    assert path.exists()
    image = QImage(str(path))
    assert not image.isNull()
    assert image.hasAlphaChannel()


def test_logo_variants_are_actually_transparent_or_opaque_as_named():
    transparent = QImage(str(BRAND_DIR / "logo-full-transparent-256.png"))
    assert transparent.hasAlphaChannel()
    on_cream = QImage(str(BRAND_DIR / "logo-full-on-cream-256.png"))
    assert on_cream.pixelColor(0, 0).name().lower() in ("#faf6f0",)
