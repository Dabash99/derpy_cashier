"""Drives the real GoLiveCleanupDialog/AdvancedToolsPanel widgets."""
from __future__ import annotations

from PySide2.QtWidgets import QDialog

from derby.core.db import settings_repo, users_repo
from derby.features.settings.advanced_tools_panel import AdvancedToolsPanel
from derby.features.settings.go_live_cleanup_dialog import GoLiveCleanupDialog


def test_wrong_pin_shows_error_and_stays_open(qapp, db_conn, tmp_path):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    settings_repo.set_value(db_conn, "backup_folder_primary", str(tmp_path / "backups"))

    dialog = GoLiveCleanupDialog(db_conn, owner, tmp_path / "test_derby.db")
    dialog._pin_input.setText("0000")
    dialog._word_input.setText("تصفية")
    dialog._on_confirm()

    assert dialog.result() != QDialog.Accepted
    assert dialog._error_label.text() != ""


def test_correct_pin_and_word_succeeds(qapp, db_conn, tmp_path):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    settings_repo.set_value(db_conn, "backup_folder_primary", str(tmp_path / "backups"))

    dialog = GoLiveCleanupDialog(db_conn, owner, tmp_path / "test_derby.db")
    dialog._pin_input.setText("1111")
    dialog._word_input.setText("تصفية")
    dialog._on_confirm()

    assert dialog.result() == QDialog.Accepted
    assert dialog.result_message != ""


def test_advanced_tools_panel_opens_dialog_and_shows_result(qapp, db_conn, tmp_path, monkeypatch):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    settings_repo.set_value(db_conn, "backup_folder_primary", str(tmp_path / "backups"))

    panel = AdvancedToolsPanel(db_conn, owner, tmp_path / "test_derby.db")

    def _fake_exec(self):
        self._pin_input.setText("1111")
        self._word_input.setText("تصفية")
        self._on_confirm()
        return QDialog.Accepted

    monkeypatch.setattr(GoLiveCleanupDialog, "exec_", _fake_exec)
    panel._on_cleanup()

    assert panel._status_label.text() != ""
