"""Dev-time ONLY (Part B3). Wraps the PyInstaller build in derby.spec:

  1. ruff + the full test suite + policy tests first -- aborts the build
     on any failure, so a broken build never ships.
  2. Runs PyInstaller (one-dir, see derby.spec).
  3. Makes sure dist\\Derby carries its own UCRT DLLs (api-ms-win-crt-*.dll,
     ucrtbase.dll), copying them from the Windows 10 SDK redist if
     PyInstaller didn't already bundle them -- so the app works on
     Windows 7 even without KB2999226 (see installer/derby.iss).
  4. Verifies the frozen output: dist\\Derby\\Derby.exe --selftest (its
     own sandboxed temp dirs, offscreen Qt) must exit 0; confirms no
     QtNetwork/QtSvg DLL made it into dist\\Derby; reports folder size,
     file count, and the --selftest run's wall time as a cold-start
     proxy (--selftest does meaningfully more work than a plain launch --
     a full migration, order/payment/PlayStation/export/backup/restore
     cycle -- so this is a conservative, not a tight, timing).
  5. Prints SHA-256 of the built Derby.exe.

Must run under venv32 (Python 3.8.10 32-bit) -- the shipped build targets
Windows 7 SP1 32-bit and 64-bit from one 32-bit interpreter/build, so a
64-bit interpreter here would silently produce a binary that never runs
on the 32-bit target. Aborts immediately if the running interpreter is
not 32-bit.

Usage:
    venv32\\Scripts\\python.exe tools\\build.py
"""
from __future__ import annotations

import glob
import hashlib
import os
import shutil
import struct
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

# PyInstaller bundles vcruntime140.dll (it pulls that one in on its own
# because the Python 3.8 DLL itself depends on it) but not the separate
# api-ms-win-crt-*.dll / ucrtbase.dll forwarder files -- those are normally
# supplied by Windows Update (KB2999226) on Windows 7. Since the installer
# no longer blocks on that update (see installer/derby.iss), the build
# copies these DLLs from the Windows 10 SDK's redistributable folder so
# Derby.exe works even on a Windows 7 box that never got KB2999226.
REQUIRED_UCRT_DLL = "api-ms-win-crt-runtime-l1-1-0.dll"
UCRT_REDIST_GLOBS = (
    r"C:\Program Files (x86)\Windows Kits\10\Redist\*\ucrt\DLLs\x86\*.dll",
    r"C:\Program Files\Windows Kits\10\Redist\*\ucrt\DLLs\x86\*.dll",
)


def _run(args, **kwargs):
    print("+ {0}".format(" ".join(str(a) for a in args)))
    return subprocess.run(args, cwd=str(PROJECT_ROOT), **kwargs)


def _abort(message: str) -> None:
    print("BUILD ABORTED: {0}".format(message))
    sys.exit(1)


def check_32bit_interpreter() -> None:
    bits = struct.calcsize("P") * 8
    if bits != 32:
        _abort(
            "this build must run under a 32-bit Python interpreter (venv32), "
            "but the running interpreter ({0}) is {1}-bit. Create/use venv32 "
            "with Python 3.8.10 32-bit and run: "
            "venv32\\Scripts\\python.exe tools\\build.py".format(PYTHON, bits)
        )
    print("Confirmed: running under a 32-bit interpreter ({0}).".format(PYTHON))


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


def ensure_ucrt_dlls() -> None:
    if (DIST_DIR / REQUIRED_UCRT_DLL).exists():
        print("Confirmed: {0} already present in dist/Derby.".format(REQUIRED_UCRT_DLL))
        return

    print("{0} missing from dist/Derby -- looking for the Windows 10 SDK UCRT redist...".format(
        REQUIRED_UCRT_DLL
    ))
    redist_dir = None
    for pattern in UCRT_REDIST_GLOBS:
        matches = sorted(glob.glob(pattern))
        if matches:
            redist_dir = str(Path(matches[0]).parent)
            break

    if redist_dir is None:
        print(
            "WARNING: {0} is missing from dist/Derby and no Windows 10 SDK UCRT "
            "redist (Redist\\ucrt\\DLLs\\x86) was found on this machine to copy "
            "it from. This build was produced WITHOUT the bundled UCRT DLLs -- "
            "on a Windows 7 machine, Derby.exe will only run if KB2999226 (or a "
            "later cumulative update that includes it) is already installed. "
            "Install the Windows 10 SDK on the build machine to bundle these "
            "DLLs and remove this dependency.".format(REQUIRED_UCRT_DLL)
        )
        return

    copied = 0
    for dll_path in glob.glob(str(Path(redist_dir) / "*.dll")):
        shutil.copy2(dll_path, DIST_DIR)
        copied += 1
    print("Copied {0} UCRT DLL(s) from {1} into dist/Derby.".format(copied, redist_dir))

    if not (DIST_DIR / REQUIRED_UCRT_DLL).exists():
        _abort("Copied UCRT DLLs from {0} but {1} is still missing.".format(redist_dir, REQUIRED_UCRT_DLL))


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
    check_32bit_interpreter()
    run_quality_gates()
    run_pyinstaller()
    ensure_ucrt_dlls()
    check_no_forbidden_dlls()
    report_folder_stats()
    run_frozen_selftest()
    print_sha256()
    print("Build verified OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
