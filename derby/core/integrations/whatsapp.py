"""Hands the daily report off to WhatsApp -- the app itself still makes
NO network request. Opening WhatsApp Desktop or the owner's browser, or
copying to the clipboard, is a user-initiated hand-off to the OS, not a
request this process makes. This is the ONLY file (besides
derby/core/updates/update_check.py) allowed to call os.startfile or
webbrowser.open -- see tests/test_policy.py.
"""
from __future__ import annotations

import os
import re
import webbrowser
from typing import Callable, Optional, Tuple
from urllib.parse import quote

from derby.core.i18n import ar

METHOD_DESKTOP = "desktop"
METHOD_BROWSER = "browser"
METHOD_COPY = "copy"

MAX_URL_LENGTH = 7000
_DIGITS_PATTERN = re.compile(r"^\d+$")

STATUS_OPENED_DESKTOP = "opened_desktop"
STATUS_OPENED_BROWSER = "opened_browser"
STATUS_COPIED = "copied"
STATUS_ERROR_COPIED = "error_copied"


class WhatsAppResult:
    def __init__(self, status: str, message: str) -> None:
        self.status = status
        self.message = message


def validate_number(raw: str) -> Tuple[bool, str]:
    """Digits only, 8-15 digits (with country code). Does not reject an
    Egyptian local-looking number -- see egypt_local_hint for that, which
    is a suggestion, not a rejection."""
    text = (raw or "").strip()
    if not text or not _DIGITS_PATTERN.match(text):
        return False, ar.WHATSAPP_ERROR_DIGITS_ONLY
    if not (8 <= len(text) <= 15):
        return False, ar.WHATSAPP_ERROR_LENGTH
    return True, ""


def egypt_local_hint(raw: str) -> Optional[str]:
    text = (raw or "").strip()
    if text.startswith("0") and len(text) == 11 and _DIGITS_PATTERN.match(text):
        return ar.WHATSAPP_HINT_EGYPT_LOCAL
    return None


def build_desktop_url(number: str, text: str) -> str:
    return "whatsapp://send?phone={0}&text={1}".format(number, quote(text, safe=""))


def build_web_url(number: str, text: str) -> str:
    return "https://wa.me/{0}?text={1}".format(number, quote(text, safe=""))


def _default_clipboard_setter(text: str) -> None:
    from PySide2.QtWidgets import QApplication

    clipboard = QApplication.clipboard()
    if clipboard is not None:
        clipboard.setText(text)


def open_report(
    method: str, number: str, text: str, clipboard_setter: Optional[Callable[[str], None]] = None
) -> WhatsAppResult:
    """Opens WhatsApp Desktop or the browser with the report pre-filled,
    with clipboard-copy fallbacks whenever that is not possible: no
    number, an invalid number, a too-long URL, or the hand-off itself
    raising (e.g. WhatsApp Desktop not installed)."""
    set_clipboard = clipboard_setter or _default_clipboard_setter
    number = (number or "").strip()

    if not number:
        set_clipboard(text)
        return WhatsAppResult(STATUS_COPIED, ar.WHATSAPP_NO_NUMBER_COPIED)

    is_valid, error = validate_number(number)
    if not is_valid:
        set_clipboard(text)
        return WhatsAppResult(STATUS_COPIED, error)

    if method == METHOD_COPY:
        set_clipboard(text)
        return WhatsAppResult(STATUS_COPIED, ar.WHATSAPP_COPIED)

    url = build_desktop_url(number, text) if method == METHOD_DESKTOP else build_web_url(number, text)
    if len(url) > MAX_URL_LENGTH:
        set_clipboard(text)
        return WhatsAppResult(STATUS_COPIED, ar.WHATSAPP_TOO_LONG_COPIED)

    try:
        if method == METHOD_DESKTOP:
            os.startfile(url)  # noqa: S606 -- a whatsapp:// hand-off, not a local path
            return WhatsAppResult(STATUS_OPENED_DESKTOP, ar.WHATSAPP_OPENED_DESKTOP)
        opened = webbrowser.open(build_web_url(number, text))
        if not opened:
            raise OSError("webbrowser.open returned False")
        return WhatsAppResult(STATUS_OPENED_BROWSER, ar.WHATSAPP_OPENED_BROWSER)
    except Exception as error:  # noqa: BLE001 -- any hand-off failure falls back to the clipboard
        set_clipboard(text)
        return WhatsAppResult(STATUS_ERROR_COPIED, ar.WHATSAPP_FAILED_COPIED.format(error=str(error)))
