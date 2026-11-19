"""Drives the real ClosingBannerWidget."""
from __future__ import annotations

from derby.core.db import backup_log_repo, day_closures_repo, settings_repo, users_repo
from derby.features.closing.closing_banner import ClosingBannerWidget


def _suppress_old_backup_warning(conn):
    backup_log_repo.log_backup(conn, "daily", "primary", "ok", verified=True)


def test_banner_lists_unsent_closures(qapp, db_conn):
    _suppress_old_backup_warning(db_conn)
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    day_closures_repo.create_closure(db_conn, "2026-01-10", "auto", "نص اليوم", 3, 5000, 0, 5000, 0, 0)

    banner = ClosingBannerWidget(db_conn, users_repo.get_user(db_conn, owner_id))
    assert banner._rows_layout.count() == 1


def test_mark_sent_removes_the_row(qapp, db_conn):
    _suppress_old_backup_warning(db_conn)
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    closure_id = day_closures_repo.create_closure(db_conn, "2026-01-10", "auto", "نص", 3, 5000, 0, 5000, 0, 0)
    closure = day_closures_repo.get_closure(db_conn, closure_id)

    banner = ClosingBannerWidget(db_conn, users_repo.get_user(db_conn, owner_id))
    banner._on_mark_sent(closure)
    assert banner._rows_layout.count() == 0
    assert day_closures_repo.get_closure(db_conn, closure_id)["sent_at_utc"] is not None


def test_whatsapp_copy_button_never_touches_os_or_browser(qapp, db_conn, monkeypatch):
    monkeypatch.setattr(
        "derby.core.integrations.whatsapp.os.startfile",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not call startfile")),
    )
    monkeypatch.setattr(
        "derby.core.integrations.whatsapp.webbrowser.open",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not call webbrowser")),
    )
    copied = []
    monkeypatch.setattr("derby.core.integrations.whatsapp._default_clipboard_setter", copied.append)

    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    settings_repo.set_value(db_conn, "whatsapp_number", "201234567890")
    closure_id = day_closures_repo.create_closure(db_conn, "2026-01-10", "auto", "نص التقرير", 3, 5000, 0, 5000, 0, 0)
    closure = day_closures_repo.get_closure(db_conn, closure_id)

    banner = ClosingBannerWidget(db_conn, users_repo.get_user(db_conn, owner_id))
    banner._on_send(closure, "copy")
    assert copied == ["نص التقرير"]


def test_old_backup_warning_shown_when_nothing_backed_up_yet(qapp, db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    banner = ClosingBannerWidget(db_conn, users_repo.get_user(db_conn, owner_id))
    assert banner._rows_layout.count() == 1  # just the old-backup warning, no closures
