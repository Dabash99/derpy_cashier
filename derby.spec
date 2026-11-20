# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Derby -- Part B3.

ONE-DIR (not one-file: faster startup, easier to inspect/verify), no
UPX (UPX-packed binaries are a common false-positive trigger for AV on
a cafe PC, and this app is not large enough to need the size saving),
windowed (console=False -- this is a GUI app).

Run via tools/build.py, not `pyinstaller derby.spec` directly -- the
wrapper runs ruff + the full test suite + policy tests first (abort on
any failure), and verifies the frozen output afterward (--selftest,
size/DLL checks, SHA-256).
"""
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

PROJECT_ROOT = Path(SPECPATH)  # noqa: F821 -- SPECPATH is injected by PyInstaller
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

import derby  # noqa: E402
from version_info import build_version_info  # noqa: E402

block_cipher = None

# Only QtCore/QtGui/QtWidgets are used anywhere in derby/ (see
# CLAUDE.md hard constraint 4 and tests/test_policy.py) -- every other
# Qt module PySide2 ships is excluded so it is never even extracted into
# dist/Derby. platforms/qwindows, imageformats, and styles plugins are
# NOT excluded -- the app needs them to run at all.
EXCLUDED_MODULES = [
    "PySide2.QtWebEngineCore",
    "PySide2.QtWebEngineWidgets",
    "PySide2.QtWebEngine",
    "PySide2.Qt3DCore",
    "PySide2.Qt3DRender",
    "PySide2.Qt3DInput",
    "PySide2.Qt3DLogic",
    "PySide2.Qt3DAnimation",
    "PySide2.Qt3DExtras",
    "PySide2.QtMultimedia",
    "PySide2.QtMultimediaWidgets",
    "PySide2.QtQml",
    "PySide2.QtQuick",
    "PySide2.QtQuickWidgets",
    "PySide2.QtQuickControls2",
    "PySide2.QtNetwork",
    "PySide2.QtSql",
    "PySide2.QtCharts",
    "PySide2.QtDataVisualization",
    "PySide2.QtSvg",
    "PySide2.QtSvgWidgets",
    "PySide2.QtWebSockets",
    "PySide2.QtPositioning",
    "PySide2.QtLocation",
    "PySide2.QtSensors",
    "PySide2.QtSerialPort",
    "PySide2.QtBluetooth",
    "PySide2.QtNfc",
    "PySide2.QtTest",
    "PySide2.QtHelp",
    "PySide2.QtDesigner",
    "PySide2.QtXmlPatterns",
    "PySide2.QtRemoteObjects",
    "PySide2.QtScxml",
    "PySide2.QtWebChannel",
    "PySide2.QtOpenGL",
    "PySide2.QtPrintSupport",
    "tkinter",
    "unittest",
    "pytest",
    "pydoc",
]

datas = [(str(PROJECT_ROOT / "assets"), "assets")]
datas += collect_data_files("tzdata")
datas += collect_data_files("backports.zoneinfo")
datas += collect_data_files("openpyxl")
datas += collect_data_files("et_xmlfile")

a = Analysis(
    [str(PROJECT_ROOT / "derby" / "__main__.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=["backports.zoneinfo", "et_xmlfile", "openpyxl.cell._writer"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDED_MODULES,
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Derby",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_ROOT / "assets" / "derby.ico"),
    version=build_version_info(derby.__version__),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Derby",
)
