"""Dev-time ONLY: rough startup-time and idle-RAM numbers for the UI fix
pass's acceptance report. Builds the real MainWindow (owner role) against
a synthetic temp database under offscreen Qt -- same technique as
tools/preview_screens.py, never real user data.

Usage:
    .venv\\Scripts\\python.exe tools\\measure_startup.py
"""
from __future__ import annotations

import ctypes
import os
import sys
import tempfile
import time
from pathlib import Path

_work_dir = Path(tempfile.mkdtemp(prefix="derby_measure_"))
os.environ["DERBY_DATA_DIR"] = str(_work_dir / "appdata" / "Derby")
os.environ["DERBY_DOCS_DIR"] = str(_work_dir / "documents_derby" / "Derby")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

_t0 = time.perf_counter()

from PySide2.QtCore import Qt  # noqa: E402
from PySide2.QtGui import QFont  # noqa: E402
from PySide2.QtWidgets import QApplication  # noqa: E402

from derby.core.db import settings_repo, users_repo  # noqa: E402
from derby.core.db.connection import connect  # noqa: E402
from derby.core.db.migrations import run_pending_migrations  # noqa: E402
from derby.core.theme.fonts import CAIRO_FAMILY, load_bundled_fonts  # noqa: E402
from derby.core.theme.stylesheet import build_stylesheet  # noqa: E402
from derby.features.shell.idle_filter import IdleTimer  # noqa: E402
from derby.features.shell.main_window import MainWindow  # noqa: E402

_t_imports_done = time.perf_counter()


def _working_set_mb() -> float:
    """Current process's resident memory (Windows) via psapi -- no new
    dependency (ctypes is stdlib), same approach as platform_info.py's
    AppUserModelID call. Returns 0.0 off-Windows."""
    try:
        import ctypes.wintypes as wintypes

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        ctypes.windll.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wintypes.DWORD,
        ]
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        ok = ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
        if not ok:
            return 0.0
        return counters.WorkingSetSize / (1024 * 1024)
    except (AttributeError, OSError):
        return 0.0


def main() -> int:
    app = QApplication.instance() or QApplication([])
    app.setLayoutDirection(Qt.RightToLeft)
    load_bundled_fonts()
    app.setFont(QFont(CAIRO_FAMILY, 10))
    app.setStyleSheet(build_stylesheet())

    db_path = _work_dir / "measure.db"
    conn = connect(db_path)
    run_pending_migrations(conn)
    settings_repo.ensure_defaults(conn)
    owner_id = users_repo.create_user(conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(conn, owner_id)

    t_before_window = time.perf_counter()
    mw = MainWindow(conn, owner, IdleTimer(), db_path)
    mw.resize(1100, 720)
    mw.show()
    for _ in range(30):
        app.processEvents()
    t_after_window = time.perf_counter()

    conn.close()

    print("imports:              {0:.0f} ms".format((_t_imports_done - _t0) * 1000))
    print("MainWindow construct:  {0:.0f} ms".format((t_after_window - t_before_window) * 1000))
    print("total (import->shown): {0:.0f} ms".format((t_after_window - _t0) * 1000))
    print("idle working set:      {0:.1f} MB".format(_working_set_mb()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
