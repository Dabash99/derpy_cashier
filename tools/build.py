"""Dev-time ONLY (Part B3). Wraps the PyInstaller build in derby.spec:

  1. ruff + the full test suite + policy tests first -- aborts the build
     on any failure, so a broken build never ships.
  2. Runs PyInstaller (one-dir, see derby.spec).
  3. Verifies the frozen output: dist\\Derby\\Derby.exe --selftest (its
     own sandboxed temp dirs, offscreen Qt) must exit 0; confirms no
     QtNetwork/QtSvg DLL made it into dist\\Derby; reports folder size,
     file count, and the --selftest run's wall time as a cold-start
     proxy (--selftest does meaningfully more work than a plain launch --
     a full migration, order/payment/PlayStation/export/backup/restore
     cycle -- so this is a conservative, not a tight, timing).
  4. Prints SHA-256 of the built Derby.exe.

Usage:
    .venv\\Scripts\\python.exe tools\\build.py
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
DIST_DIR = PROJECT_ROOT / "dist" / "Derby"
EXE_PATH = DIST_DIR / "Derby.exe"

FORBIDDEN_DLL_SUBSTRINGS = ("qtnetwork", "qtsvg", "qtwebengine", "qt3d")


def _run(args, **kwargs):
    print("+ {0}".format(" ".join(str(a) for a in args)))
    return subprocess.run(args, cwd=str(PROJECT_ROOT), **kwargs)


def _abort(message: str) -> None:
    print("BUILD ABORTED: {0}".format(message))
    sys.exit(1)


def run_quality_gates() -> None:
    result = _run([PYTHON, "-m", "ruff", "check", "."])
    if result.returncode != 0:
        _abort("ruff check failed")

    result = _run([PYTHON, "-m", "pytest", "-q"])
    if result.returncode != 0:
        _abort("test suite failed")
    print("Quality gates passed: ruff clean, full test suite green (includes tests/test_policy.py).")


def run_pyinstaller() -> None:
    result = _run([PYTHON, "-m", "PyInstaller", "--noconfirm", "--clean", str(PROJECT_ROOT / "derby.spec")])
    if result.returncode != 0:
        _abort("PyInstaller build failed")
    if not EXE_PATH.exists():
        _abort("PyInstaller reported success but {0} does not exist".format(EXE_PATH))


def check_no_forbidden_dlls() -> None:
    offenders = []
    for path in DIST_DIR.rglob("*"):
        if path.is_file():
            lowered = path.name.lower()
            for forbidden in FORBIDDEN_DLL_SUBSTRINGS:
                if forbidden in lowered:
                    offenders.append(str(path.relative_to(DIST_DIR)))
    if offenders:
        _abort("forbidden Qt module files found in dist/Derby: {0}".format(offenders))
    print("Confirmed: no QtNetwork/QtSvg/QtWebEngine/Qt3D files in dist/Derby.")


def report_folder_stats() -> None:
    files = [p for p in DIST_DIR.rglob("*") if p.is_file()]
    total_bytes = sum(p.stat().st_size for p in files)
    print("dist/Derby: {0} files, {1:.1f} MB".format(len(files), total_bytes / (1024 * 1024)))


def run_frozen_selftest() -> None:
    work_dir = Path(tempfile.mkdtemp(prefix="derby_build_verify_"))
    env = dict(os.environ)
    env["DERBY_DATA_DIR"] = str(work_dir / "appdata")
    env["DERBY_DOCS_DIR"] = str(work_dir / "docs")
    env["QT_QPA_PLATFORM"] = "offscreen"

    t0 = time.perf_counter()
    result = _run([str(EXE_PATH), "--selftest"], env=env, capture_output=True, text=True, timeout=120)
    elapsed = time.perf_counter() - t0

    print(result.stdout)
    if result.returncode != 0:
        _abort("frozen Derby.exe --selftest failed (exit {0})".format(result.returncode))
    print("Frozen --selftest passed in {0:.2f}s (cold-start proxy -- see module docstring).".format(elapsed))


def print_sha256() -> None:
    digest = hashlib.sha256()
    with open(str(EXE_PATH), "rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    print("SHA-256 ({0}): {1}".format(EXE_PATH.relative_to(PROJECT_ROOT), digest.hexdigest()))


def main() -> int:
    run_quality_gates()
    run_pyinstaller()
    check_no_forbidden_dlls()
    report_folder_stats()
    run_frozen_selftest()
    print_sha256()
    print("Build verified OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
