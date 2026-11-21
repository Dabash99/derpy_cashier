# Fix: login crash + waste-cost business-day boundary + one-time cache clear

## Root cause and fix of the login crash (Task 0)

**Root cause** (found from the real log, `C:\Users\Ahmed\AppData\Roaming\Derby\logs\derby.log`,
not guessed): `sqlite3.OperationalError: no such column: is_historical`,
raised from `drawer_repo.get_last_opening_entry` the moment الرئيسية
tried to read the cash-in-drawer figure, right after login.

The real history: `drawer_entries.is_historical` was added by editing
migration 0009's body *in place*, during the same earlier session that
first wrote it — a violation of this project's own "never edit a past
migration" rule, which went unnoticed at the time because no release
had shipped yet. In between, though, this exact dev machine had
already run the ORIGINAL (column-less) migration 0009 for real, via
`run.bat`, which set `PRAGMA user_version` to 9 on the real
`%APPDATA%\Derby\derby.db`. Migrations are version-gated and never
re-run once applied, so that database's `drawer_entries` table
permanently lacks the column — and every later attempt to read OR
write a drawer_entries row (the dashboard tile, any cash sale, expense,
purchase, or drawer action) raises the same error. I confirmed this
directly: copying the real `derby.db` (together with its `-wal`/`-shm`
files — the live data was in WAL, not yet checkpointed into the main
file) into a sandbox showed `user_version = 10` and a `drawer_entries`
table with 8 columns, missing `is_historical`, with 0 rows (consistent
with every write attempt having failed the same way since the schema
drifted). The real database was never written to in the course of this
diagnosis — only read-only copies were touched.

**Fix:**
- New migration `0011_drawer_entries_is_historical_repair`
  (`derby/core/db/migrations.py`): defensively checks
  `PRAGMA table_info(drawer_entries)` and only adds the column if it is
  genuinely missing (a database created from the *current*
  `migrations.py` already has it from migration 0009 itself, so this
  is then a complete no-op). When it does add the column, every
  existing row is marked `is_historical = 1` — safe, because with the
  column missing, no row could have been written by any live
  `drawer_repo.create_entry()` call either (that INSERT always names
  `is_historical`), so every row already in the table at that point can
  only be from migration 0009's own one-time historical backfill.
- Verified the fix against a real-shaped copy of the actual database:
  ran the app's normal `migrate_with_pre_backup` path on it, confirmed
  `is_historical` appears and الرئيسية now builds for the owner role
  without error. (The test copy and its one side effect — a
  pre-migration backup file it wrote into the real
  `Documents\Derby\Backups` folder, since that setting wasn't
  sandboxed — were both cleaned up afterward; your real `derby.db` is
  untouched, still at `user_version = 10`.)
- **Defense in depth**, independent of the specific bug: الرئيسية's
  cash-in-drawer and low-stock tiles are now wrapped in a small
  `_safe()` helper (`daily_stats_screen.py`) that catches any exception,
  logs it the same way the app's global crash handler would (so it
  still ends up in `derby.log`), and falls back to a placeholder
  ("—", or "افتح الدرج" specifically when the drawer has no live
  opening entry) instead of taking down the whole dashboard. This means
  a *future* bug in either lookup can no longer crash login the same
  way, even if its root cause is different from this one.
- Added regression tests (`tests/test_dashboard_crash_regression.py`)
  building the dashboard for both roles against: a fresh database, a
  database with the exact real-world schema drift reproduced
  structurally (drawer_entries rebuilt without the column, a
  historical-shaped row inserted, then migrated forward), and a
  database with a real opening entry and a paid sale. All must build
  and `reload()` without raising.

## What changed (Task 1 — waste cost now uses the cafe's business day)

- New migration `0010_stock_movement_business_date`
  (`derby/core/db/migrations.py`): adds `stock_movements.business_date`,
  backfills it using the exact same `business_date()` +
  `business_close_time` rule `orders_service.py`/`expenses_service.py`
  already use (never a second, invented rule), and adds
  `idx_stock_movements_business_date`. The backfill loop only touches
  rows where `business_date IS NULL`, so it is idempotent even if
  called more than once; `run_pending_migrations`'s own version-gate
  already guarantees a migration function body runs exactly once per
  database, same as every other migration — this is exactly the
  guarantee migration 0011 above had to work around for 0009.
- `derby/core/db/stock_movements_repo.py`: `create_movement` now
  requires `business_date` from its caller (repos stay pure data
  access in this codebase — no settings lookups there).
  `sum_waste_cost_in_range` now filters on `business_date` instead of
  a UTC calendar-date substring of `created_at_utc`.
- `derby/features/inventory/stock_service.py`: a new
  `_current_business_date(conn)` helper (same small snippet
  `orders_service`/`expenses_service` each already carry, not a new
  shared abstraction) computes the business date once per call and
  passes it to every `create_movement` call site (purchase, sale
  deduction, return/reversal, waste, stocktake adjustment).
- No change was needed in `report_service.py`, `closing_text.py`, or
  the WhatsApp message builder: they already all read
  `report_service.build_report(...).waste_cost_piasters`, which itself
  calls `stock_movements_repo.sum_waste_cost_in_range` — fixing that
  one function fixes all three call sites at once, and they are
  guaranteed to show the same number because they share the same call.
- Tests (`tests/test_migration_0010_stock_business_date.py`,
  `tests/test_stock_service.py`): waste at 00:30/01:45 before a 03:00
  close lands on the previous business day, waste at 03:01 lands on
  the new day, the Cairo DST transition doesn't crash the backfill,
  the migration is idempotent across a second app launch, and the
  report + daily close text agree on the same waste figure.

## What changed (Task 2 — one-time cache clear, 1.0.0 → 1.1.0 only)

**Version bump**: `derby/__init__.py`'s `__version__` is this project's
single source of truth (enforced by `tests/test_policy.py`'s
version-matches-pyproject check) — bumped `1.0.0` → `1.1.0`, and with
it `pyproject.toml`'s mirror (same test enforces they match).
Regenerated the two files that are *generated from* that version
rather than hand-maintained: `installer/version.iss` (via
`tools/write_installer_version.py`) and `release/version.json` (via
`tools/write_version_json.py` — written with a placeholder sha256 of
zeros since no `Derby-Setup-1.1.0.exe` exists yet; `tests/test_version_json.py`
only checks the version matches and the URL host is allowed, not the
hash, so this is correct for now and gets a real hash when
`tools/make_release.py` actually builds the installer). `release/public/version.json`
is a separate, gitignored, publish-time-only artifact — left alone.

**Implementation**: the real logic lives in Python now, not in
`run.bat` — new module `derby/core/utils/startup_cache.py`, called from
`derby.app.main()` right after the crash-log hook is installed, before
any window is created. This covers BOTH launch paths the task asked
about (`run.bat`'s `python -m derby`, and the frozen installed `.exe`)
with one implementation, since both ultimately run the same
`derby.app.main()` — a pure-batch-only version could only ever have
covered the dev `run.bat` path.
- `TARGET_VERSION = "1.1.0"` is a hardcoded constant, deliberately
  separate from `derby.__version__` even though they're equal right
  now: it fixes this clear to exactly the 1.0.0→1.1.0 transition. A
  future 1.2.0 release ships this same file unchanged, but the check
  `current_version != TARGET_VERSION` is then true, so nothing fires —
  even in the (should-never-happen) case the marker was somehow lost.
- Marker file `.cache_cleared_for` (its content: the version it was
  handled for) lives "next to the app" via `resource_path.project_root()`
  — the same helper the project already uses to find bundled assets for
  both the source-run and frozen-build cases, so I didn't invent a
  second way to find that location.
- `run.bat` is back to a one-line launcher (see file) with a comment
  pointing at where the real logic now lives and how to force one more
  clear (delete the marker) for testing.
- `.gitignore` updated: `.cache_cleared_v1` (the first draft of this,
  from before the version-gating requirement existed) replaced with
  `.cache_cleared_for`.
- No installer file-exclusion list exists in `installer/derby.iss` to
  add the marker to — it's created at runtime after install, never
  part of what the installer packages, so there's nothing to exclude
  it from.

## Caches found, and what gets cleared

- `__pycache__/` folders and `*.pyc` files anywhere under the project
  root except `.venv/`, `.git/`, `build/`, `dist/` — cleared once.
  `build/`/`dist/` (PyInstaller output) are deliberately excluded: they
  are never read by either launch path at runtime, so clearing them
  would not change anything the cafe owner sees, only force an
  unnecessary rebuild.
- `.pytest_cache/`, `.ruff_cache/` at the project root — cleared once
  (dev-tool caches; asked for explicitly, free to regenerate).
- **No on-disk application-level cache exists.** `derby/features/menu/images.py`
  and `derby/features/expenses/receipts.py`'s thumbnail caches are
  plain in-memory Python dicts that die with the process on every
  launch — nothing stale could persist there between launches, before
  or after Phase 9. No QSS/Qt disk cache, no `QNetworkDiskCache` (no
  networking at all, per `CLAUDE.md`), and no cache subfolder under
  `derby/core/utils/paths.py`'s app-data directory — only `derby.db`,
  `images/`, `receipts/`, all real user data, never touched.

## Decisions I made

1. **Moved the whole mechanism from batch to Python** between this
   report's first draft and this one, once the task clarified it must
   also cover the installed `.exe` and must be version-gated to exactly
   one transition — a `run.bat`-only implementation structurally cannot
   reach the frozen build, and reading `derby.__version__` from inside
   `cmd.exe` without a second, hand-maintained copy of the version
   isn't practical, so Python reading its own single source of truth
   directly was the correct fix, not a nice-to-have.
2. **`TARGET_VERSION` hardcoded rather than "clear whenever no marker
   exists."** The task explicitly asked for exactly-one-transition
   semantics with a safety net against the marker ever failing to
   write; a version-independent "no marker → clear" rule wouldn't give
   that self-expiring guarantee for 1.2.0 and beyond.
3. **Regenerated `release/version.json` and `installer/version.iss`.**
   I had initially judged these release-time-only and left them stale,
   but `tests/test_version_json.py` turned out to already enforce that
   `release/version.json`'s version matches `derby.__version__` — so
   this was not optional once the version bumped; both are small,
   script-generated files with no release/build dependency to worry
   about (the version.json placeholder sha256 is explicitly documented
   by its own generator as a placeholder, not something to publish).
4. **Cleared `.pytest_cache`/`.ruff_cache` even though neither launch
   path reads them** — asked for explicitly, free to regenerate.
5. **Defense-in-depth tile wrapping** in `daily_stats_screen.py` goes
   beyond the literal ask (which was to fix one crash) because the task
   explicitly asked for it as a general rule ("every dashboard tile...
   shows '—' ... rather than taking down the screen") — applied to the
   two newest, least-proven lookups (drawer, low-stock), not to the
   long-stable report-based tiles above them, which share the same
   `report_service.build_report()` call everything else already
   depends on.

## Test results

- Full suite: **924 passed, 1 skipped**, 0 failed (the one transient
  failure during this run, `test_version_json.py` catching the version
  bump before `release/version.json` was regenerated, is fixed per the
  decision above and is not a real failure in the delivered state).
- `ruff check .`: all checks passed.
- `requirements.txt`: **unchanged** (verified via `git diff --stat`).
- `python -m derby --selftest` (offscreen): all scenarios pass,
  including `main_window_builds_for_owner_and_cashier`, which already
  drives the exact MainWindow → `_build_screens()` → `DailyStatsScreen`
  path that crashed.
- The real `derby.db` was read (via a copy, including its WAL/SHM
  sidecars) to confirm the crash and verify the fix, and was never
  itself written to; a stray pre-migration backup the verification run
  created in the real `Documents\Derby\Backups` folder was deleted
  afterward.

## Not verified / risks

- **Not run on real Windows 7.** Nothing added uses anything beyond
  stdlib `shutil`/`pathlib`, PySide2 QtWidgets/QtCore, and plain
  `cmd.exe` syntax that has worked since Windows XP — no specific
  reason to expect a problem there, but unverified.
- **`for /r`-style directory walks were replaced**, so the earlier
  report's Windows-7-cmd-walk risk no longer applies — the real
  implementation is now Python's `Path.rglob()`, called once at
  startup, gated so it only ever actually walks the tree on the single
  qualifying launch.
- The waste-cost business-day fix changes a number that was already
  slightly wrong (UTC-dated instead of business-day-dated) — if you've
  compared a waste-cost figure near a business-day boundary to an
  earlier screenshot, it may now differ by one or two entries. This is
  the fix working as intended, not a regression.
- The login crash existed on the real dev database between whenever
  migration 0009 was first run there and this fix — if any cash sale,
  expense, purchase, or drawer action was attempted in that window, it
  would have failed the same way (and nothing would have been written,
  per the root-cause analysis above), so there should be no corrupted
  or partial data from it, but this reasoning is not a substitute for
  you checking your real numbers (see manual check 4 below).

## Manual checks

1. **Log in with no drawer opened**: as both owner and cashier, confirm
   login succeeds with no crash dialog, and الرئيسية shows "افتح الدرج"
   on the drawer tile instead of a number or an error.
2. **Waste at 00:30**: on المخزون, record a waste entry right after
   midnight (if your close time is e.g. 03:00, it should land on
   *yesterday's* business day in تقارير, not today's).
3. **Run `run.bat` twice**: the first run after this update should
   print one short line about clearing the cache (and `.cache_cleared_for`
   should now exist next to `run.bat`, containing `1.1.0`); the second
   run, and every one after, should print nothing extra. A later real
   version bump (e.g. to 1.2.0) must also print nothing, even though
   its own code won't literally exist until then.
4. **Data intact**: open الخزنة, المخزون, والتقارير and confirm your
   real sales/expenses/stock numbers are exactly what you expect from
   before this update.
