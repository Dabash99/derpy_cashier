"""Only the panel's button-enabled/hint state -- never triggers the real
network call (clicking the button would), per the "no real network in
tests" rule.
"""
from __future__ import annotations

from derby.core.i18n import ar
from derby.core.updates.update_check import FAILURE_OFFLINE, UpdateCheckResult
from derby.features.settings.update_check_panel import UpdateCheckPanel


def test_button_always_enabled(qapp, db_conn):
    panel = UpdateCheckPanel(db_conn)
    assert panel._check_button.isEnabled() is True
    assert panel._status_label.text() == ""


def test_on_succeeded_with_new_version_shows_notes_and_sha256(qapp, db_conn):
    panel = UpdateCheckPanel(db_conn)
    result = UpdateCheckResult(
        up_to_date=False, version="1.0.1", notes="إصلاحات صغيرة", download_url="https://github.com/a/b", sha256="a" * 64
    )
    panel._on_succeeded(result)

    text = panel._status_label.text()
    assert "1.0.1" in text
    assert "إصلاحات صغيرة" in text
    assert "a" * 64 in text
    assert panel._open_download_button.isHidden() is False


def test_on_succeeded_up_to_date_hides_download_button(qapp, db_conn):
    panel = UpdateCheckPanel(db_conn)
    result = UpdateCheckResult(up_to_date=True, version="1.0.0")
    panel._on_succeeded(result)

    assert panel._status_label.text() == ar.UPDATE_CHECK_UP_TO_DATE
    assert panel._open_download_button.isHidden() is True


def test_on_failed_shows_arabic_message(qapp, db_conn):
    panel = UpdateCheckPanel(db_conn)
    panel._on_failed(FAILURE_OFFLINE)

    assert panel._status_label.text() == ar.UPDATE_CHECK_FAILED_OFFLINE
    assert panel._check_button.isEnabled() is True
