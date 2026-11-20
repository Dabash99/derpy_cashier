"""Filesystem locations for app data, kept out of the install folder.

Windows 7 and 10 both expose %APPDATA% (Roaming); using it means the app
works for whichever Windows user account runs it without needing admin
rights to write files.

Every function here is the ONLY place in the codebase allowed to read
%APPDATA%/%USERPROFILE% (or their override env vars) -- see
tests/test_policy.py's "no real user paths outside paths.py" guard. Two
env vars let tests, tools/preview_screens.py, --selftest, and build
checks redirect every path this module computes without ever touching
the real %APPDATA%\\Derby or Documents\\Derby:

- DERBY_DATA_DIR overrides app_data_dir() (normally %APPDATA%\\Derby).
- DERBY_DOCS_DIR overrides the Documents\\Derby parent used by
  default_backup_dir()/default_export_dir().

Because these are read fresh on every call (never cached at import time),
setting the env var once at process start redirects every call site,
including ones that did `from derby.core.utils.paths import
default_backup_dir` and bound that name into their own module.
"""
from __future__ import annotations

import os
from pathlib import Path

APP_FOLDER_NAME = "Derby"


def app_data_dir() -> Path:
    """Return %APPDATA%\\Derby (or $DERBY_DATA_DIR), creating it if needed."""
    override = os.environ.get("DERBY_DATA_DIR")
    if override:
        folder = Path(override)
    else:
        appdata = os.environ.get("APPDATA")
        if not appdata:
            # Fallback for non-Windows dev/test environments only.
            appdata = str(Path.home() / "AppData" / "Roaming")
        folder = Path(appdata) / APP_FOLDER_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def database_path() -> Path:
    return app_data_dir() / "derby.db"


def lock_file_path() -> Path:
    return app_data_dir() / "derby.lock"


def _documents_derby_dir() -> Path:
    override = os.environ.get("DERBY_DOCS_DIR")
    if override:
        return Path(override)
    documents = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Documents"
    return documents / APP_FOLDER_NAME


def default_backup_dir() -> Path:
    """Default primary backup folder: Documents\\Derby\\Backups."""
    return _documents_derby_dir() / "Backups"


def default_export_dir() -> Path:
    """Default folder for report/expenses/sales-log exports: Documents\\Derby\\Exports."""
    return _documents_derby_dir() / "Exports"
