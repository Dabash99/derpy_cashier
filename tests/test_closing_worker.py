"""Confirms ClosingWorker actually runs on its own connection/thread and
never blocks the caller -- waited for explicitly, same pattern as
tests/test_export_panel.py."""
from __future__ import annotations

import threading

from PySide2.QtWidgets import QApplication

from derby.core.db.connection import connect
from derby.core.db.migrations import MIGRATIONS, run_pending_migrations
from derby.features.closing.closing_worker import ClosingWorker


def _flush_events(times=20):
    for _ in range(times):
        QApplication.processEvents()


def test_worker_runs_on_a_different_thread_with_its_own_connection(qapp, tmp_path):
    db_path = tmp_path / "derby.db"
    conn = connect(db_path)
    run_pending_migrations(conn)
    conn.close()

    seen_thread_ids = []
    main_thread_id = threading.get_ident()

    def _work(worker_conn):
        seen_thread_ids.append(threading.get_ident())
        return worker_conn.execute("PRAGMA user_version").fetchone()[0]

    worker = ClosingWorker(db_path, _work)
    results = []
    worker.finished_ok.connect(results.append)
    worker.start()
    worker.wait(5000)
    _flush_events()

    assert results == [len(MIGRATIONS)]  # current schema version
    assert seen_thread_ids[0] != main_thread_id


def test_worker_reports_errors_without_crashing(qapp, tmp_path):
    db_path = tmp_path / "derby.db"
    conn = connect(db_path)
    run_pending_migrations(conn)
    conn.close()

    def _work(worker_conn):
        raise ValueError("بيانات غير صالحة")

    worker = ClosingWorker(db_path, _work)
    errors = []
    worker.finished_error.connect(errors.append)
    worker.start()
    worker.wait(5000)
    _flush_events()

    assert errors == ["بيانات غير صالحة"]
