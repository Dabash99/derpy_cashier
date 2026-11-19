"""Global exception hook (Phase 8/B1): logs any uncaught exception to a
small rotating local log file and shows a friendly Arabic dialog instead
of the app silently dying. Logs never leave this machine -- no network
call here or anywhere else in this module (see CLAUDE.md hard constraint 1).

Never logs PINs: traceback formatting here uses plain
traceback.format_exception() (file/line/function/message only, never
local variable values), and nothing in this codebase raises an exception
whose own message embeds a PIN -- see tests/test_error_log.py and
tests/test_policy.py.
"""
from __future__ import annotations

import logging
import logging.handlers
import sys
import traceback
from pathlib import Path
from typing import Optional

from derby.core.i18n import ar
from derby.core.utils.paths import app_data_dir

LOG_FILE_NAME = "derby.log"
MAX_BYTES = 1 * 1024 * 1024
BACKUP_COUNT = 3

_logger: Optional[logging.Logger] = None


def log_dir() -> Path:
    return app_data_dir() / "logs"


def log_path() -> Path:
    return log_dir() / LOG_FILE_NAME


def _get_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger
    logger = logging.getLogger("derby")
    logger.setLevel(logging.ERROR)
    log_dir().mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        str(log_path()), maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    _logger = logger
    return logger


def reset_logger_for_tests() -> None:
    """Test-only: drops the cached logger (and its file handle on the old
    log_path()) so a later call re-opens against a freshly-sandboxed
    DERBY_DATA_DIR."""
    global _logger
    if _logger is not None:
        for handler in list(_logger.handlers):
            handler.close()
            _logger.removeHandler(handler)
    _logger = None


def format_exception_text(exc_type, exc_value, exc_tb) -> str:
    """Plain traceback text -- file/line/function/message only, never
    local variable values, so a PIN held in a local variable at the
    moment of a crash can never end up here or in the log file."""
    return "".join(traceback.format_exception(exc_type, exc_value, exc_tb))


def log_exception(exc_type, exc_value, exc_tb) -> str:
    text = format_exception_text(exc_type, exc_value, exc_tb)
    try:
        _get_logger().error(text)
    except Exception:
        pass  # logging itself must never crash the crash handler
    return text


def install_exception_hook() -> None:
    def _hook(exc_type, exc_value, exc_tb):
        text = log_exception(exc_type, exc_value, exc_tb)
        try:
            _show_dialog(text)
        except Exception:
            pass  # showing the dialog must never crash the crash handler
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook


def _show_dialog(traceback_text: str) -> None:
    # Imported here, not at module top, so importing this module (e.g.
    # from a worker thread or --selftest before QApplication exists)
    # never pays for Qt GUI classes unless a dialog is actually shown.
    from PySide2.QtWidgets import QApplication, QMessageBox

    app = QApplication.instance()
    if app is None:
        return  # no GUI yet (e.g. a very early startup crash) -- log-only
    box = QMessageBox()
    box.setIcon(QMessageBox.Critical)
    box.setWindowTitle(ar.UNEXPECTED_ERROR_TITLE)
    box.setText(ar.UNEXPECTED_ERROR_MESSAGE.format(log_path=log_path()))
    copy_button = box.addButton(ar.UNEXPECTED_ERROR_COPY_BUTTON, QMessageBox.ActionRole)
    box.addButton(ar.GENERIC_OK, QMessageBox.AcceptRole)
    box.exec_()
    if box.clickedButton() is copy_button:
        app.clipboard().setText(traceback_text)
