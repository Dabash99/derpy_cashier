"""Pure parsing/comparison logic for the update check — no I/O here at all,
so it can be unit tested without any network or Qt dependency.
"""
from __future__ import annotations

import json
import re
from typing import Tuple
from urllib.parse import urlparse

ALLOWED_DOWNLOAD_HOSTS = ("github.com", "objects.githubusercontent.com", "raw.githubusercontent.com")

# version.json is published to the SEPARATE public "releases" repo
# (Dabash99/derby-releases) -- the source repo (derpy_cashier) stays
# private because its git history contains real cafe menu photos/prices
# (commit 00edea1, never cleaned from history -- see docs/RELEASING.md).
# This is only the prefilled default for Settings -> update_manifest_url;
# the owner can still edit it.
DEFAULT_UPDATE_MANIFEST_URL = "https://raw.githubusercontent.com/Dabash99/derby-releases/main/version.json"

_SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ManifestError(ValueError):
    """Raised when the update manifest JSON is malformed or incomplete."""


def parse_version(text: str) -> Tuple[int, ...]:
    """Parse a semantic-ish version string like "1.10.0" into (1, 10, 0)."""
    parts = text.strip().split(".")
    if not parts or not all(part.isdigit() for part in parts):
        raise ValueError("invalid version string: {0!r}".format(text))
    return tuple(int(part) for part in parts)


def is_newer(current_version: str, candidate_version: str) -> bool:
    return parse_version(candidate_version) > parse_version(current_version)


def is_allowed_download_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname in ALLOWED_DOWNLOAD_HOSTS


def parse_manifest(raw_json: str) -> dict:
    """Parse and validate the update manifest JSON.

    Expected shape:
    {"version": "1.0.1", "notes": "...", "download_url": "https://...", "sha256": "<64 hex chars>"}
    Raises ManifestError on invalid JSON, missing fields, a malformed
    version string, a download_url that isn't an allowed https host, or a
    sha256 that isn't exactly 64 lowercase hex characters.
    """
    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError) as error:
        raise ManifestError("invalid JSON") from error

    if not isinstance(data, dict):
        raise ManifestError("manifest must be a JSON object")

    for field in ("version", "notes", "download_url", "sha256"):
        if field not in data or not isinstance(data[field], str):
            raise ManifestError("missing or invalid field: {0}".format(field))

    try:
        parse_version(data["version"])
    except ValueError as error:
        raise ManifestError("invalid version in manifest") from error

    if not is_allowed_download_url(data["download_url"]):
        raise ManifestError("download_url is not an allowed https host")

    if not _SHA256_HEX_PATTERN.match(data["sha256"]):
        raise ManifestError("sha256 must be 64 lowercase hex characters")

    return {
        "version": data["version"],
        "notes": data["notes"],
        "download_url": data["download_url"],
        "sha256": data["sha256"],
    }
