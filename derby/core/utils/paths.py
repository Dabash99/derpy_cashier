"""Filesystem locations for app data, kept out of the install folder.

Windows 7 and 10 both expose %APPDATA% (Roaming); using it means the app
works for whichever Windows user account runs it without needing admin
rights to write files.
"""
from __future__ import annotations

import os
from pathlib import Path

APP_FOLDER_NAME = "Derby"


def app_data_dir() -> Path:
    """Return %APPDATA%\\Derby, creating it if it does not exist yet."""
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


def default_backup_dir() -> Path:
    """Default primary backup folder: Documents\\Derby\\Backups."""
    documents = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Documents"
    return documents / APP_FOLDER_NAME / "Backups"
