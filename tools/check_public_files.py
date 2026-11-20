"""Privacy guard for release\\public\\ -- the ONLY folder whose contents are
meant to be copied into the separate public repo (Dabash99/derby-releases).

The source repo (derpy_cashier) must stay PRIVATE: its git history
contains real cafe menu photos and prices (commit 00edea1, never cleaned
from history -- see docs/RELEASING.md). release\\public\\ is the one
place tools/make_release.py writes files that are safe to make public,
and this script is the automated check that it really is just
version.json + README.md, with no personal data (real paths, phone
numbers, emails) baked into version.json.

Used both as a standalone check (tools/make_release.py runs it after
writing release\\public\\) and as a library function for tests.

Usage:
    .venv\\Scripts\\python.exe tools\\check_public_files.py [public_dir]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PUBLIC_DIR = PROJECT_ROOT / "release" / "public"

ALLOWED_FILENAMES = {"version.json", "README.md"}
ALLOWED_VERSION_JSON_KEYS = {"version", "notes", "download_url", "sha256"}

# A real Windows user/profile path, an email address, or a long run of
# digits (a phone/WhatsApp number) should never end up in a manifest that
# only needs version/notes/download_url/sha256.
_SUSPICIOUS_PATTERNS = (
    re.compile(r"[A-Za-z]:\\\\?Users\\", re.IGNORECASE),
    re.compile(r"%APPDATA%", re.IGNORECASE),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"\d{10,}"),
)


def check_public_dir(public_dir: Path) -> List[str]:
    """Returns a list of problems (empty list = all clear)."""
    problems = []

    if not public_dir.exists():
        return ["{0} does not exist".format(public_dir)]

    actual_names = {p.name for p in public_dir.iterdir() if p.is_file()}
    extra = actual_names - ALLOWED_FILENAMES
    if extra:
        problems.append("unexpected file(s) in {0}: {1}".format(public_dir, sorted(extra)))
    missing = ALLOWED_FILENAMES - actual_names
    if missing:
        problems.append("missing required file(s) in {0}: {1}".format(public_dir, sorted(missing)))

    version_json_path = public_dir / "version.json"
    if version_json_path.exists():
        raw_text = version_json_path.read_text(encoding="utf-8")
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as error:
            problems.append("version.json is not valid JSON: {0}".format(error))
            data = None

        if isinstance(data, dict):
            extra_keys = set(data.keys()) - ALLOWED_VERSION_JSON_KEYS
            if extra_keys:
                problems.append("version.json has unexpected key(s): {0}".format(sorted(extra_keys)))

            # Only scan the free-text "notes" field for personal data --
            # "sha256" and "version" are expected to contain long digit
            # runs (a hex digest, "1.0.0") that would otherwise false-
            # positive against the phone-number pattern below.
            notes_text = data.get("notes", "") if isinstance(data.get("notes"), str) else ""
            for pattern in _SUSPICIOUS_PATTERNS:
                if pattern.search(notes_text):
                    problems.append(
                        "version.json's notes field contains what looks like personal data "
                        "(matched {0!r})".format(pattern.pattern)
                    )

            download_url = data.get("download_url", "")
            if isinstance(download_url, str) and ("Users" in download_url or "%APPDATA%" in download_url):
                problems.append("version.json's download_url looks like a local file path, not a release URL")

    readme_path = public_dir / "README.md"
    if readme_path.exists():
        readme_text = readme_path.read_text(encoding="utf-8")
        for pattern in _SUSPICIOUS_PATTERNS:
            if pattern.search(readme_text):
                problems.append(
                    "README.md contains what looks like personal data (matched {0!r})".format(pattern.pattern)
                )

    return problems


def main() -> int:
    public_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PUBLIC_DIR
    problems = check_public_dir(public_dir)
    if problems:
        print("check_public_files FAILED:")
        for problem in problems:
            print("  - {0}".format(problem))
        return 1
    print("check_public_files OK: {0} contains only {1}, no personal data detected.".format(
        public_dir, sorted(ALLOWED_FILENAMES)
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
