"""Pure parsing/comparison logic for the update check — no I/O here at all,
so it can be unit tested without any network or Qt dependency.
"""
from __future__ import annotations

import json
from typing import Tuple
from urllib.parse import urlparse

ALLOWED_DOWNLOAD_HOSTS = ("github.com", "objects.githubusercontent.com", "raw.githubusercontent.com")


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

    Expected shape: {"version": "1.0.1", "notes": "...", "download_url": "https://..."}
    Raises ManifestError on invalid JSON, missing fields, a malformed
    version string, or a download_url that isn't an allowed https host.
    """
    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError) as error:
        raise ManifestError("invalid JSON") from error

    if not isinstance(data, dict):
        raise ManifestError("manifest must be a JSON object")

    for field in ("version", "notes", "download_url"):
        if field not in data or not isinstance(data[field], str):
            raise ManifestError("missing or invalid field: {0}".format(field))

    try:
        parse_version(data["version"])
    except ValueError as error:
        raise ManifestError("invalid version in manifest") from error

    if not is_allowed_download_url(data["download_url"]):
        raise ManifestError("download_url is not an allowed https host")

    return {
        "version": data["version"],
        "notes": data["notes"],
        "download_url": data["download_url"],
    }
