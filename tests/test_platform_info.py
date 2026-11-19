"""Windows 7 does not run WhatsApp Desktop, so a fresh install there must
default whatsapp_method to the browser hand-off instead. Mocked --
these tests must pass whether or not they actually run on Windows."""
from __future__ import annotations

import sys
import types

from derby.core.utils import platform_info


def _fake_windows_version(major, minor):
    return types.SimpleNamespace(major=major, minor=minor)


def test_windows_7_defaults_to_browser(monkeypatch):
    monkeypatch.setattr(sys, "getwindowsversion", lambda: _fake_windows_version(6, 1), raising=False)
    assert platform_info.default_whatsapp_method() == "browser"


def test_windows_10_defaults_to_desktop(monkeypatch):
    monkeypatch.setattr(sys, "getwindowsversion", lambda: _fake_windows_version(10, 0), raising=False)
    assert platform_info.default_whatsapp_method() == "desktop"


def test_windows_8_1_defaults_to_desktop(monkeypatch):
    # Only exactly 6.1 (Windows 7) lacks WhatsApp Desktop support here --
    # 6.2/6.3 (Windows 8/8.1) are not specifically called out by the spec.
    monkeypatch.setattr(sys, "getwindowsversion", lambda: _fake_windows_version(6, 3), raising=False)
    assert platform_info.default_whatsapp_method() == "desktop"


def test_non_windows_defaults_to_desktop(monkeypatch):
    monkeypatch.delattr(sys, "getwindowsversion", raising=False)
    assert platform_info.default_whatsapp_method() == "desktop"
