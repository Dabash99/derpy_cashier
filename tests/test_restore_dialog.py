"""Drives the real RestoreDialog -- every real folder (%APPDATA%, the
images/receipts dirs) is monkeypatched to a temp dir first."""
from __future__ import annotations

import pytest
from PySide2.QtWidgets import QFileDialog

from derby.core.db import users_repo
from derby.core.db.connection import connect
from derby.core.db.migrations import run_pending_migrations
from derby.features.closing import backup_service, restore_dialog, restore_service


@pytest.fixture()
def fake_app_data(tmp_path, monkeypatch):
    app_data = tmp_path / "appdata" / "Derby"
    app_data.mkdir(parents=True)
    monkeypatch.setattr("derby.features.closing.restore_dialog.app_data_dir", lambda: app_data)
    monkeypatch.setattr("derby.features.menu.images.app_data_dir", lambda: app_data)
    monkeypatch.setattr("derby.features.expenses.receipts.app_data_dir", lambda: app_data)
    return app_data


def test_confirm_requires_a_chosen_file(qapp, db_conn, fake_app_data, tmp_path):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    dialog = restore_dialog.RestoreDialog(db_conn, owner, tmp_path / "primary")
    dialog._pin_input.setText("1111")
    dialog._on_confirm()
    assert dialog.result() != dialog.Accepted  # nothing was ever picked


def test_confirm_rejects_corrupted_file(qapp, db_conn, fake_app_data, tmp_path):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    bogus = tmp_path / "bogus.db"
    bogus.write_bytes(b"not a database")

    dialog = restore_dialog.RestoreDialog(db_conn, owner, tmp_path / "primary")
    dialog._chosen_path = bogus
    dialog._pin_input.setText("1111")
    dialog._on_confirm()
    assert dialog.result() != dialog.Accepted
    assert dialog._error_label.text() != ""


def test_confirm_rejects_wrong_pin(qapp, db_conn, fake_app_data, tmp_path):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)

    good_backup = tmp_path / "good.db"
    source_db = tmp_path / "test_derby.db"  # db_conn's own file
    backup_service.backup_to_file(source_db, good_backup)

    dialog = restore_dialog.RestoreDialog(db_conn, owner, tmp_path / "primary")
    dialog._chosen_path = good_backup
    dialog._pin_input.setText("0000")
    dialog._on_confirm()
    assert dialog.result() != dialog.Accepted
    assert dialog._error_label.text() != ""


def test_confirm_stages_restore_and_accepts(qapp, db_conn, fake_app_data, tmp_path):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)

    good_backup = tmp_path / "good.db"
    source_db = tmp_path / "test_derby.db"
    backup_service.backup_to_file(source_db, good_backup)

    # A live db.db must exist at app_data_dir for the staged safety copy.
    live_conn = connect(fake_app_data / "derby.db")
    run_pending_migrations(live_conn)
    live_conn.close()

    dialog = restore_dialog.RestoreDialog(db_conn, owner, tmp_path / "primary")
    dialog._chosen_path = good_backup
    dialog._pin_input.setText("1111")
    dialog._on_confirm()

    assert dialog.result() == dialog.Accepted
    assert (fake_app_data / restore_service.MARKER_FILE_NAME).exists()


def test_pick_file_dialog_updates_label(qapp, db_conn, fake_app_data, tmp_path, monkeypatch):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    chosen = tmp_path / "chosen.db"
    chosen.write_text("x")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(chosen), "")))

    dialog = restore_dialog.RestoreDialog(db_conn, owner, tmp_path / "primary")
    dialog._on_pick_file()
    assert dialog._chosen_label.text() == "chosen.db"
