"""One-time cache clear for exactly the 1.0.0 -> 1.1.0 upgrade.

Phase 9 changed enough (new modules, three migrations) that a stale
compiled-Python cache from the 1.0.0 build could, in principle, shadow
the new code. This clears __pycache__/*.pyc (plus the dev-only
.pytest_cache/.ruff_cache, if present) exactly once: on the first
launch after upgrading from the already-released 1.0.0 build to this
one. It must never run again on any later update -- see
docs/FIX_TZ_CACHE_REPORT.md.

Works for both launch paths this project has (see resource_path.py):
running from source via run.bat, and the frozen one-dir PyInstaller
build -- both end up calling clear_cache_once_after_1_0_0_upgrade()
from derby.app.main(), and both use project_root() to find "next to
the app" the same way resource_path() already does for bundled assets.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

import derby
from derby.core.utils.resource_path import project_root

MARKER_FILE_NAME = ".cache_cleared_for"

# The exact one-time transition this clears: the already-released 1.0.0
# build (no marker file exists for it) upgrading to THIS version. A
# future release (e.g. 1.2.0) ships with this same module unchanged,
# but TARGET_VERSION stays "1.1.0" -- so on 1.2.0 the version check
# below is false and nothing is ever cleared again, even in the
# (should-never-happen) case the marker was somehow lost.
HANDLED_UPGRADE_FROM_VERSION = "1.0.0"
TARGET_VERSION = "1.1.0"

_EXCLUDED_DIR_NAMES = {".venv", ".git", "build", "dist"}
_DEV_TOOL_CACHE_DIR_NAMES = (".pytest_cache", ".ruff_cache")


def marker_path(root: Optional[Path] = None) -> Path:
    return (root or project_root()) / MARKER_FILE_NAME


def _is_excluded(path: Path, root: Path) -> bool:
    try:
        relative_parts = path.relative_to(root).parts
    except ValueError:
        return True
    return any(part in _EXCLUDED_DIR_NAMES for part in relative_parts)


def _clear_compiled_python_caches(root: Path) -> None:
    for pycache_dir in root.rglob("__pycache__"):
        if pycache_dir.is_dir() and not _is_excluded(pycache_dir, root):
            shutil.rmtree(pycache_dir, ignore_errors=True)
    for pyc_file in root.rglob("*.pyc"):
        if pyc_file.is_file() and not _is_excluded(pyc_file, root):
            try:
                pyc_file.unlink()
            except OSError:
                pass
    for dev_cache_name in _DEV_TOOL_CACHE_DIR_NAMES:
        dev_cache_dir = root / dev_cache_name
        if dev_cache_dir.is_dir():
            shutil.rmtree(dev_cache_dir, ignore_errors=True)


def clear_cache_once_after_1_0_0_upgrade(root: Optional[Path] = None, current_version: Optional[str] = None) -> bool:
    """Returns True the one time it actually clears (so the caller can
    print the one short status line); False every other time (marker
    already present, or this isn't the 1.0.0-to-1.1.0 transition)."""
    root = root or project_root()
    current_version = current_version if current_version is not None else derby.__version__
    if current_version != TARGET_VERSION:
        return False
    marker = marker_path(root)
    if marker.exists():
        return False  # already handled once -- never clear again
    _clear_compiled_python_caches(root)
    try:
        marker.write_text(current_version, encoding="utf-8")
    except OSError:
        pass
    return True
