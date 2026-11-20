"""Dev-time ONLY asset pipeline. Renders:

  - assets/logo/Derby_Logo.svg into assets/brand/ as transparent PNGs,
    plus cream/black/amber background-composited convenience files, at
    the sizes the UI needs.
  - A cropped "icon-only mark" (viewfinder brackets + bean, no wordmark),
    found by scanning the rendered raster for ink/gap bands rather than
    hand-picked pixel coordinates, since the source SVG has no group that
    marks this region on its own.
  - The hand-drawn line-icon set in tools/icon_defs.py, pre-rendered to
    PNG in a dark-stroke and a light-stroke variant.
  - An optional low-contrast coffee-bean texture PNG for the login
    background only.

This is the ONLY regeneration path for assets/brand/ -- never hand-edit
its output. It needs QtSvg, which is why it lives in tools/ and not in
derby/: the shipped app loads only these pre-rendered PNGs via
QIcon/QPixmap, never SVG, at runtime (see CLAUDE.md hard constraint 4
and tests/test_policy.py).

Usage:
    .venv\\Scripts\\python.exe tools\\render_assets.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from icon_defs import ICONS, icon_svg  # noqa: E402
from PySide2.QtCore import QByteArray, QRect, QRectF, Qt  # noqa: E402
from PySide2.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide2.QtSvg import QSvgRenderer  # noqa: E402
from PySide2.QtWidgets import QApplication  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SVG_PATH = PROJECT_ROOT / "assets" / "logo" / "Derby_Logo.svg"
OUT_DIR = PROJECT_ROOT / "assets" / "brand"

# Native render resolution for the full logo; every smaller PNG is
# downsampled from this (smooth, high-quality) rather than re-rasterized
# at low resolution directly from the vector, which is simpler and keeps
# every exported size visually consistent with each other.
FULL_RENDER_SIZE = 2048
LOGO_FULL_SIZES = (256, 512, 1024)  # "1x" is the first; "2x" is 2x the previous tier where applicable

ICON_SIZES = (24, 32)  # with an implicit 2x render for each

CREAM = QColor("#FAF6F0")
BLACK = QColor("#0F0F10")
AMBER = QColor("#D98E04")
WHITE = QColor("#FFFFFF")

INK_ALPHA_THRESHOLD = 10


def render_svg_to_image(renderer: QSvgRenderer, size: int) -> QImage:
    image = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return image


def flatten_to_color(image: QImage, color: QColor) -> QImage:
    """Alpha-mask silhouette of `image` filled with one solid color -- used
    where the full-color mark would not have contrast on a background
    (e.g. the amber bean disappearing into an amber background)."""
    out = QImage(image.size(), QImage.Format_ARGB32_Premultiplied)
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.drawImage(0, 0, image)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(out.rect(), color)
    painter.end()
    return out


def composite_on_background(image: QImage, bg: QColor) -> QImage:
    out = QImage(image.size(), QImage.Format_ARGB32_Premultiplied)
    out.fill(bg)
    painter = QPainter(out)
    painter.drawImage(0, 0, image)
    painter.end()
    return out


def _row_has_ink(image: QImage, y: int) -> bool:
    for x in range(0, image.width(), 3):
        if image.pixelColor(x, y).alpha() > INK_ALPHA_THRESHOLD:
            return True
    return False


def _col_has_ink(image: QImage, x: int, y0: int, y1: int) -> bool:
    for y in range(y0, y1 + 1, 3):
        if image.pixelColor(x, y).alpha() > INK_ALPHA_THRESHOLD:
            return True
    return False


def find_icon_mark_bbox(image: QImage) -> QRect:
    """The icon mark (brackets + bean) is the topmost ink band in the
    full lockup, separated from the DERBY wordmark below it by a blank
    gap. Found by scanning rows/columns for ink, not hand-picked
    coordinates, so it stays correct if the source SVG is ever replaced."""
    h = image.height()
    ink_rows = [_row_has_ink(image, y) for y in range(h)]
    y0 = next(y for y, ink in enumerate(ink_rows) if ink)
    y1 = y0
    gap = 0
    gap_threshold = int(h * 0.02)
    for y in range(y0, h):
        if ink_rows[y]:
            y1 = y
            gap = 0
        else:
            gap += 1
            if gap > gap_threshold:
                break
    xs_with_ink = [x for x in range(image.width()) if _col_has_ink(image, x, y0, y1)]
    x0, x1 = xs_with_ink[0], xs_with_ink[-1]
    pad = int((x1 - x0) * 0.06)
    left = max(0, x0 - pad)
    top = max(0, y0 - pad)
    right = min(image.width(), x1 + pad)
    bottom = min(image.height(), y1 + pad)
    return QRect(left, top, right - left, bottom - top)


def save(image: QImage, name: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / name
    ok = image.save(str(path), "PNG")
    if not ok:
        raise RuntimeError("Failed to save {0}".format(path))
    print("wrote {0} ({1}x{2})".format(path.relative_to(PROJECT_ROOT), image.width(), image.height()))


def render_logo_assets() -> None:
    if not SVG_PATH.exists():
        print("MISSING: {0} -- cannot render logo assets.".format(SVG_PATH))
        return
    renderer = QSvgRenderer(str(SVG_PATH))
    if not renderer.isValid():
        print("STOP: {0} failed to parse as SVG -- cannot render logo assets.".format(SVG_PATH))
        return

    full_color = render_svg_to_image(renderer, FULL_RENDER_SIZE)
    mono_black = flatten_to_color(full_color, BLACK)
    mono_white = flatten_to_color(full_color, WHITE)

    icon_bbox = find_icon_mark_bbox(full_color)

    for size in LOGO_FULL_SIZES:
        save(full_color.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation), "logo-full-transparent-{0}.png".format(size))
        save(
            composite_on_background(full_color, CREAM).scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation),
            "logo-full-on-cream-{0}.png".format(size),
        )
        save(
            composite_on_background(mono_white, BLACK).scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation),
            "logo-full-on-black-{0}.png".format(size),
        )
        save(
            composite_on_background(mono_black, AMBER).scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation),
            "logo-full-on-amber-{0}.png".format(size),
        )

    for variant_name, source in (("transparent", full_color), ("mono-black", mono_black), ("mono-white", mono_white)):
        cropped = source.copy(icon_bbox)
        for size in (32, 48, 64, 128, 256, 512):
            save(
                cropped.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation),
                "icon-mark-{0}-{1}.png".format(variant_name, size),
            )


def render_icon_set() -> None:
    icons_out = OUT_DIR / "icons"
    icons_out.mkdir(parents=True, exist_ok=True)
    variants = {"dark": "#0F0F10", "light": "#FAF6F0"}
    for name in ICONS:
        for variant, stroke in variants.items():
            svg_text = icon_svg(name, stroke)
            renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
            if not renderer.isValid():
                print("STOP: icon {0!r} failed to parse as SVG.".format(name))
                continue
            for size in ICON_SIZES:
                for scale, suffix in ((1, "1x"), (2, "2x")):
                    px = size * scale
                    image = render_svg_to_image(renderer, px)
                    path = icons_out / "{0}-{1}-{2}-{3}.png".format(name, variant, size, suffix)
                    ok = image.save(str(path), "PNG")
                    if not ok:
                        raise RuntimeError("Failed to save {0}".format(path))
        print("wrote icons/{0}-{{dark,light}}-{{24,32}}-{{1x,2x}}.png".format(name))


def render_login_texture() -> None:
    """A single low-contrast coffee-bean motif, tiled by the login screen
    itself at paint time (not here) -- this renders one bean tile, cream
    on cream, barely visible, never competing with the login form."""
    if not SVG_PATH.exists():
        return
    renderer = QSvgRenderer(str(SVG_PATH))
    if not renderer.isValid():
        return
    full_color = render_svg_to_image(renderer, FULL_RENDER_SIZE)
    bbox = find_icon_mark_bbox(full_color)
    # The bean itself is the right-hand two-thirds of the icon mark
    # (the brackets are the outer frame); crop a square from the bean's
    # own bounding region within that band for a clean repeatable tile.
    bean_side = int(bbox.height() * 0.62)
    bean_rect = QRect(bbox.center().x() - bean_side // 2, bbox.top() + int(bbox.height() * 0.12), bean_side, bean_side)
    bean_rect = bean_rect.intersected(full_color.rect())
    mono_cream_on_cream_source = flatten_to_color(full_color, QColor(CREAM.red() - 10, CREAM.green() - 14, CREAM.blue() - 18, 18))
    # A bigger tile (fewer repeats across the login screen's width) reads
    # as a faint motif rather than a busy, obviously-repeating wallpaper.
    tile = mono_cream_on_cream_source.copy(bean_rect).scaled(220, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    save(tile, "login-texture-bean-tile.png")


def main() -> int:
    app = QApplication.instance() or QApplication([])
    _ = app
    render_logo_assets()
    render_icon_set()
    render_login_texture()
    return 0


if __name__ == "__main__":
    sys.exit(main())
