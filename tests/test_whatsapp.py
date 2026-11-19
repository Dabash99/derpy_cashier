"""WhatsApp URL builders, validation, and fallbacks -- os.startfile and
webbrowser.open are ALWAYS mocked here; nothing in this file ever opens
a real app or browser."""
from __future__ import annotations

from derby.core.integrations import whatsapp


def test_validate_number_accepts_digits_with_country_code():
    ok, error = whatsapp.validate_number("201234567890")
    assert ok is True
    assert error == ""


def test_validate_number_rejects_non_digits():
    ok, error = whatsapp.validate_number("20abc")
    assert ok is False
    assert error != ""


def test_validate_number_rejects_too_short_or_too_long():
    assert whatsapp.validate_number("1234567")[0] is False  # 7 digits
    assert whatsapp.validate_number("1" * 16)[0] is False  # 16 digits


def test_egypt_local_hint_shown_for_11_digit_zero_prefixed_number():
    hint = whatsapp.egypt_local_hint("01234567890")
    assert hint is not None
    assert "20" in hint


def test_egypt_local_hint_none_for_already_international_number():
    assert whatsapp.egypt_local_hint("201234567890") is None


def test_build_desktop_url_and_web_url_schemes():
    desktop = whatsapp.build_desktop_url("201234567890", "مرحبا")
    web = whatsapp.build_web_url("201234567890", "مرحبا")
    assert desktop.startswith("whatsapp://send?phone=201234567890&text=")
    assert web.startswith("https://wa.me/201234567890?text=")


def test_url_round_trips_arabic_emojis_and_newlines():
    from urllib.parse import unquote

    text = "تقرير اليوم 📊\nصافي: 100 ج.م"
    url = whatsapp.build_web_url("201234567890", text)
    encoded = url.split("text=", 1)[1]
    assert unquote(encoded) == text


def test_open_report_with_no_number_copies_to_clipboard():
    copied = []
    result = whatsapp.open_report("desktop", "", "نص", clipboard_setter=copied.append)
    assert result.status == whatsapp.STATUS_COPIED
    assert copied == ["نص"]


def test_open_report_with_invalid_number_copies_to_clipboard():
    copied = []
    result = whatsapp.open_report("desktop", "abc", "نص", clipboard_setter=copied.append)
    assert result.status == whatsapp.STATUS_COPIED
    assert copied == ["نص"]


def test_open_report_method_copy_never_touches_os_or_browser(monkeypatch):
    monkeypatch.setattr(whatsapp.os, "startfile", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not be called")))
    monkeypatch.setattr(whatsapp.webbrowser, "open", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not be called")))
    copied = []
    result = whatsapp.open_report("copy", "201234567890", "نص", clipboard_setter=copied.append)
    assert result.status == whatsapp.STATUS_COPIED
    assert copied == ["نص"]


def test_open_report_desktop_calls_startfile_with_whatsapp_url(monkeypatch):
    calls = []
    monkeypatch.setattr(whatsapp.os, "startfile", lambda url: calls.append(url))
    result = whatsapp.open_report("desktop", "201234567890", "نص", clipboard_setter=lambda t: None)
    assert result.status == whatsapp.STATUS_OPENED_DESKTOP
    assert len(calls) == 1
    assert calls[0].startswith("whatsapp://send?")


def test_open_report_browser_calls_webbrowser_open_with_web_url(monkeypatch):
    calls = []
    monkeypatch.setattr(whatsapp.webbrowser, "open", lambda url: calls.append(url) or True)
    result = whatsapp.open_report("browser", "201234567890", "نص", clipboard_setter=lambda t: None)
    assert result.status == whatsapp.STATUS_OPENED_BROWSER
    assert len(calls) == 1
    assert calls[0].startswith("https://wa.me/")


def test_open_report_falls_back_to_clipboard_when_startfile_raises(monkeypatch):
    monkeypatch.setattr(whatsapp.os, "startfile", lambda url: (_ for _ in ()).throw(OSError("no whatsapp installed")))
    copied = []
    result = whatsapp.open_report("desktop", "201234567890", "نص", clipboard_setter=copied.append)
    assert result.status == whatsapp.STATUS_ERROR_COPIED
    assert copied == ["نص"]


def test_open_report_falls_back_to_clipboard_when_browser_open_returns_false(monkeypatch):
    monkeypatch.setattr(whatsapp.webbrowser, "open", lambda url: False)
    copied = []
    result = whatsapp.open_report("browser", "201234567890", "نص", clipboard_setter=copied.append)
    assert result.status == whatsapp.STATUS_ERROR_COPIED
    assert copied == ["نص"]


def test_very_long_text_falls_back_to_clipboard_instead_of_an_oversized_url():
    copied = []
    huge_text = "س" * 8000
    result = whatsapp.open_report("desktop", "201234567890", huge_text, clipboard_setter=copied.append)
    assert result.status == whatsapp.STATUS_COPIED
    assert copied == [huge_text]
