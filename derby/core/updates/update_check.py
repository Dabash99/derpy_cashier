"""The ONLY file in Derby that makes a network request.

It is only ever triggered by the owner clicking "فحص التحديثات" in
Settings — never automatically. It fetches a small JSON manifest over
HTTPS, with a short timeout and no retries, and runs off the UI thread so
a slow or dead connection never freezes the app.
"""
from __future__ import annotations

import socket
import ssl
import urllib.error
import urllib.request
from typing import Optional
from urllib.parse import urlparse

from PySide2.QtCore import QThread, Signal

import derby
from derby.core.updates.version_logic import ManifestError, is_newer, parse_manifest

USER_AGENT = "Derby-Update-Check"
TIMEOUT_SECONDS = 5

FAILURE_OFFLINE = "offline"
FAILURE_SSL = "ssl"
FAILURE_INVALID = "invalid"


def _fetch_manifest_text(url: str) -> str:
    if urlparse(url).scheme != "https":
        raise ValueError("update_manifest_url must be https")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return response.read().decode("utf-8")


class UpdateCheckResult:
    def __init__(
        self,
        up_to_date: bool,
        version: str = "",
        notes: str = "",
        download_url: str = "",
        sha256: str = "",
    ) -> None:
        self.up_to_date = up_to_date
        self.version = version
        self.notes = notes
        self.download_url = download_url
        self.sha256 = sha256


class UpdateCheckWorker(QThread):
    """Runs the manifest fetch + parse off the UI thread."""

    succeeded = Signal(object)  # UpdateCheckResult
    failed = Signal(str)  # one of FAILURE_* category strings

    def __init__(self, manifest_url: str, parent: Optional[object] = None) -> None:
        super().__init__(parent)
        self._manifest_url = manifest_url

    def run(self) -> None:
        try:
            raw_text = _fetch_manifest_text(self._manifest_url)
        except ssl.SSLError:
            self.failed.emit(FAILURE_SSL)
            return
        except (urllib.error.URLError, socket.timeout, OSError, ValueError):
            self.failed.emit(FAILURE_OFFLINE)
            return

        try:
            manifest = parse_manifest(raw_text)
        except ManifestError:
            self.failed.emit(FAILURE_INVALID)
            return

        up_to_date = not is_newer(derby.__version__, manifest["version"])
        self.succeeded.emit(
            UpdateCheckResult(
                up_to_date=up_to_date,
                version=manifest["version"],
                notes=manifest["notes"],
                download_url=manifest["download_url"],
                sha256=manifest["sha256"],
            )
        )
