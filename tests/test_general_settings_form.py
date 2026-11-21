from __future__ import annotations

from derby.features.settings.general_settings_form import GeneralSettingsForm


def _fill_minimum_valid_fields(form: GeneralSettingsForm) -> None:
    form._close_time_input.setText("23:59")


def test_save_rejects_invalid_close_time(qapp, db_conn):
    form = GeneralSettingsForm(db_conn)
    form._close_time_input.setText("not-a-time")
    form._on_save()

    assert form._error_label.text() != ""


def test_save_accepts_valid_fields(qapp, db_conn):
    form = GeneralSettingsForm(db_conn)
    _fill_minimum_valid_fields(form)
    form._on_save()

    assert form._error_label.text() == ""
