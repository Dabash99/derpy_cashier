"""release/version.json must be the exact shape
derby/core/updates/version_logic.parse_manifest() expects, and match
derby.__version__ -- regenerate with tools/write_version_json.py."""
from __future__ import annotations

import json
from pathlib import Path

import derby
from derby.core.updates import version_logic

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERSION_JSON_PATH = PROJECT_ROOT / "release" / "version.json"


def test_version_json_exists_and_parses_as_a_valid_manifest():
    assert VERSION_JSON_PATH.exists()
    text = VERSION_JSON_PATH.read_text(encoding="utf-8")
    manifest = version_logic.parse_manifest(text)  # raises ManifestError if malformed
    # Not bumped ahead of derby.__version__ here: release/version.json is the
    # live update-check manifest, and the release step (tools/make_release.py
    # / publish_release.py) sets it only once that version is actually
    # published on GitHub.
    assert not version_logic.is_newer(derby.__version__, manifest["version"])


def test_version_json_download_url_is_on_an_allowed_host():
    manifest = json.loads(VERSION_JSON_PATH.read_text(encoding="utf-8"))
    assert version_logic.is_allowed_download_url(manifest["download_url"])
