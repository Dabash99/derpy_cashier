"""Writes installer/version.iss -- a tiny generated #include with
MyAppVersion, kept in sync with derby.__version__ (the one place the
version lives, see CLAUDE.md). installer/derby.iss includes this file
rather than hardcoding the version itself. Re-run this whenever the
version in derby/__init__.py changes, before compiling the installer
(tools/build_installer.py does this automatically).

Usage:
    .venv\\Scripts\\python.exe tools\\write_installer_version.py
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import derby  # noqa: E402

OUT_PATH = PROJECT_ROOT / "installer" / "version.iss"


def main() -> int:
    OUT_PATH.write_text(
        '#define MyAppVersion "{0}"\n'.format(derby.__version__),
        encoding="utf-8",
    )
    print("wrote {0} (MyAppVersion={1})".format(OUT_PATH.relative_to(PROJECT_ROOT), derby.__version__))
    return 0


if __name__ == "__main__":
    sys.exit(main())
