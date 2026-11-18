# Derby — Cafe POS (Cashier) App

Derby is a Windows desktop point-of-sale app for a cafe called "Derby" in
Menoufia, Egypt, which also has a PlayStation corner. It is built from
scratch in Python, Arabic-only UI, fully offline except for one manual
update-check button.

See [docs/SPEC.md](docs/SPEC.md) for the full approved spec and phase list.
This file covers engineering rules and conventions.

## Hard constraints

1. **No networking**, except the manual "فحص التحديثات" (check for updates)
   button in Settings. No telemetry, no auto-update, no accounts, no
   analytics, no crash reporting. All networking code lives only in
   `derby/core/updates/update_check.py`.
2. **Target OS**: Windows 7 SP1 64-bit AND Windows 10 64-bit, from one
   codebase. Windows 7 needs the Universal C Runtime update (KB2999226)
   installed — this is a Windows prerequisite, not something the app can
   install itself.
3. **Python 3.8.x 64-bit only.** 3.9+ does not run on Windows 7. Every module
   starts with `from __future__ import annotations`. No `match` statements,
   no `X | Y` union syntax, no builtin generics (`list[int]`) evaluated at
   runtime, no `str.removeprefix`/`removesuffix`. Import `ZoneInfo` via:
   ```python
   try:
       from zoneinfo import ZoneInfo
   except ImportError:
       from backports.zoneinfo import ZoneInfo
   ```
4. **GUI: PySide2 5.15.2.1 only** (not PySide6, not PyQt). Only `QtCore`,
   `QtGui`, `QtWidgets` are allowed. Never import `QtNetwork`,
   `QtWebEngine*`, `QtWebSockets`, `QtQml`, `QtQuick`, `QtMultimedia`,
   `Qt3D`, or `QtCharts`.
5. **UI is Arabic-only and RTL.** `app.setLayoutDirection(Qt.RightToLeft)`.
   The Cairo font is bundled under `assets/fonts/` and loaded with
   `QFontDatabase` — never fetched at runtime. `Qt.AA_EnableHighDpiScaling`
   is set before `QApplication` is constructed. All Arabic strings live in
   `derby/core/i18n/ar.py`.
6. **Keep it simple.** Small files, clear names, comments that explain
   *why* (not what), one feature per folder under `derby/features/`, no
   metaprogramming, no ORM. SQL lives in a repository layer using plain
   `sqlite3` from the standard library.

## Conventions

- **Money** is always an integer number of piasters (1 EGP = 100 piasters).
  Never use `float` for money. See `derby/core/utils/money.py`.
- **Timestamps** are stored in the database as UTC ISO-8601 strings, and
  converted to Africa/Cairo local time only for display. See
  `derby/core/utils/time_utils.py` and `business_date.py`.
- **Database**: `sqlite3`, file at `%APPDATA%\Derby\derby.db` (see
  `derby/core/utils/paths.py`). `PRAGMA journal_mode=WAL` and
  `PRAGMA foreign_keys=ON` are set on every connection. Schema changes are
  ordered migrations keyed off `PRAGMA user_version` in
  `derby/core/db/migrations.py` — always append, never edit a past
  migration.
- **Folder structure**:
  ```
  derby/
    __init__.py        __version__
    __main__.py         entry point (python -m derby)
    app.py              QApplication setup, font, RTL, single-instance, DB init, routing
    core/
      db/                connection.py, migrations.py, repositories (*_repo.py)
      theme/             colors.py, stylesheet.py
      i18n/              ar.py — all Arabic strings
      utils/             money.py, time_utils.py, business_date.py, pin_hash.py,
                         single_instance.py, paths.py
      updates/           update_check.py (only networking file), version_logic.py (pure)
    features/
      auth/ settings/ shell/              <- built in Phase 1
      menu/ pos/ tables/ playstation/
      expenses/ reports/ closing/          <- empty, README.md "Phase N" placeholders
  assets/fonts/          Cairo font + OFL license
  tests/
  ```

## Running and testing

```bat
run.bat
```
or directly:
```bash
.venv\Scripts\python.exe -m derby
```

Run tests:
```bash
.venv\Scripts\python.exe -m pytest
```

Lint:
```bash
.venv\Scripts\python.exe -m ruff check .
```

## Backups

Backups (Phase 7) must include the images folder `%APPDATA%\Derby\images`
alongside the database file — product photos live on disk, not in SQLite.

## Windows 7 requirements (for the machine running Derby)

- Windows 7 **Service Pack 1**, 64-bit.
- Universal C Runtime update **KB2999226** (or later cumulative update that
  includes it) — required for Python 3.8 / PySide2 to run at all.
- No other runtime is required; Python 3.8 + dependencies are bundled with
  the app's venv during installation on the target machine, or the app is
  packaged with PyInstaller in a later phase.
