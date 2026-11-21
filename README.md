# Derby — Cafe POS (Cashier) App

Derby is a Windows desktop point-of-sale app built for **Derby**, a cafe
with a PlayStation corner in Menoufia, Egypt. The UI is Arabic-only and
right-to-left. The app runs fully offline — the only network request in
the whole codebase is a manual "check for updates" button. Current
version: **1.1.0** — see [CHANGELOG.md](CHANGELOG.md) for what's new.

See [CLAUDE.md](CLAUDE.md) for engineering rules/conventions and
[docs/SPEC.md](docs/SPEC.md) for the full approved spec and phase plan.

## Features

- Sales & tables: cart, add-ons, discounts with owner approval and audit
  log, cash/InstaPay payment, sales log, takeaway orders.
- PlayStation corner billing: devices, Single/Multi hourly rates, timed
  sessions, bill transfer to/from a table.
- Menu: categories, products, add-ons, CSV import/export, product images.
- Expenses, with receipts and recurring expenses.
- Inventory & stock: ingredients, stock movements, recipes with cost and
  margin, purchases and suppliers.
- Profit report, and daily/monthly/custom-range reports exportable to
  Excel/CSV/PDF.
- Cash drawer (الخزنة): open/close, cash count, goods review.
- Home dashboard (إحصائيات اليوم): today's stats, new-invoice flow, and
  open orders at a glance.
- Daily closing, backup/restore, and a WhatsApp report hand-off (opens
  WhatsApp/the browser — the app itself never makes that request).
- A single manual "Check for Updates" button — the app's only other
  network request.

## Supported systems

Windows 7 SP1 (64-bit, with the Universal C Runtime update KB2999226
installed) or Windows 10 (64-bit). All data is local — there is no
cloud account, no telemetry, and the app works fully offline.

## تحميل / Download & update

**[Download the latest Derby installer](https://github.com/Dabash99/derpy_cashier/releases/latest)**
— or the current version directly:
[Derby-Setup-1.1.0.exe](https://github.com/Dabash99/derpy_cashier/releases/download/v1.1.0/Derby-Setup-1.1.0.exe).

Run the downloaded `Derby-Setup-*.exe` on Windows 7 SP1 (64-bit) or
Windows 10 (64-bit) and follow the installer — installing a new version
over an existing one upgrades it in place and never touches your data
(`%APPDATA%\Derby`, `Documents\Derby`). If Windows shows a blue
SmartScreen warning, click **"More info"** then **"Run anyway"** — this
is normal for a new app without a paid code-signing certificate.

Each release page lists a `SHA256SUMS.txt` asset alongside the
installer — compare it against the file you downloaded if you want to
verify it. The app's own Settings → "فحص التحديثات" button checks for
newer releases automatically against a fixed URL (manifest on the
`releases` branch, see [docs/RELEASING.md](docs/RELEASING.md)); there is
no Settings field for that URL — it is not user-editable. The button
never connects to the internet on its own otherwise.

## Status

| Phase | What | Status |
|---|---|---|
| 1 | Foundation — SQLite + migrations, PIN auth with lockout, roles/permissions, settings, main window shell, update check | ✅ done |
| 2 | Menu — categories, products, add-ons, CSV import/export, product images | ✅ done |
| 3 | Cashier & tables — cart, add-ons, discounts with approval + audit log, cash/InstaPay payment, sales log | ✅ done |
| 4 | PlayStation — devices, Single/Multi hourly rates, timed sessions, bill transfer to/from a table | ✅ done |
| 5 | Printing | deferred (no printer integration yet) |
| 6 | Expenses, reports, profit, export to Excel/CSV/PDF | ✅ done |
| 7 | Daily closing, backup/restore, WhatsApp report hand-off | ✅ done |
| 8 | Delivery — PyInstaller build, Inno Setup installer, user guide | ✅ done |
| 9 | Inventory, purchases/suppliers, recipes with cost/margin, profit report, cash drawer (الخزنة), home dashboard | ✅ done |
| 10 | Home: open-orders section, redesigned cashier product cards | ✅ done |

Past the original phase plan, the app has kept growing: a
supplies/shopping-list screen, an owner-only go-live data-cleanup tool, a
takeaway ("تيك أواي") order section with lazy draft creation, and the
Phase 9/10 work above. See `git log` and [CHANGELOG.md](CHANGELOG.md) for
the detailed history — the table tracks the original phase plan in
[docs/SPEC.md](docs/SPEC.md).

## Requirements

- **Python 3.8.x, 64-bit** (required — 3.9+ does not support Windows 7).
- Windows 7 SP1 64-bit (with UCRT update KB2999226) or Windows 10 64-bit.

## Setup

```bat
py -3.8 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## Run

```bat
run.bat
```
or directly:
```bash
.venv\Scripts\python.exe -m derby
```

On first run you'll be asked to set the cafe name, owner name, and owner
PIN. After that, login is PIN-only (no username).

## Test & lint

```bash
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m derby --selftest
```

## Building a release

```bat
.venv\Scripts\python.exe tools\make_release.py
```

Runs the quality gates, the PyInstaller build, and the Inno Setup
installer, and writes `release\version.json`. See
[docs/RELEASING.md](docs/RELEASING.md) for the full release/publish
flow and [CHANGELOG.md](CHANGELOG.md) for the version history.

## Tech stack

- **Python 3.8** + **PySide2 5.15.2.1** (Qt 5.15), `QtCore`/`QtGui`/`QtWidgets` only.
- **sqlite3** (standard library) with a plain repository layer — no ORM.
- Money is always an integer number of piasters (1 EGP = 100 piasters), never a float.
- Cairo font bundled under `assets/fonts/` (OFL-licensed, static weights).

## Project layout

```
derby/
  app.py              QApplication setup, font, RTL, single-instance, DB init, routing
  core/
    db/                connection, migrations, repositories
    theme/             tokens, stylesheet, fonts, icons, shared tab-bar helper
    i18n/              ar.py — every Arabic string in the app
    utils/             money, time, business-day rule, PIN hashing, paths
    updates/           update_check.py — the only HTTP request in the app
    integrations/      whatsapp.py — user-initiated hand-off, no HTTP request
  features/
    auth/ settings/ shell/
    menu/ pos/ tables/ playstation/ expenses/ reports/ closing/ supplies/
    dashboard/         إحصائيات اليوم (daily stats, separate from reports/)
assets/
  fonts/               Cairo + Montserrat, bundled and loaded via QFontDatabase
  logo/ brand/         source logo + generated brand PNGs/icons
tools/                 dev-time scripts: build, installer, previews, asset render
installer/             Inno Setup script + redistributables
release/               committed version.json + user-guide PDF; installer output is gitignored
tests/
```

See [CLAUDE.md](CLAUDE.md) for the full folder structure and the hard
engineering constraints (no networking beyond the update check and the
WhatsApp hand-off, Python 3.8-only syntax, PySide2 Qt Widgets only, money
as integer piasters, etc).

## Notes

- `menu/` (the cafe's real menu CSV + product photos) is intentionally
  **not** committed — see `.gitignore`. It's local-only data the owner
  imports through the app's Settings → Menu screen.
- The Arabic user guide lives at [docs/USER-GUIDE-AR.md](docs/USER-GUIDE-AR.md)
  and as a printable PDF at `release/دليل-استخدام-ديربي.pdf` (regenerate it
  with `tools/make_user_guide_pdf.py` after changing the guide).
- [docs/WIN7-CHECKLIST.md](docs/WIN7-CHECKLIST.md) is the manual test
  script for a real Windows 7 machine, and
  [docs/RELEASING.md](docs/RELEASING.md) covers building and publishing a
  release.
