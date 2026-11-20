"""Dev-time ONLY (Part B4). Builds the two wizard images Inno Setup
needs for installer/derby.iss, from the A1 brand renders. Inno Setup
requires BMP specifically (WizardImageFile/WizardSmallImageFile), not
PNG, hence this separate tool rather than reusing render_assets.py's
PNG output directly.

  - installer/wizard-image.bmp: 164x314, full logo on black (the large
    image shown down the left side of the wizard).
  - installer/wizard-small-image.bmp: 55x55, the icon mark on a white
    background (the small top-right banner image).

Usage:
    .venv\\Scripts\\python.exe tools\\make_installer_images.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide2.QtCore import QPoint, Qt  # noqa: E402
from PySide2.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide2.QtWidgets import QApplication  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BRAND_DIR = PROJECT_ROOT / "assets" / "brand"
OUT_DIR = PROJECT_ROOT / "installer"

JET_BLACK = QColor("#0F0F10")
WHITE = QColor("#FFFFFF")


def _centered(canvas_size, source: QImage, max_fraction: float = 0.8) -> QImage:
    width, height = canvas_size
    canvas = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
    canvas.fill(Qt.transparent)
    max_w, max_h = int(width * max_fraction), int(height * max_fraction)
    scaled = source.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.Antialiasing)
    offset = QPoint((width - scaled.width()) // 2, (height - scaled.height()) // 2)
    painter.drawImage(offset, scaled)
    painter.end()
    return canvas


def _flatten_onto(image: QImage, background: QColor) -> QImage:
    out = QImage(image.size(), QImage.Format_RGB32)
    out.fill(background)
    painter = QPainter(out)
    painter.drawImage(0, 0, image)
    painter.end()
    return out


def build_wizard_image() -> None:
    logo_path = BRAND_DIR / "logo-full-transparent-512.png"
    logo = QImage(str(logo_path))
    if logo.isNull():
        raise RuntimeError("missing {0} -- run tools/render_assets.py first".format(logo_path))
    # Flatten white/colored logo pixels onto black first (so a dark
    # wordmark stays legible), THEN composite onto the final canvas --
    # matches the "on black" variant render_assets.py already produces.
    mono_white_path = BRAND_DIR / "icon-mark-mono-white-512.png"
    full_on_black_path = BRAND_DIR / "logo-full-on-black-512.png"
    source = QImage(str(full_on_black_path)) if full_on_black_path.exists() else logo
    centered = _centered((164, 314), source, max_fraction=0.72)
    final = _flatten_onto(centered, JET_BLACK)
    out_path = OUT_DIR / "wizard-image.bmp"
    final.save(str(out_path), "BMP")
    print("wrote {0} ({1}x{2})".format(out_path.relative_to(PROJECT_ROOT), final.width(), final.height()))
    _ = mono_white_path  # kept for reference; full_on_black already includes the mark


def build_wizard_small_image() -> None:
    mark_path = BRAND_DIR / "icon-mark-mono-black-256.png"
    mark = QImage(str(mark_path))
    if mark.isNull():
        raise RuntimeError("missing {0} -- run tools/render_assets.py first".format(mark_path))
    centered = _centered((55, 55), mark, max_fraction=0.82)
    final = _flatten_onto(centered, WHITE)
    out_path = OUT_DIR / "wizard-small-image.bmp"
    final.save(str(out_path), "BMP")
    print("wrote {0} ({1}x{2})".format(out_path.relative_to(PROJECT_ROOT), final.width(), final.height()))


def main() -> int:
    app = QApplication.instance() or QApplication([])
    _ = app
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    build_wizard_image()
    build_wizard_small_image()
    return 0


if __name__ == "__main__":
    sys.exit(main())
