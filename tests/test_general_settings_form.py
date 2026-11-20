from __future__ import annotations

from derby.core.db import settings_repo
from derby.core.i18n import ar
from derby.features.settings.general_settings_form import GeneralSettingsForm


def _fill_minimum_valid_fields(form: GeneralSettingsForm) -> None:
    form._close_time_input.setText("23:59")


def test_save_rejects_non_https_update_url(qapp, db_conn):
    form = GeneralSettingsForm(db_conn)
    _fill_minimum_valid_fields(form)
    before = settings_repo.get(db_conn, "update_manifest_url")

    form._update_url_input.setText("http://example.com/version.json")
    form._on_save()

    assert form._error_label.text() == ar.SETTINGS_ERROR_INVALID_UPDATE_URL
    assert settings_repo.get(db_conn, "update_manifest_url") == before


def test_save_accepts_https_update_url(qapp, db_conn):
    form = GeneralSettingsForm(db_conn)
    _fill_minimum_valid_fields(form)

    form._update_url_input.setText("https://example.com/version.json")
    form._on_save()

    assert form._error_label.text() == ""
    assert settings_repo.get(db_conn, "update_manifest_url") == "https://example.com/version.json"


def test_save_accepts_empty_update_url_to_disable_checking(qapp, db_conn):
    form = GeneralSettingsForm(db_conn)
    _fill_minimum_valid_fields(form)

    form._update_url_input.setText("")
    form._on_save()

    assert form._error_label.text() == ""
    assert settings_repo.get(db_conn, "update_manifest_url") == ""
