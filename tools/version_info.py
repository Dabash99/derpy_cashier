"""Builds the Windows EXE version-info resource (product name, version,
copyright) for derby.spec, from derby.__version__ -- the one place the
version lives (see CLAUDE.md). Dev-time/build-time only; never shipped.
"""
from __future__ import annotations

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)


def _version_tuple(version: str):
    parts = [int(p) for p in version.split(".")]
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts[:4])


def build_version_info(version: str) -> VSVersionInfo:
    file_version = _version_tuple(version)
    return VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=file_version,
            prodvers=file_version,
            mask=0x3F,
            flags=0x0,
            OS=0x4,  # VOS_NT
            fileType=0x1,  # VFT_APP
            subtype=0x0,
            date=(0, 0),
        ),
        kids=[
            StringFileInfo(
                [
                    StringTable(
                        "040904B0",  # US English, Unicode
                        [
                            StringStruct("CompanyName", "Derby"),
                            StringStruct("FileDescription", "Derby - Cafe POS"),
                            StringStruct("FileVersion", version),
                            StringStruct("InternalName", "Derby"),
                            StringStruct("LegalCopyright", "Derby"),
                            StringStruct("OriginalFilename", "Derby.exe"),
                            StringStruct("ProductName", "Derby"),
                            StringStruct("ProductVersion", version),
                        ],
                    )
                ]
            ),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )
