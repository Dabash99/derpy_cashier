"""Only the panel's button-enabled/hint state -- never triggers the real
network call (clicking the button would), per the "no real network in
tests" rule.
"""
from __future__ import annotations

from derby.core.db import settings_repo
from derby.core.i18n import ar
from derby.core.updates.update_check import FAILURE_OFFLINE, UpdateCheckResult
from derby.features.settings.update_check_panel import UpdateCheckPanel


def test_button_enabled_by_default_prefilled_url(qapp, db_conn):
    # ensure_defaults() (via the db_conn fixture) prefills update_manifest_url
    # with the public releases repo's manifest URL -- see
    # derby/core/updates/version_logic.py:DEFAULT_UPDATE_MANIFEST_URL.
    panel = UpdateCheckPanel(db_conn)
    assert panel._check_button.isEnabled() is True
    assert panel._status_label.text() == ""


def test_button_disabled_when_url_empty(qapp, db_conn):
    settings_repo.set_value(db_conn, "update_manifest_url", "")
    panel = UpdateCheckPanel(db_conn)
    assert panel._check_button.isEnabled() is False
    assert panel._status_label.text() == ar.UPDATE_CHECK_NO_URL_HINT


def test_button_enabled_when_url_set(qapp, db_conn):
    settings_repo.set_value(db_conn, "update_manifest_url", "https://example.com/derby-manifest.json")
    panel = UpdateCheckPanel(db_conn)
    assert panel._check_button.isEnabled() is True
    assert panel._status_label.text() == ""


def test_reload_reflects_a_later_settings_change(qapp, db_conn):
    settings_repo.set_value(db_conn, "update_manifest_url", "")
    panel = UpdateCheckPanel(db_conn)
    assert panel._check_button.isEnabled() is False

    settings_repo.set_value(db_conn, "update_manifest_url", "https://example.com/derby-manifest.json")
    panel.reload()
    assert panel._check_button.isEnabled() is True


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
