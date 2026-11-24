"""Windows-only DLL search path setup, applied before PySide2 is ever
imported (see derby/__main__.py, which calls ensure_win_dll_search_paths()
before importing derby.app or derby.core.selftest).

On Windows 7 without KB2533623, AddDllDirectory is missing from
kernel32.dll, so the real os.add_dll_directory() raises
"OSError: [WinError 127] The specified procedure could not be found".
PySide2\\__init__.py calls os.add_dll_directory() unconditionally at
import time (_setupQtDirectories()), so that OSError crashes the app
before a single line of derby code runs. _patch_add_dll_directory()
makes that call degrade gracefully instead, by falling back to the
pre-Windows-8 way of extending the DLL search path: prepending to PATH.
"""
from __future__ import annotations

import os
import sys


class _NullDllDirectoryCookie:
    """Stands in for the object os.add_dll_directory() normally returns,
    whose only documented use is `cookie.close()` or as a context manager
    (`with os.add_dll_directory(...):`). PATH changes made by the fallback
    below are not undone on close() -- same lifetime as the real call
    would have for the process, since nothing in this codebase or PySide2
    relies on the directory being removed again."""

    def close(self) -> None:
        pass

    def __enter__(self) -> _NullDllDirectoryCookie:
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False


def _patch_add_dll_directory() -> None:
    original_add_dll_directory = getattr(os, "add_dll_directory", None)
    if original_add_dll_directory is None:
        # Not on a Windows build of Python at all -- nothing to patch.
        return

    def _safe_add_dll_directory(path: os.PathLike) -> object:
        try:
            return original_add_dll_directory(path)
        except OSError:
            path_str = os.fspath(path)
            os.environ["PATH"] = path_str + os.pathsep + os.environ.get("PATH", "")
            return _NullDllDirectoryCookie()

    os.add_dll_directory = _safe_add_dll_directory


def _app_root_dirs() -> list:
    """The app's own install directory, plus the PySide2 and shiboken2
    subfolders PyInstaller's one-dir build places inside it (Qt DLLs and
    shiboken2's own DLL live there, not in the install root) -- see
    derby/core/utils/resource_path.py for the same frozen-vs-source
    distinction. Returns [] when running from source, since the normal
    import machinery already finds these via the real site-packages."""
    if not getattr(sys, "frozen", False):
        return []
    app_root = os.path.dirname(os.path.abspath(sys.executable))
    candidates = [app_root, os.path.join(app_root, "PySide2"), os.path.join(app_root, "shiboken2")]
    return [path for path in candidates if os.path.isdir(path)]


def ensure_win_dll_search_paths() -> None:
    _patch_add_dll_directory()
    for directory in _app_root_dirs():
        os.environ["PATH"] = directory + os.pathsep + os.environ.get("PATH", "")
        os.add_dll_directory(directory)  # patched above -- never raises
