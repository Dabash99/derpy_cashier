"""Dev-time ONLY (Part B4). Compiles installer/derby.iss with Inno
Setup 6 and verifies it end to end -- entirely inside temp directories,
never Program Files, never a real Start Menu/desktop shortcut.

If ISCC.exe (the Inno Setup 6 command-line compiler) is not found, this
script does NOT try to install Inno Setup or work around its absence:
it prints exactly where to get it and the exact manual compile command,
and stops. installer/derby.iss itself is still complete and ready to
compile regardless -- see tools/write_installer_version.py too, which
this script runs first either way.

When ISCC.exe IS found:
  1. Regenerates installer/version.iss from derby.__version__.
  2. Compiles installer/derby.iss -> release/Derby-Setup-<version>.exe.
  3. Silent-installs it into a TEMP directory
     (/VERYSILENT /SUPPRESSMSGBOXES /NOICONS /DIR=<temp>).
  4. Runs the installed Derby.exe --selftest (its own sandboxed
     DERBY_DATA_DIR/DERBY_DOCS_DIR, offscreen Qt) -- must exit 0.
  5. Silent-uninstalls it, then confirms the temp install directory is
     gone and the --selftest's own temp data directories are untouched
     (uninstall only ever touches {app} -- see derby.iss's own comments).
  6. Prints SHA-256 of release/Derby-Setup-<version>.exe and
     release/SHA256SUMS.txt.

Usage:
    .venv\\Scripts\\python.exe tools\\build_installer.py
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
INSTALLER_DIR = PROJECT_ROOT / "installer"
ISS_PATH = INSTALLER_DIR / "derby.iss"
RELEASE_DIR = PROJECT_ROOT / "release"

ISCC_CANDIDATES = (
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
)


def find_iscc() -> "str | None":
    on_path = shutil.which("ISCC.exe") or shutil.which("ISCC")
    if on_path:
        return on_path
    for candidate in ISCC_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


def _run(args, **kwargs):
    print("+ {0}".format(" ".join(str(a) for a in args)))
    return subprocess.run(args, **kwargs)


def regenerate_version_include() -> str:
    result = _run([PYTHON, str(PROJECT_ROOT / "tools" / "write_installer_version.py")], cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        print("ABORTED: could not regenerate installer/version.iss")
        sys.exit(1)
    sys.path.insert(0, str(PROJECT_ROOT))
    import derby

    return derby.__version__


def report_missing_iscc() -> None:
    print("ISCC.exe (Inno Setup 6 command-line compiler) was not found on this machine.")
    print()
    print("installer/derby.iss is complete and ready to compile regardless -- get Inno Setup 6 here:")
    print("    https://jrsoftware.org/isdl.php")
    print()
    print("Then compile it by hand:")
    print(r'    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\derby.iss')
    print()
    print("(If you installed it somewhere else, use that ISCC.exe path instead.)")


def find_built_installer() -> Path:
    candidates = sorted(RELEASE_DIR.glob("Derby-Setup-*.exe"))
    if not candidates:
        print("ABORTED: no release\\Derby-Setup-*.exe found after compiling")
        sys.exit(1)
    return candidates[-1]


def verify_installer(installer_path: Path) -> None:
    install_dir = Path(tempfile.mkdtemp(prefix="derby_installer_verify_"))
    data_dir = Path(tempfile.mkdtemp(prefix="derby_installer_verify_data_"))
    print("Silent-installing into {0} (never Program Files for this check) ...".format(install_dir))
    # /CURRENTUSER (allowed via PrivilegesRequiredOverridesAllowed=commandline
    # in installer/derby.iss) skips the admin/UAC elevation a real end-user
    # install would normally request -- there is nobody here to click a UAC
    # consent prompt, so this verification must never depend on one.
    result = _run(
        [
            str(installer_path),
            "/CURRENTUSER",
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NOICONS",
            "/DIR={0}".format(install_dir),
        ],
        timeout=180,
    )
    if result.returncode != 0:
        print("ABORTED: silent install failed (exit {0})".format(result.returncode))
        sys.exit(1)

    exe_path = install_dir / "Derby.exe"
    if not exe_path.exists():
        print("ABORTED: {0} does not exist after install".format(exe_path))
        sys.exit(1)

    env = dict(os.environ)
    env["DERBY_DATA_DIR"] = str(data_dir / "appdata")
    env["DERBY_DOCS_DIR"] = str(data_dir / "docs")
    env["QT_QPA_PLATFORM"] = "offscreen"
    print("Running installed Derby.exe --selftest ...")
    result = _run([str(exe_path), "--selftest"], env=env, capture_output=True, text=True, timeout=120)
    print(result.stdout)
    if result.returncode != 0:
        print("ABORTED: installed Derby.exe --selftest failed (exit {0})".format(result.returncode))
        sys.exit(1)

    uninstaller = install_dir / "unins000.exe"
    print("Silent-uninstalling ...")
    result = _run([str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES"], timeout=180)
    if result.returncode != 0:
        print("ABORTED: silent uninstall failed (exit {0})".format(result.returncode))
        sys.exit(1)

    # unins000.exe deletes ITSELF asynchronously: it spawns a copy of
    # itself elsewhere that removes the original a moment after this
    # process (which we've already waited for above) exits -- so the
    # file can still legitimately be on disk for a brief window here.
    # Poll for up to a few seconds before treating it as a real leftover.
    remaining = []
    for _ in range(20):
        remaining = [p for p in install_dir.rglob("*") if p.is_file() and p.name != "unins000.dat"]
        if not remaining:
            break
        time.sleep(0.25)
    if remaining:
        print("ABORTED: files remain in {0} after uninstall: {1}".format(install_dir, remaining))
        sys.exit(1)
    if not (data_dir / "appdata").exists():
        print("ABORTED: the --selftest run's own sandboxed data dir vanished -- that would mean uninstall touched user data")
        sys.exit(1)

    print("Verified: silent install -> --selftest (exit 0) -> silent uninstall -> install dir empty, data dir untouched.")
    shutil.rmtree(install_dir, ignore_errors=True)
    shutil.rmtree(data_dir, ignore_errors=True)


def print_checksums(installer_path: Path) -> None:
    digest = hashlib.sha256()
    with open(str(installer_path), "rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    hex_digest = digest.hexdigest()
    print("SHA-256 ({0}): {1}".format(installer_path.name, hex_digest))

    sums_path = RELEASE_DIR / "SHA256SUMS.txt"
    sums_path.write_text("{0}  {1}\n".format(hex_digest, installer_path.name), encoding="utf-8")
    print("wrote {0}".format(sums_path.relative_to(PROJECT_ROOT)))


def main() -> int:
    regenerate_version_include()

    iscc = find_iscc()
    if iscc is None:
        report_missing_iscc()
        return 2

    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    result = _run([iscc, str(ISS_PATH)], cwd=str(INSTALLER_DIR))
    if result.returncode != 0:
        print("ABORTED: ISCC compile failed")
        return 1

    installer_path = find_built_installer()
    verify_installer(installer_path)
    print_checksums(installer_path)
    print("Installer build verified OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
