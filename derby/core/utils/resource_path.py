"""Resolves bundled asset paths (fonts, logo, icons) so the same code
works both running from source and from a PyInstaller one-dir frozen
build (Phase 8/Part B): a frozen build sets `sys.frozen = True` and
extracts bundled data next to the executable (one-dir, not one-file, so
there is no _MEIPASS temp-extraction step at runtime -- data files sit
in the dist folder beside Derby.exe).
"""
from __future__ import annotations

import sys
from pathlib import Path


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        # One-dir build: bundled data sits next to the executable, not in
        # a temp extraction folder (that's one-file mode, which this
        # project does not use -- see tools/build.py).
        return Path(sys.executable).resolve().parent
    # derby/core/utils/resource_path.py -> project root is three parents up.
    return Path(__file__).resolve().parents[3]


def resource_path(*parts: str) -> Path:
    return project_root().joinpath(*parts)
