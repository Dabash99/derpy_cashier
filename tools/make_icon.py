"""Dev-time ONLY (Part B2). Builds assets/derby.ico -- a real
multi-resolution Windows icon (16/24/32/48/64/128/256px) -- from the
icon-only mark rendered in A1 (assets/brand/icon-mark-mono-black-*.png).
Also writes a plain 256px PNG for the window/taskbar icon (QIcon already
has its own PNG loader for that -- see derby/core/theme/icons.py -- this
copy is for build tooling/documentation convenience).

Qt's own ICO writer (QImageWriter) only ever keeps the LAST image
written, not a true multi-resolution directory (verified by hand before
writing this script) -- so the .ico file is assembled directly here:
a standard ICONDIR header + one ICONDIRENTRY per size, each pointing at
a PNG-encoded frame. PNG-compressed ICO frames are valid from Windows
Vista onward (explicitly fine on Windows 7 per this project's target
OSes) and every size here, including 256px, uses one.

Usage:
    .venv\\Scripts\\python.exe tools\\make_icon.py
"""
from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide2.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide2.QtGui import QImage  # noqa: E402
from PySide2.QtWidgets import QApplication  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BRAND_DIR = PROJECT_ROOT / "assets" / "brand"
OUT_ICO_PATH = PROJECT_ROOT / "assets" / "derby.ico"
OUT_WINDOW_PNG_PATH = PROJECT_ROOT / "assets" / "derby-window-icon-256.png"

ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
# icon-mark-mono-black is the single clean solid-color silhouette --
# the right choice for a tiny 16px taskbar/title-bar icon, where the
# full-color mark's fine detail (bean gradient line, brackets) would
# just turn to mush.
SOURCE_SIZES = (32, 48, 64, 128, 256, 512)


def _load_source_image(target_size: int) -> QImage:
    closest = min(SOURCE_SIZES, key=lambda candidate: abs(candidate - target_size))
    path = BRAND_DIR / "icon-mark-mono-black-{0}.png".format(closest)
    image = QImage(str(path))
    if image.isNull():
        raise RuntimeError("missing or unreadable source: {0}".format(path))
    return image


def _square_canvas(image: QImage, size: int) -> QImage:
    """The icon mark is wider than tall (viewfinder brackets); an .ico
    frame must be square, so center it on a transparent square canvas
    rather than stretching it out of proportion."""
    from PySide2.QtCore import QPoint, Qt
    from PySide2.QtGui import QPainter

    scaled = image.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    canvas = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    canvas.fill(Qt.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.Antialiasing)
    offset = QPoint((size - scaled.width()) // 2, (size - scaled.height()) // 2)
    painter.drawImage(offset, scaled)
    painter.end()
    return canvas


def _png_bytes(image: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    data = bytes(buffer.data())
    buffer.close()
    return data


def build_ico(sizes=ICO_SIZES) -> bytes:
    frames = []
    for size in sizes:
        source = _load_source_image(size)
        canvas = _square_canvas(source, size)
        frames.append((size, _png_bytes(canvas)))

    # ICONDIR: reserved(2)=0, type(2)=1 (icon), count(2)=N
    header = struct.pack("<HHH", 0, 1, len(frames))

    entries = b""
    image_data = b""
    offset = len(header) + 16 * len(frames)
    for size, png_bytes in frames:
        # width/height: a byte value of 0 means "256" per the ICO spec.
        dim_byte = 0 if size >= 256 else size
        entry = struct.pack(
            "<BBBBHHII",
            dim_byte,  # width
            dim_byte,  # height
            0,  # color count (0 = no palette, true color)
            0,  # reserved
            1,  # color planes
            32,  # bits per pixel
            len(png_bytes),  # size of this frame's data
            offset,  # offset of this frame's data from file start
        )
        entries += entry
        image_data += png_bytes
        offset += len(png_bytes)

    return header + entries + image_data


def main() -> int:
    app = QApplication.instance() or QApplication([])
    _ = app

    ico_bytes = build_ico()
    OUT_ICO_PATH.write_bytes(ico_bytes)
    print("wrote {0} ({1} bytes, sizes {2})".format(OUT_ICO_PATH.relative_to(PROJECT_ROOT), len(ico_bytes), ICO_SIZES))

    window_source = _load_source_image(256)
    window_canvas = _square_canvas(window_source, 256)
    window_canvas.save(str(OUT_WINDOW_PNG_PATH), "PNG")
    print("wrote {0} ({1}x{2})".format(OUT_WINDOW_PNG_PATH.relative_to(PROJECT_ROOT), window_canvas.width(), window_canvas.height()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
