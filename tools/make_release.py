"""One command for a full Derby release: quality gates, the PyInstaller
build, the Inno Setup installer (compiled + silently
installed/--selftest'ed/uninstalled -- see tools/build_installer.py),
then the files meant to go public.

Release assets (the installer, SHA256SUMS.txt) and an orphan "releases"
branch (version.json, README.md, releases-history.json -- no source
code) both live in this same repo, Dabash99/derpy_cashier (public --
see docs/RELEASING.md for what that means for this repo's git history).
Only release\\public\\version.json and release\\public\\README.md are
ever meant to leave this machine as-is, by being handed to
tools/publish_release.py (which maintains its own separate clone under
build\\releases-clone, never this checkout's working tree). This
script itself:

  - NEVER touches git (no branch, no worktree, no commit) in this repo
    or anywhere else.
  - NEVER pushes, tags, or creates a GitHub release -- UNLESS --publish
    is passed explicitly, in which case it hands off to
    tools/publish_release.py (git/gh via subprocess only, no Python
    networking) at the very end, after everything else below succeeds.
  - Without --publish, NEVER makes a network request (the app's own
    update_check.py is the only networking code in the whole project,
    and it is not exercised by this script).
  - Stops loudly (non-zero exit, clear message) on the first failing
    step -- a half-finished release is never silently reported as OK.

Steps:
  1. ruff check .
  2. pytest -q (full suite -- includes tests/test_policy.py)
  3. tools/build.py (PyInstaller build + packaged --selftest)
  4. tools/build_installer.py (Inno Setup 6 compile + silent
     install/--selftest/uninstall verification + release\\SHA256SUMS.txt)
  5. release\\version.json: real sha256 of the built installer, and the
     download_url for this repo's GitHub Release.
  6. release\\public\\version.json + release\\public\\README.md -- a
     privacy-checked preview of what tools/publish_release.py will push
     to the orphan "releases" branch.
  7. tools/check_public_files.py against release\\public\\.
  8. Prints the exact manual copy/push steps -- or, with --publish, runs
     tools/publish_release.py to do them (still asks to confirm unless
     --yes is also passed).

Usage:
    .venv\\Scripts\\python.exe tools\\make_release.py
    .venv\\Scripts\\python.exe tools\\make_release.py --publish
"""
from __future__ import annotations

import argparse
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
    "https://github.com/Dabash99/derpy_cashier/releases/download/v{version}/Derby-Setup-{version}.exe"
)
NOTES_TEMPLATE = "إصدار ديربي {version}"

PUBLIC_README = """# Derby releases

This file previews what the "releases" branch of this repo will hold:
`version.json` for Derby's manual "فحص التحديثات" (Check for Updates)
button. It contains no source code and no cafe data.
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
    print("Build finished. Nothing was pushed, tagged, or released -- do these by hand,")
    print("or run: .venv\\Scripts\\python.exe tools\\publish_release.py (does all of it):")
    print("=" * 70)
    print()
    print("1. In a separate local clone of this repo's orphan 'releases' branch")
    print("   (build\\releases-clone\\, created automatically by publish_release.py),")
    print("   copy and commit:")
    print("     {0}\\public\\version.json  -> version.json".format(RELEASE_DIR))
    print("     {0}\\public\\README.md     -> README.md".format(RELEASE_DIR))
    print('     git commit -m "Release v{0}"  &&  git push origin releases'.format(version))
    print()
    print("2. On GitHub, create a Release on Dabash99/derpy_cashier tagged v{0},".format(version))
    print("   and upload these two files as assets:")
    print("     {0}\\{1}".format(RELEASE_DIR, installer_name))
    print("     {0}\\SHA256SUMS.txt".format(RELEASE_DIR))
    print()
    print("3. Verify the raw manifest URL opens in a browser:")
    print("     https://raw.githubusercontent.com/Dabash99/derpy_cashier/releases/version.json")
    print()
    print("4. In Derby's Settings, click \"Check for Updates\" (the URL is fixed in code,")
    print("   DEFAULT_UPDATE_MANIFEST_URL) and confirm it finds v{0}.".format(version))
    print()
    print("Or pass --publish to this script to run tools/publish_release.py automatically")
    print("once this build finishes (it will still ask to confirm unless you also pass --yes).")


def run_publish(extra_args) -> int:
    result = _run([PYTHON, str(PROJECT_ROOT / "tools" / "publish_release.py")] + list(extra_args))
    return result.returncode


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--publish",
        action="store_true",
        help="after a successful build, also run tools/publish_release.py (default: never publish)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="with --publish, skip publish_release.py's confirmation prompt",
    )
    args = parser.parse_args(argv)

    import derby

    run_quality_gates()
    run_build()
    run_build_installer()
    manifest = write_version_json(derby.__version__)
    write_public_files(manifest)
    run_public_files_check()
    print_manual_steps(derby.__version__)

    if args.publish:
        publish_args = ["--yes"] if args.yes else []
        returncode = run_publish(publish_args)
        if returncode != 0:
            _abort("tools/publish_release.py failed -- see its output above")
    return 0


if __name__ == "__main__":
    sys.exit(main())
