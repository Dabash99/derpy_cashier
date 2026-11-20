"""One command for a full Derby release: quality gates, the PyInstaller
build, the Inno Setup installer (compiled + silently
installed/--selftest'ed/uninstalled -- see tools/build_installer.py),
then the files meant to go public.

The source repo (derpy_cashier) stays PRIVATE -- its git history has
real cafe menu data in it (commit 00edea1, see docs/RELEASING.md). Only
release\\public\\version.json and release\\public\\README.md are ever
meant to leave this machine, by being copied by hand into a separate
local clone of the public repo Dabash99/derby-releases. This script:

  - NEVER touches git (no branch, no worktree, no commit) in this repo
    or anywhere else.
  - NEVER pushes, tags, or creates a GitHub release.
  - NEVER makes a network request (the app's own update_check.py is the
    only networking code in the whole project, and it is not exercised
    by this script).
  - Stops loudly (non-zero exit, clear message) on the first failing
    step -- a half-finished release is never silently reported as OK.

Steps:
  1. ruff check .
  2. pytest -q (full suite -- includes tests/test_policy.py)
  3. tools/build.py (PyInstaller build + packaged --selftest)
  4. tools/build_installer.py (Inno Setup 6 compile + silent
     install/--selftest/uninstall verification + release\\SHA256SUMS.txt)
  5. release\\version.json: real sha256 of the built installer, and the
     download_url for the public releases repo.
  6. release\\public\\version.json + release\\public\\README.md -- the
     only two files meant to be copied into derby-releases.
  7. tools/check_public_files.py against release\\public\\.
  8. Prints the exact manual copy/push steps (never run automatically).

Usage:
    .venv\\Scripts\\python.exe tools\\make_release.py
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
RELEASE_DIR = PROJECT_ROOT / "release"
PUBLIC_DIR = RELEASE_DIR / "public"

sys.path.insert(0, str(PROJECT_ROOT))

DOWNLOAD_URL_TEMPLATE = (
    "https://github.com/Dabash99/derby-releases/releases/download/v{version}/Derby-Setup-{version}.exe"
)
NOTES_TEMPLATE = "إصدار ديربي {version}"

PUBLIC_README = """# Derby releases

This repo publishes `version.json` for Derby's manual "فحص التحديثات"
(Check for Updates) button, plus installer files attached to GitHub
Releases here. It contains no source code and no cafe data -- see the
main app repo (private) for that.
"""


def _run(args, **kwargs):
    print("+ {0}".format(" ".join(str(a) for a in args)))
    return subprocess.run(args, cwd=str(PROJECT_ROOT), **kwargs)


def _abort(message: str) -> None:
    print("RELEASE ABORTED: {0}".format(message))
    sys.exit(1)


def run_quality_gates() -> None:
    result = _run([PYTHON, "-m", "ruff", "check", "."])
    if result.returncode != 0:
        _abort("ruff check failed")

    result = _run([PYTHON, "-m", "pytest", "-q"])
    if result.returncode != 0:
        _abort("test suite failed")


def run_build() -> None:
    result = _run([PYTHON, str(PROJECT_ROOT / "tools" / "build.py")])
    if result.returncode != 0:
        _abort("tools/build.py failed (PyInstaller build or packaged --selftest)")


def run_build_installer() -> None:
    result = _run([PYTHON, str(PROJECT_ROOT / "tools" / "build_installer.py")])
    if result.returncode == 2:
        _abort(
            "Inno Setup 6 (ISCC.exe) was not found -- see the message above for where to get it "
            "and the exact manual compile command. installer/derby.iss is otherwise ready."
        )
    if result.returncode != 0:
        _abort("tools/build_installer.py failed (compile, or silent install/--selftest/uninstall verification)")


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(str(path), "rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_version_json(version: str) -> dict:
    installer_path = RELEASE_DIR / "Derby-Setup-{0}.exe".format(version)
    if not installer_path.exists():
        _abort("{0} was not produced by tools/build_installer.py".format(installer_path))

    sha256 = _sha256_of(installer_path)
    manifest = {
        "version": version,
        "notes": NOTES_TEMPLATE.format(version=version),
        "download_url": DOWNLOAD_URL_TEMPLATE.format(version=version),
        "sha256": sha256,
    }

    import json

    version_json_path = RELEASE_DIR / "version.json"
    version_json_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote {0}".format(version_json_path.relative_to(PROJECT_ROOT)))
    return manifest


def write_public_files(manifest: dict) -> None:
    import json

    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    (PUBLIC_DIR / "version.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (PUBLIC_DIR / "README.md").write_text(PUBLIC_README, encoding="utf-8")
    print("wrote {0}\\version.json and README.md".format(PUBLIC_DIR.relative_to(PROJECT_ROOT)))


def run_public_files_check() -> None:
    sys.path.insert(0, str(PROJECT_ROOT / "tools"))
    import check_public_files

    problems = check_public_files.check_public_dir(PUBLIC_DIR)
    if problems:
        for problem in problems:
            print("  - {0}".format(problem))
        _abort("release/public failed the privacy check -- see tools/check_public_files.py")
    print("check_public_files OK.")


def print_manual_steps(version: str) -> None:
    installer_name = "Derby-Setup-{0}.exe".format(version)
    print()
    print("=" * 70)
    print("Build finished. Nothing was pushed, tagged, or released -- do these by hand:")
    print("=" * 70)
    print()
    print("1. Copy the public manifest into your local clone of derby-releases:")
    print("     copy {0}\\public\\version.json  <path-to-derby-releases-clone>\\version.json".format(RELEASE_DIR))
    print("     copy {0}\\public\\README.md     <path-to-derby-releases-clone>\\README.md".format(RELEASE_DIR))
    print("   Then, inside that clone:")
    print("     git add version.json README.md")
    print('     git commit -m "Release v{0}"'.format(version))
    print("     git push origin main")
    print()
    print("2. On GitHub, create a Release on Dabash99/derby-releases tagged v{0},".format(version))
    print("   and upload these two files as assets:")
    print("     {0}\\{1}".format(RELEASE_DIR, installer_name))
    print("     {0}\\SHA256SUMS.txt".format(RELEASE_DIR))
    print()
    print("3. Verify the raw manifest URL opens in a browser:")
    print("     https://raw.githubusercontent.com/Dabash99/derby-releases/main/version.json")
    print()
    print("4. In Derby's Settings -> رابط ملف التحديثات, confirm it is prefilled with that")
    print("   same URL (it is, by default), then click فحص التحديثات to confirm it finds v{0}.".format(version))
    print()
    print("Reminder: derpy_cashier (this repo) must stay PRIVATE -- its git history still")
    print("contains real cafe menu photos/prices (commit 00edea1).")


def main() -> int:
    import derby

    run_quality_gates()
    run_build()
    run_build_installer()
    manifest = write_version_json(derby.__version__)
    write_public_files(manifest)
    run_public_files_check()
    print_manual_steps(derby.__version__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
