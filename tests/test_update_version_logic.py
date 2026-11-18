from __future__ import annotations

import json

import pytest

from derby.core.updates.version_logic import (
    ManifestError,
    is_allowed_download_url,
    is_newer,
    parse_manifest,
    parse_version,
)


def test_parse_version():
    assert parse_version("1.0.1") == (1, 0, 1)
    assert parse_version("1.10.0") == (1, 10, 0)


def test_parse_version_invalid():
    with pytest.raises(ValueError):
        parse_version("1.0.a")
    with pytest.raises(ValueError):
        parse_version("")


def test_is_newer():
    assert is_newer("1.0.0", "1.0.1") is True
    assert is_newer("1.9.9", "1.10.0") is True
    assert is_newer("1.0.1", "1.0.1") is False
    assert is_newer("1.0.1", "1.0.0") is False


def test_allowed_download_hosts():
    assert is_allowed_download_url("https://github.com/user/repo/releases/tag/v1.0.1") is True
    assert is_allowed_download_url("https://objects.githubusercontent.com/x") is True
    assert is_allowed_download_url("https://raw.githubusercontent.com/x") is True
    assert is_allowed_download_url("http://github.com/user/repo") is False  # not https
    assert is_allowed_download_url("https://evil.com/download") is False
    assert is_allowed_download_url("https://github.com.evil.com/x") is False


def test_parse_manifest_valid():
    raw = json.dumps({"version": "1.0.1", "notes": "notes", "download_url": "https://github.com/a/b"})
    manifest = parse_manifest(raw)
    assert manifest["version"] == "1.0.1"
    assert manifest["download_url"] == "https://github.com/a/b"


def test_parse_manifest_invalid_json():
    with pytest.raises(ManifestError):
        parse_manifest("{not json")


def test_parse_manifest_missing_fields():
    with pytest.raises(ManifestError):
        parse_manifest(json.dumps({"version": "1.0.1"}))


def test_parse_manifest_rejects_non_https_download_url():
    raw = json.dumps({"version": "1.0.1", "notes": "x", "download_url": "http://github.com/a/b"})
    with pytest.raises(ManifestError):
        parse_manifest(raw)


def test_parse_manifest_rejects_non_github_download_url():
    raw = json.dumps({"version": "1.0.1", "notes": "x", "download_url": "https://evil.com/a"})
    with pytest.raises(ManifestError):
        parse_manifest(raw)
