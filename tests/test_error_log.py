"""The global exception hook must log to a small rotating local file and
never include PINs -- see the module docstring on error_log.py for why
plain traceback formatting is safe by construction."""
from __future__ import annotations

import logging

import pytest

from derby.core.utils import error_log


@pytest.fixture(autouse=True)
def _reset_error_logger():
    error_log.reset_logger_for_tests()
    yield
    error_log.reset_logger_for_tests()


def test_log_path_is_under_app_data_dir_logs_subfolder():
    from derby.core.utils.paths import app_data_dir

    assert error_log.log_path() == app_data_dir() / "logs" / "derby.log"


def test_log_exception_writes_the_traceback_to_the_log_file():
    try:
        raise ValueError("a deliberately raised test error")
    except ValueError:
        import sys

        exc_type, exc_value, exc_tb = sys.exc_info()
        text = error_log.log_exception(exc_type, exc_value, exc_tb)

    assert "a deliberately raised test error" in text
    assert error_log.log_path().exists()
    logged = error_log.log_path().read_text(encoding="utf-8")
    assert "a deliberately raised test error" in logged
    assert "ValueError" in logged


def test_rotating_handler_caps_log_file_size(monkeypatch):
    monkeypatch.setattr(error_log, "MAX_BYTES", 2000)
    monkeypatch.setattr(error_log, "BACKUP_COUNT", 2)

    for i in range(200):
        try:
            raise RuntimeError("padding error number {0} with some extra filler text".format(i))
        except RuntimeError:
            import sys

            error_log.log_exception(*sys.exc_info())

    assert error_log.log_path().stat().st_size <= error_log.MAX_BYTES * 1.5  # a little slack for the final record
    rotated = list(error_log.log_dir().glob("derby.log.*"))
    assert len(rotated) <= error_log.BACKUP_COUNT


def test_format_exception_text_never_contains_local_variable_dump():
    """A PIN held in a local variable at crash time must never reach the
    log. traceback.format_exception() (used here) only ever includes
    file/line/function/message, never variable values -- prove it by
    putting an obviously-identifiable "PIN-shaped" local in the frame and
    confirming it is absent from the formatted text."""
    import sys

    def _crash():
        pin = "947261"  # noqa: F841 -- deliberately unused, just needs to exist as a local
        raise RuntimeError("boom")

    try:
        _crash()
    except RuntimeError:
        exc_type, exc_value, exc_tb = sys.exc_info()
        text = error_log.format_exception_text(exc_type, exc_value, exc_tb)

    assert "947261" not in text


def test_install_exception_hook_sets_sys_excepthook():
    import sys

    original = sys.excepthook
    try:
        error_log.install_exception_hook()
        assert sys.excepthook is not original
        assert sys.excepthook is not sys.__excepthook__
    finally:
        sys.excepthook = original


def test_show_dialog_builds_and_closes_without_crashing_under_offscreen_qt(qapp, monkeypatch):
    from PySide2.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "exec_", lambda self: None)
    error_log._show_dialog("some traceback text")  # must not raise


def test_logger_is_a_plain_python_logger_not_propagating_to_root(caplog):
    with caplog.at_level(logging.ERROR):
        try:
            raise KeyError("should not leak to the root logger/caplog")
        except KeyError:
            import sys

            error_log.log_exception(*sys.exc_info())
    assert "should not leak to the root logger/caplog" not in caplog.text
