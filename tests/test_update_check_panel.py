"""Only the panel's button-enabled/hint state -- never triggers the real
network call (clicking the button would), per the "no real network in
tests" rule.
"""
from __future__ import annotations

from derby.core.db import settings_repo
from derby.core.i18n import ar
from derby.features.settings.update_check_panel import UpdateCheckPanel


def test_button_disabled_when_url_empty(qapp, db_conn):
    panel = UpdateCheckPanel(db_conn)
    assert panel._check_button.isEnabled() is False
    assert panel._status_label.text() == ar.UPDATE_CHECK_NO_URL_HINT


def test_button_enabled_when_url_set(qapp, db_conn):
    settings_repo.set_value(db_conn, "update_manifest_url", "https://example.com/derby-manifest.json")
    panel = UpdateCheckPanel(db_conn)
    assert panel._check_button.isEnabled() is True
    assert panel._status_label.text() == ""


def test_reload_reflects_a_later_settings_change(qapp, db_conn):
    panel = UpdateCheckPanel(db_conn)
    assert panel._check_button.isEnabled() is False

    settings_repo.set_value(db_conn, "update_manifest_url", "https://example.com/derby-manifest.json")
    panel.reload()
    assert panel._check_button.isEnabled() is True
