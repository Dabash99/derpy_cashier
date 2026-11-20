"""Exercises UpdateCheckWorker.run() directly (never .start() -- running it
as a plain method call keeps this synchronous and off any real thread)
against a mocked urllib opener. No test here ever touches the real
network -- see tests/test_policy.py and CLAUDE.md's "no networking"
hard constraint.
"""
from __future__ import annotations

import json
import socket
import ssl
import urllib.error

import pytest

from derby.core.updates import update_check

VALID_SHA256 = "a" * 64


def _make_worker(monkeypatch, *, text=None, raises=None, url="https://raw.githubusercontent.com/x/y/version.json"):
    def fake_fetch(manifest_url):
        assert manifest_url == url
        if raises is not None:
            raise raises
        return text

    monkeypatch.setattr(update_check, "_fetch_manifest_text", fake_fetch)
    return update_check.UpdateCheckWorker(url)


def _run_and_capture(worker):
    results = {}
    worker.succeeded.connect(lambda result: results.setdefault("succeeded", result))
    worker.failed.connect(lambda category: results.setdefault("failed", category))
    worker.run()
    return results


def _manifest(version="1.0.1", download_url="https://github.com/a/b", sha256=VALID_SHA256, notes="x"):
    return json.dumps({"version": version, "notes": notes, "download_url": download_url, "sha256": sha256})


def test_newer_version_available(qapp, monkeypatch):
    monkeypatch.setattr(update_check.derby, "__version__", "1.0.0")
    worker = _make_worker(monkeypatch, text=_manifest(version="1.0.1"))
    results = _run_and_capture(worker)

    result = results["succeeded"]
    assert result.up_to_date is False
    assert result.version == "1.0.1"
    assert result.sha256 == VALID_SHA256
    assert "failed" not in results


def test_same_version_is_up_to_date(qapp, monkeypatch):
    monkeypatch.setattr(update_check.derby, "__version__", "1.0.0")
    worker = _make_worker(monkeypatch, text=_manifest(version="1.0.0"))
    results = _run_and_capture(worker)

    assert results["succeeded"].up_to_date is True


def test_older_version_on_server_is_treated_as_up_to_date(qapp, monkeypatch):
    monkeypatch.setattr(update_check.derby, "__version__", "2.0.0")
    worker = _make_worker(monkeypatch, text=_manifest(version="1.0.0"))
    results = _run_and_capture(worker)

    assert results["succeeded"].up_to_date is True


@pytest.mark.parametrize(
    "exception",
    [
        urllib.error.URLError("no connection"),
        socket.timeout("timed out"),
        urllib.error.HTTPError("https://x", 404, "Not Found", {}, None),
        OSError("offline"),
    ],
    ids=["url_error", "timeout", "http_404", "os_error"],
)
def test_network_failures_report_offline(qapp, monkeypatch, exception):
    worker = _make_worker(monkeypatch, raises=exception)
    results = _run_and_capture(worker)

    assert results["failed"] == update_check.FAILURE_OFFLINE
    assert "succeeded" not in results


def test_ssl_failure_reports_ssl_category(qapp, monkeypatch):
    worker = _make_worker(monkeypatch, raises=ssl.SSLError("bad cert"))
    results = _run_and_capture(worker)

    assert results["failed"] == update_check.FAILURE_SSL


def test_invalid_json_reports_invalid_category(qapp, monkeypatch):
    worker = _make_worker(monkeypatch, text="{not json")
    results = _run_and_capture(worker)

    assert results["failed"] == update_check.FAILURE_INVALID


def test_missing_keys_reports_invalid_category(qapp, monkeypatch):
    worker = _make_worker(monkeypatch, text=json.dumps({"version": "1.0.1"}))
    results = _run_and_capture(worker)

    assert results["failed"] == update_check.FAILURE_INVALID


def test_malformed_download_host_reports_invalid_category(qapp, monkeypatch):
    worker = _make_worker(monkeypatch, text=_manifest(download_url="https://evil.com/a"))
    results = _run_and_capture(worker)

    assert results["failed"] == update_check.FAILURE_INVALID


def test_non_https_manifest_url_is_rejected_without_network(qapp, monkeypatch):
    # _fetch_manifest_text itself (not mocked here) must refuse a non-https
    # URL before ever calling urllib.request.urlopen.
    worker = update_check.UpdateCheckWorker("http://example.com/version.json")
    results = _run_and_capture(worker)

    assert results["failed"] == update_check.FAILURE_OFFLINE
