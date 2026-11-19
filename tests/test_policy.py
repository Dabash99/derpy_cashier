"""Guards the project's hard constraints from CLAUDE.md: no networking
anywhere except the one update-check file, no forbidden dependencies, and
no Python 3.9+-only syntax (the app must run on Python 3.8 for Windows 7).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

import derby

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DERBY_DIR = PROJECT_ROOT / "derby"
TOOLS_DIR = PROJECT_ROOT / "tools"
PATHS_FILE = DERBY_DIR / "core" / "utils" / "paths.py"
ALLOWED_NETWORKING_FILE = DERBY_DIR / "core" / "updates" / "update_check.py"
WHATSAPP_FILE = DERBY_DIR / "core" / "integrations" / "whatsapp.py"
# os.startfile/webbrowser.open are a user-initiated hand-off, not a network
# request the app makes on its own -- confined to: the WhatsApp hand-off,
# the "open the download page" button (the one other place that already
# opens an external URL), and the Phase 6 "open containing export folder"
# button (a LOCAL path, not a URL -- kept here rather than treated as a
# networking concern since it never leaves the filesystem).
ALLOWED_STARTFILE_OR_BROWSER_FILES = {
    WHATSAPP_FILE,
    DERBY_DIR / "features" / "settings" / "update_check_panel.py",
    DERBY_DIR / "features" / "reports" / "export_panel.py",
}

FORBIDDEN_DEPENDENCIES = [
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    "websockets",
    "firebase",
    "sentry",
    "supabase",
    "pyside6",
    "pyqt",
]

FORBIDDEN_IMPORT_SUBSTRINGS = [
    "socket",
    "ssl",
    "http.client",
    "urllib.request",
    "urllib3",
    "requests",
    "ftplib",
    "smtplib",
    "xmlrpc",
    "QtNetwork",
    "QtWebEngine",
    "QtWebSockets",
    "QtQml",
    "QtQuick",
    "QtMultimedia",
    "Qt3D",
    "QtCharts",
    "QtSvg",
]

# Real per-user Windows locations. Only derby/core/utils/paths.py is allowed
# to read these -- everything else must go through its functions (and
# honor DERBY_DATA_DIR/DERBY_DOCS_DIR), so a stray module can never leak
# into the real %APPDATA%\Derby or Documents\Derby. See the docstring at
# the top of paths.py and the "Fix: backup_folder_primary leaked into the
# real Documents\Derby folder" commit this guards against.
REAL_USER_PATH_ACCESS_PATTERN = re.compile(
    r'os\.environ(?:\.get)?\s*[\(\[]\s*["\'](APPDATA|USERPROFILE)["\']|os\.getenv\s*\(\s*["\'](APPDATA|USERPROFILE)["\']|Path\.home\(\)'
)

IMPORT_PATTERN = re.compile(r"^\s*(?:import|from)\s+([\w\.]+)", re.MULTILINE)
MATCH_STATEMENT_PATTERN = re.compile(r"^\s*match\s+.+:\s*$", re.MULTILINE)


def _all_derby_py_files():
    return sorted(DERBY_DIR.rglob("*.py"))


def test_requirements_have_no_forbidden_packages():
    for file_name in ("requirements.txt", "requirements-dev.txt"):
        text = (PROJECT_ROOT / file_name).read_text(encoding="utf-8").lower()
        for forbidden in FORBIDDEN_DEPENDENCIES:
            assert forbidden not in text, "{0} must not appear in {1}".format(forbidden, file_name)


def test_only_pyside2_is_the_gui_dependency():
    text = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "PySide2" in text
    assert "pyside6" not in text.lower()
    assert "pyqt" not in text.lower()


@pytest.mark.parametrize("file_path", _all_derby_py_files(), ids=lambda p: str(p.relative_to(PROJECT_ROOT)))
def test_no_forbidden_networking_imports(file_path: Path):
    if file_path == ALLOWED_NETWORKING_FILE:
        pytest.skip("the one allowed networking file")
    text = file_path.read_text(encoding="utf-8")
    imported_modules = IMPORT_PATTERN.findall(text)
    for module_name in imported_modules:
        for forbidden in FORBIDDEN_IMPORT_SUBSTRINGS:
            assert forbidden not in module_name, (
                "{0} imports forbidden module reference {1!r} (matched {2!r})".format(
                    file_path.relative_to(PROJECT_ROOT), module_name, forbidden
                )
            )


def test_update_check_is_the_only_file_referencing_urllib_request():
    offenders = []
    for file_path in _all_derby_py_files():
        text = file_path.read_text(encoding="utf-8")
        if "urllib.request" in text and file_path != ALLOWED_NETWORKING_FILE:
            offenders.append(str(file_path.relative_to(PROJECT_ROOT)))
    assert offenders == []


def test_version_matches_pyproject():
    pyproject_text = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject_text, re.MULTILINE)
    assert match is not None, "pyproject.toml must declare a version"
    assert derby.__version__ == match.group(1)


def test_compileall_succeeds_on_python38():
    result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(DERBY_DIR)],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")


def test_startfile_and_webbrowser_confined_to_allowed_files():
    offenders = []
    for file_path in _all_derby_py_files():
        if file_path in ALLOWED_STARTFILE_OR_BROWSER_FILES:
            continue
        text = file_path.read_text(encoding="utf-8")
        if "os.startfile" in text or "webbrowser" in text:
            offenders.append(str(file_path.relative_to(PROJECT_ROOT)))
    assert offenders == []


def test_whatsapp_module_only_builds_whitelisted_url_schemes():
    text = WHATSAPP_FILE.read_text(encoding="utf-8")
    url_literals = re.findall(r'"((?:whatsapp://|https?://)[^"]*)"', text)
    assert url_literals, "expected at least one URL literal in whatsapp.py"
    for literal in url_literals:
        assert literal.startswith("whatsapp://send?") or literal.startswith("https://wa.me/"), literal


def test_urllib_parse_is_allowed_but_not_urllib_request_outside_update_check():
    # urllib.parse makes no network request (it's pure string parsing), so
    # it's fine anywhere; test_update_check_is_the_only_file_referencing_urllib_request
    # already proves urllib.request itself stays confined.
    text = WHATSAPP_FILE.read_text(encoding="utf-8")
    assert "urllib.parse" in text
    assert "urllib.request" not in text


def test_no_match_statements():
    offenders = []
    for file_path in _all_derby_py_files():
        text = file_path.read_text(encoding="utf-8")
        if MATCH_STATEMENT_PATTERN.search(text):
            offenders.append(str(file_path.relative_to(PROJECT_ROOT)))
    assert offenders == []


def _all_tools_py_files():
    if not TOOLS_DIR.exists():
        return []
    return sorted(TOOLS_DIR.rglob("*.py"))


@pytest.mark.parametrize("file_path", _all_tools_py_files(), ids=lambda p: str(p.relative_to(PROJECT_ROOT)))
def test_tools_scripts_still_forbid_real_networking(file_path: Path):
    """tools/ is dev-time only and may import QtSvg (CLAUDE.md hard
    constraint 4's one carve-out) -- but it must never make an actual
    network call, same as the rest of the project."""
    text = file_path.read_text(encoding="utf-8")
    imported_modules = IMPORT_PATTERN.findall(text)
    non_svg_forbidden = [item for item in FORBIDDEN_IMPORT_SUBSTRINGS if item != "QtSvg"]
    for module_name in imported_modules:
        for forbidden in non_svg_forbidden:
            assert forbidden not in module_name, (
                "{0} imports forbidden module reference {1!r} (matched {2!r})".format(
                    file_path.relative_to(PROJECT_ROOT), module_name, forbidden
                )
            )


def test_no_real_user_path_computed_outside_paths_py():
    """derby/core/utils/paths.py is the ONLY module allowed to read
    %APPDATA%/%USERPROFILE% (directly or via Path.home()) -- every other
    module must call its functions instead, which also honor the
    DERBY_DATA_DIR/DERBY_DOCS_DIR test/tool overrides. A module that reads
    these itself would bypass that override and risk writing into the
    real user folders during a test, preview, or --selftest run."""
    offenders = []
    for file_path in _all_derby_py_files():
        if file_path == PATHS_FILE:
            continue
        text = file_path.read_text(encoding="utf-8")
        if REAL_USER_PATH_ACCESS_PATTERN.search(text):
            offenders.append(str(file_path.relative_to(PROJECT_ROOT)))
    assert offenders == []


def test_no_removeprefix_or_removesuffix():
    offenders = []
    for file_path in _all_derby_py_files():
        text = file_path.read_text(encoding="utf-8")
        if "removeprefix" in text or "removesuffix" in text:
            offenders.append(str(file_path.relative_to(PROJECT_ROOT)))
    assert offenders == []
