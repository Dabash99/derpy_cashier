# Derby — Cafe POS (Cashier) App

Derby is a Windows desktop point-of-sale app for a cafe called "Derby" in
Menoufia, Egypt, which also has a PlayStation corner. It is built from
scratch in Python, Arabic-only UI, fully offline except for one manual
update-check button.

See [docs/SPEC.md](docs/SPEC.md) for the full approved spec and phase list.
See [docs/BRAND.md](docs/BRAND.md) for the fixed brand palette, logo
rules, and typography — colors there are decisions, not suggestions.
This file covers engineering rules and conventions.

## Hard constraints

1. **No networking**, except the manual "فحص التحديثات" (check for updates)
   button in Settings (`derby/core/updates/update_check.py`) and the
   WhatsApp report hand-off (`derby/core/integrations/whatsapp.py`,
   Phase 7). The app itself still makes no network request in either
   case: WhatsApp is a user-initiated hand-off to WhatsApp Desktop
   (`whatsapp://send?`) or the owner's own browser (`https://wa.me/`)
   via `os.startfile`/`webbrowser.open`, with a clipboard-copy fallback
   if that fails — never an HTTP request this process makes. No
   telemetry, no auto-update, no accounts, no analytics, no crash
   reporting. `os.startfile`/`webbrowser.open` are confined to
   `whatsapp.py`, `update_check_panel.py` (open the download page), and
   `export_panel.py` (open a local export folder — not a network call);
   `urllib.request` stays confined to `update_check.py`. See
   `tests/test_policy.py`.
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
   `QtGui`, `QtWidgets` are allowed in `derby/`. Never import `QtNetwork`,
   `QtWebEngine*`, `QtWebSockets`, `QtQml`, `QtQuick`, `QtMultimedia`,
   `Qt3D`, `QtCharts`, or `QtSvg` there. `QtSvg` is allowed **only** in
   `tools/` dev-time asset scripts (e.g. `tools/render_assets.py`) — the
   shipped app loads only pre-rendered PNGs via `QIcon`/`QPixmap`, never
   SVG at runtime. See `tests/test_policy.py`.
5. **UI is Arabic-only and RTL.** `app.setLayoutDirection(Qt.RightToLeft)`.
   The Cairo font is bundled under `assets/fonts/` and loaded with
   `QFontDatabase` — never fetched at runtime. `Qt.AA_EnableHighDpiScaling`
   is set before `QApplication` is constructed. All Arabic strings live in
   `derby/core/i18n/ar.py`. Latin brand text, numbers, and big numeric
   displays (totals/prices/timers) use Montserrat (static weights, also
   loaded via `QFontDatabase`, with graceful fallback to Cairo/the Qt
   default if the files are absent — see `derby/core/theme/fonts.py`).
   See [docs/BRAND.md](docs/BRAND.md) for the fixed color palette and
   logo rules; `derby/core/theme/tokens.py` is the source of truth for
   the spacing/radius/font/control-height scale that `stylesheet.py`
   consumes.
6. **Keep it simple.** Small files, clear names, comments that explain
   *why* (not what), one feature per folder under `derby/features/`, no
   metaprogramming, no ORM. SQL lives in a repository layer using plain
   `sqlite3` from the standard library.

## Conventions

- **Money** is always an integer number of piasters (1 EGP = 100 piasters).
  Never use `float` for money. See `derby/core/utils/money.py`.
- **PlayStation session pricing**: each session line (single or multi) is
  rounded to the nearest `rounding_step_egp` independently at the moment it
  is billed — a visit with several sessions is the sum of already-rounded
  lines, not one rounding of the visit's total. See
  `derby/features/playstation/pricing.py`.
- **Reports** (`derby/features/reports/report_service.py`) share one
  definition of every figure across the daily/monthly/custom-range views
  and every export format:
  - Sales = paid orders only (void/cancelled excluded). Net sales =
    `SUM(total_piasters)`, i.e. *after* each order's own discount.
  - Top items and sales-by-category are computed straight from
    `order_items`, so they are **gross** — before the order-level
    discount — and the screen must say so next to them.
  - PlayStation hours = `SUM(actual_minutes) / 60` of `ps_time` lines
    still attached to a paid order; a removed (voided) line has no
    `order_items` row left, so it drops out with no extra filter.
  - Profit = net sales − active expenses in the same range (simple cash
    basis, no cost of goods; can be negative).
  - Average per day = net sales ÷ `days_elapsed`, where `days_elapsed`
    is the whole range if it already ended before "today", or only the
    days up to and including "today" if the range is still ongoing.
- **Timestamps** are stored in the database as UTC ISO-8601 strings, and
  converted to Africa/Cairo local time only for display. See
  `derby/core/utils/time_utils.py` and `business_date.py`.
- **Database**: `sqlite3`, file at `%APPDATA%\Derby\derby.db` (see
  `derby/core/utils/paths.py`, which also honors the `DERBY_DATA_DIR` and
  `DERBY_DOCS_DIR` environment overrides used by tests, previews, and
  `--selftest` — no module computes `%APPDATA%`/`%USERPROFILE%` or any
  other real user path on its own; every path goes through `paths.py`).
  `PRAGMA journal_mode=WAL` and
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
      theme/             tokens.py, stylesheet.py, fonts.py, icons.py
      i18n/              ar.py — all Arabic strings
      utils/             money.py, time_utils.py, business_date.py, pin_hash.py,
                         single_instance.py, paths.py, resource_path.py,
                         platform_info.py, error_log.py
      updates/           update_check.py, version_logic.py (pure)
      integrations/      whatsapp.py (the other allowed networking-adjacent file)
      selftest.py         `python -m derby --selftest` (Phase 8)
    features/
      auth/ settings/ shell/              <- built in Phase 1
      menu/ pos/ tables/ playstation/ expenses/ reports/ closing/ supplies/
      dashboard/           إحصائيات اليوم (daily stats, separate from reports/)
  assets/
    fonts/               Cairo + Montserrat (static weights) + OFL license
    logo/                original source logo (SVG + PNG) — never edited
    brand/               generated PNGs (logo variants, icon set) — only
                         regenerated via tools/render_assets.py
    derby.ico             generated by tools/make_icon.py
  tools/                 dev-time-only scripts: render_assets.py,
                         make_icon.py, make_installer_images.py,
                         make_user_guide_pdf.py, preview_screens.py,
                         build.py, build_installer.py, version_info.py,
                         write_installer_version.py, write_version_json.py
                         (may import QtSvg; never shipped/frozen)
  installer/             derby.iss (Inno Setup) + version.iss (generated) + redist/
  derby.spec              PyInstaller spec (one-dir, see tools/build.py)
  release/                build output: version.json + guide PDF are
                         committed; Derby-Setup-*.exe/SHA256SUMS.txt are
                         generated, gitignored
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
and the receipts folder `%APPDATA%\Derby\receipts` alongside the database
file — product photos and expense receipts both live on disk, not in SQLite.

## Windows 7 requirements (for the machine running Derby)

- Windows 7 **Service Pack 1**, 64-bit.
- Universal C Runtime update **KB2999226** (or later cumulative update that
  includes it) — required for Python 3.8 / PySide2 to run at all.
- No other runtime is required; Python 3.8 + dependencies are bundled
  into the PyInstaller one-dir build (`derby.spec`, Phase 8) — see
  [docs/WIN7-CHECKLIST.md](docs/WIN7-CHECKLIST.md) for the manual test
  script and [docs/RELEASING.md](docs/RELEASING.md) for building/
  publishing a release.
