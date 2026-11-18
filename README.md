# Derby — Cafe POS (Cashier) App

Derby is a Windows desktop point-of-sale app built for **Derby**, a cafe
with a PlayStation corner in Menoufia, Egypt. The UI is Arabic-only and
right-to-left. The app runs fully offline — the only network request in
the whole codebase is a manual "check for updates" button.

See [CLAUDE.md](CLAUDE.md) for engineering rules/conventions and
[docs/SPEC.md](docs/SPEC.md) for the full approved spec and phase plan.

## Status

| Phase | What | Status |
|---|---|---|
| 1 | Foundation — SQLite + migrations, PIN auth with lockout, roles/permissions, settings, main window shell, update check | ✅ done |
| 2 | Menu — categories, products, add-ons, CSV import/export, product images | ✅ done |
| 3 | Cashier & tables | ⏳ next |
| 4 | PlayStation | — |
| 5 | Printing | — |
| 6 | Expenses & reports | — |
| 7 | Daily closing, backup, WhatsApp report | — |
| 8 | Delivery (packaged installer) | — |

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
```

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
    theme/             colors, stylesheet, bundled font loader
    i18n/              ar.py — every Arabic string in the app
    utils/             money, time, business-day rule, PIN hashing, paths
    updates/           the one file allowed to touch the network
  features/
    auth/ settings/ shell/ menu/     <- built
    pos/ tables/ playstation/
    expenses/ reports/ closing/      <- not built yet
tests/
assets/fonts/
```

## Notes

- `menu/` (the cafe's real menu CSV + product photos) is intentionally
  **not** committed — see `.gitignore`. It's local-only data the owner
  imports through the app's Settings → Menu screen.
