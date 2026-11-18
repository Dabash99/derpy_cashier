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
ALLOWED_NETWORKING_FILE = DERBY_DIR / "core" / "updates" / "update_check.py"

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
]

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


def test_no_match_statements():
    offenders = []
    for file_path in _all_derby_py_files():
        text = file_path.read_text(encoding="utf-8")
        if MATCH_STATEMENT_PATTERN.search(text):
            offenders.append(str(file_path.relative_to(PROJECT_ROOT)))
    assert offenders == []


def test_no_removeprefix_or_removesuffix():
    offenders = []
    for file_path in _all_derby_py_files():
        text = file_path.read_text(encoding="utf-8")
        if "removeprefix" in text or "removesuffix" in text:
            offenders.append(str(file_path.relative_to(PROJECT_ROOT)))
    assert offenders == []
