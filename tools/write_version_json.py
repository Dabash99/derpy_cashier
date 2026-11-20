"""Writes release/version.json -- the manifest derby/core/updates/update_check.py
fetches when the owner clicks "فحص التحديثات". This is a quick preview/dev
tool only: for a real release, use tools/make_release.py instead, which
computes the real installer sha256 and runs the full build+verify
pipeline first. See docs/RELEASING.md for the publishing steps (the
"releases" repo is Dabash99/derby-releases, kept separate and public --
the source repo stays private).

If release/Derby-Setup-<version>.exe already exists (from a previous
build), its real sha256 is used; otherwise a placeholder of 64 zeros is
written (NOT a real artifact hash -- do not publish this as-is).

Usage:
    .venv\\Scripts\\python.exe tools\\write_version_json.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import derby  # noqa: E402

OUT_PATH = PROJECT_ROOT / "release" / "version.json"
RELEASE_DIR = PROJECT_ROOT / "release"

# Must be an https:// URL on github.com, objects.githubusercontent.com,
# or raw.githubusercontent.com (see
# derby/core/updates/version_logic.py:ALLOWED_DOWNLOAD_HOSTS; anything
# else is rejected by the app itself as an extra safety net). Points at
# the separate public "releases" repo, not the private source repo.
RELEASE_DOWNLOAD_URL = (
    "https://github.com/Dabash99/derby-releases/releases/download/v{version}/Derby-Setup-{version}.exe"
)

NOTES = "إصدار ديربي {version}"

PLACEHOLDER_SHA256 = "0" * 64


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(str(path), "rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    version = derby.__version__
    installer_path = RELEASE_DIR / "Derby-Setup-{0}.exe".format(version)
    if installer_path.exists():
        sha256 = _sha256_of(installer_path)
    else:
        sha256 = PLACEHOLDER_SHA256
        print("NOTE: {0} not found -- writing a placeholder sha256 of zeros.".format(installer_path.name))
        print("      Do not publish this file; run tools/make_release.py for a real release.")

    manifest = {
        "version": version,
        "notes": NOTES.format(version=version),
        "download_url": RELEASE_DOWNLOAD_URL.format(version=version),
        "sha256": sha256,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote {0}".format(OUT_PATH.relative_to(PROJECT_ROOT)))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
