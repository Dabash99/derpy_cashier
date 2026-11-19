"""Writes release/version.json -- the manifest derby/core/updates/update_check.py
fetches when the owner clicks "فحص التحديثات". See docs/RELEASING.md for
where to host this file and how to compute the raw URL to put in
Settings -> update_manifest_url.

download_url is a placeholder until the matching GitHub release actually
exists -- update it by hand (or re-run this after editing
RELEASE_DOWNLOAD_URL below) once release/Derby-Setup-<version>.exe has
been uploaded to a real release.

Usage:
    .venv\\Scripts\\python.exe tools\\write_version_json.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import derby  # noqa: E402

OUT_PATH = PROJECT_ROOT / "release" / "version.json"

# Placeholder -- must be an https:// URL on github.com,
# objects.githubusercontent.com, or raw.githubusercontent.com (see
# derby/core/updates/version_logic.py:ALLOWED_DOWNLOAD_HOSTS; anything
# else is rejected by the app itself as an extra safety net).
RELEASE_DOWNLOAD_URL = "https://github.com/<owner>/<repo>/releases/download/v{version}/Derby-Setup-{version}.exe"

NOTES = "إصدار ديربي {version}"


def main() -> int:
    version = derby.__version__
    manifest = {
        "version": version,
        "notes": NOTES.format(version=version),
        "download_url": RELEASE_DOWNLOAD_URL.format(version=version),
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote {0}".format(OUT_PATH.relative_to(PROJECT_ROOT)))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
