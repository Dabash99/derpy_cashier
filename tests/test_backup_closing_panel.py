"""Drives the real BackupClosingPanel, including its background workers
(waited for explicitly, then flushed, same pattern as test_export_panel.py)."""
from __future__ import annotations

from PySide2.QtWidgets import QApplication

from derby.core.db import backup_log_repo, day_closures_repo, settings_repo, users_repo
from derby.features.closing.backup_closing_panel import BackupClosingPanel


def _flush_events(times=30):
    for _ in range(times):
        QApplication.processEvents()


def _wait_worker(panel, times=30):
    if panel._worker is not None:
        panel._worker.wait(5000)
    _flush_events(times)


def test_save_persists_settings(qapp, db_conn, tmp_path):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    panel = BackupClosingPanel(db_conn, users_repo.get_user(db_conn, owner_id), tmp_path / "test_derby.db")

    panel._enable_checkbox.setChecked(False)
    panel._keep_count_input.setValue(10)
    panel._whatsapp_number_input.setText("201234567890")
    panel._primary_input.setText(str(tmp_path / "primary"))
    panel._on_save()

    assert settings_repo.get(db_conn, "closing_enabled") == "0"
    assert settings_repo.get(db_conn, "backup_keep_count") == "10"
    assert settings_repo.get(db_conn, "whatsapp_number") == "201234567890"


def test_save_rejects_invalid_whatsapp_number(qapp, db_conn, tmp_path):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    panel = BackupClosingPanel(db_conn, users_repo.get_user(db_conn, owner_id), tmp_path / "test_derby.db")
    panel._whatsapp_number_input.setText("abc")
    panel._on_save()
    assert panel._error_label.text() != ""


def test_egypt_local_hint_shown_live(qapp, db_conn, tmp_path):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    panel = BackupClosingPanel(db_conn, users_repo.get_user(db_conn, owner_id), tmp_path / "test_derby.db")
    panel._whatsapp_number_input.setText("01012345678")
    assert panel._whatsapp_hint_label.text() != ""


def test_same_drive_warning(qapp, db_conn, tmp_path):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    panel = BackupClosingPanel(db_conn, users_repo.get_user(db_conn, owner_id), tmp_path / "test_derby.db")
    panel._primary_input.setText(str(tmp_path / "a"))
    panel._secondary_input.setText(str(tmp_path / "b"))
    assert panel._same_drive_label.text() != ""


def test_backup_now_updates_status_and_log(qapp, db_conn, tmp_path):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    panel = BackupClosingPanel(db_conn, users_repo.get_user(db_conn, owner_id), tmp_path / "test_derby.db")
    panel._primary_input.setText(str(tmp_path / "primary"))

    panel._on_backup_now()
    _wait_worker(panel)

    assert ar_success_shown(panel)
    backups = backup_log_repo.list_backups(db_conn, target="primary")
    assert len(backups) == 1
    assert backups[0]["verified"] == 1


def ar_success_shown(panel):
    from derby.core.i18n import ar

    return panel._status_label.text().startswith(ar.CLOSING_BACKUP_SUCCESS)


def test_close_today_creates_a_closure(qapp, db_conn, tmp_path):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    panel = BackupClosingPanel(db_conn, users_repo.get_user(db_conn, owner_id), tmp_path / "test_derby.db")
    panel._primary_input.setText(str(tmp_path / "primary"))

    closed_signals = []
    panel.closed_today.connect(lambda: closed_signals.append(True))

    panel._on_close_today()
    _wait_worker(panel)

    assert closed_signals == [True]
    assert len(day_closures_repo.list_closures(db_conn)) == 1


def test_retry_secondary_after_primary_backup(qapp, db_conn, tmp_path):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    panel = BackupClosingPanel(db_conn, users_repo.get_user(db_conn, owner_id), tmp_path / "test_derby.db")
    panel._primary_input.setText(str(tmp_path / "primary"))
    panel._on_backup_now()
    _wait_worker(panel)

    panel._secondary_input.setText(str(tmp_path / "secondary"))
    panel._on_retry_secondary()
    _wait_worker(panel)

    secondary_backups = backup_log_repo.list_backups(db_conn, target="secondary")
    # The first backup_now (no secondary configured yet) logs a 'skipped'
    # row; the retry afterwards logs the real 'ok' one as the newest.
    assert secondary_backups[0]["status"] == "ok"


def test_test_folder_button_reports_success(qapp, db_conn, tmp_path):
    from PySide2.QtWidgets import QMessageBox

    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    panel = BackupClosingPanel(db_conn, users_repo.get_user(db_conn, owner_id), tmp_path / "test_derby.db")
    panel._primary_input.setText(str(tmp_path / "new_folder"))

    shown = []
    original = QMessageBox.information
    QMessageBox.information = staticmethod(lambda *a, **k: shown.append(a[2]))
    try:
        panel._on_test_folder(panel._primary_input)
    finally:
        QMessageBox.information = original

    from derby.core.i18n import ar

    assert shown == [ar.CLOSING_TEST_FOLDER_SUCCESS]
