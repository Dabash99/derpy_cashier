"""Windows-version-dependent defaults. Phase 8: WhatsApp Desktop does not
run on Windows 7, so a fresh install on Windows 7 should default the
WhatsApp hand-off method to the browser instead.
"""
from __future__ import annotations

import sys


def default_whatsapp_method() -> str:
    """'browser' on Windows 7 (major 6, minor 1) -- WhatsApp Desktop is not
    available there; 'desktop' everywhere else (Windows 10, and any
    non-Windows dev/test environment, where getwindowsversion() does not
    exist at all)."""
    getwindowsversion = getattr(sys, "getwindowsversion", None)
    if getwindowsversion is None:
        return "desktop"
    version = getwindowsversion()
    if version.major == 6 and version.minor == 1:
        return "browser"
    return "desktop"
