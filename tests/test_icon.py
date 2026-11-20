"""Sanity checks for the generated assets/derby.ico -- not a re-render
(that needs Qt image I/O and tools/make_icon.py, dev-time only), just
proof the committed file is a well-formed multi-resolution Windows icon.
If this fails, re-run:
    .venv\\Scripts\\python.exe tools\\make_icon.py
"""
from __future__ import annotations

import struct
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ICO_PATH = PROJECT_ROOT / "assets" / "derby.ico"
WINDOW_PNG_PATH = PROJECT_ROOT / "assets" / "derby-window-icon-256.png"

EXPECTED_SIZES = (16, 24, 32, 48, 64, 128, 256)


def _parse_ico_directory(data: bytes):
    reserved, type_, count = struct.unpack("<HHH", data[:6])
    assert reserved == 0
    assert type_ == 1  # 1 = icon (not 2 = cursor)
    entries = []
    offset = 6
    for _ in range(count):
        width, height, _colors, _res, planes, bpp, size, image_offset = struct.unpack(
            "<BBBBHHII", data[offset : offset + 16]
        )
        entries.append(
            {
                "width": width or 256,
                "height": height or 256,
                "planes": planes,
                "bpp": bpp,
                "size": size,
                "offset": image_offset,
            }
        )
        offset += 16
    return entries


def test_ico_file_exists_and_is_nonempty():
    assert ICO_PATH.exists()
    assert ICO_PATH.stat().st_size > 0


def test_ico_has_every_expected_size_with_valid_frame_data():
    data = ICO_PATH.read_bytes()
    entries = _parse_ico_directory(data)
    sizes_found = {entry["width"] for entry in entries}
    assert sizes_found == set(EXPECTED_SIZES)

    for entry in entries:
        assert entry["width"] == entry["height"]
        assert entry["bpp"] == 32
        frame_bytes = data[entry["offset"] : entry["offset"] + entry["size"]]
        assert len(frame_bytes) == entry["size"]
        assert frame_bytes.startswith(b"\x89PNG\r\n\x1a\n")  # each frame is PNG-compressed


def test_window_icon_png_present_and_square_256():
    from PySide2.QtGui import QImage

    assert WINDOW_PNG_PATH.exists()
    image = QImage(str(WINDOW_PNG_PATH))
    assert not image.isNull()
    assert image.width() == 256 and image.height() == 256
    assert image.hasAlphaChannel()
