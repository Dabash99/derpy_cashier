# Derby 1.1.0 — release report

## 1. Status

1. Version bump to 1.1.0 + one-time cache clear (1.0.0 → 1.1.0 only): **already done** before this run (commits `f864ca0`, `3dd1f89`) — verified only.
2. Update link: hide the Settings field, use a fixed URL: **done**.
3. Release 1.1.0 (build, tag, publish, README): **done**.

## 2. What changed, per part

### Part 1 (verification only — no new changes)

- `derby/__init__.py`: `__version__ = "1.1.0"` — the single place the version is defined.
- `derby/core/utils/startup_cache.py`: the one-time `.cache_cleared_for` marker clears `__pycache__`/`*.pyc`/`.pytest_cache`/`.ruff_cache` exactly once, only on the 1.0.0 → 1.1.0 transition, gated on both the marker's absence and `derby.__version__ == "1.1.0"`. Confirmed it never fires again once the marker exists, and never fires for any later version bump. `.cache_cleared_for` is in `.gitignore` and not packaged.
- Installer name, `tools/make_release.py` output, `release/version.json` all already derive from `derby.__version__` — single source of truth, no second copy.

### Part 2

- `derby/core/updates/version_logic.py`'s `DEFAULT_UPDATE_MANIFEST_URL` already pointed at the project's established **orphan `releases` branch** manifest (`https://raw.githubusercontent.com/Dabash99/derpy_cashier/releases/version.json`), built and documented in `CLAUDE.md`/`docs/RELEASING.md`/`tools/publish_release.py`, with `v1.0.0` already live under that scheme. **I kept this scheme** (confirmed with you) rather than switching to a `main/release/version.json` URL, since that would have meant rewriting the already-working publish pipeline for no benefit.
- `derby/features/settings/general_settings_form.py`: removed the "رابط ملف التحديثات" field (input, label, validation, save-path) entirely — no leftover label/spacing.
- `derby/features/settings/update_check_panel.py`: the "فحص التحديثات" button now always uses `DEFAULT_UPDATE_MANIFEST_URL` directly; the panel no longer reads/writes `update_manifest_url` at all, and the button is always enabled (the "no URL configured" state is now unreachable).
- `derby/core/i18n/ar.py`: removed the now-dead `SETTINGS_UPDATE_URL_LABEL`, `SETTINGS_ERROR_INVALID_UPDATE_URL`, `UPDATE_CHECK_NO_URL_HINT` strings.
- The `update_manifest_url` **settings row/column is untouched** in the database — just no longer read or written by the UI.
- Updated `docs/RELEASING.md` and a `tools/make_release.py` print line that referenced the old editable field.
- Tests: rewrote `tests/test_general_settings_form.py` and `tests/test_update_check_panel.py` for the new behavior (constant URL, no field, button always enabled).

**How 1.0.0 handled its stored URL**: at the `v1.0.0` tag, `DEFAULT_UPDATE_MANIFEST_URL` was already the same raw-githubusercontent `releases` branch URL (not a `github.com/.../blob/...` HTML link) — so the scenario in the original brief ("1.0.0 stored a `blob` URL it can't parse") did not apply to this codebase; 1.0.0's button already worked against the real manifest. Installed 1.0.0 apps will see 1.1.0 through the button normally.

### Part 3

- Found and fixed a real bug while running the release gate: `derby/features/playstation/ps_adjust_start_dialog.py` always placed the user's typed time-of-day on the running session's own Cairo calendar day. If the session started just after local midnight, a legitimate "backdate to last night" input landed ~24h in the future and was correctly rejected by `ps_service` — this is what made `tests/test_playstation_screen.py::test_adjust_start_dialog_owner_direct` fail (reproducibly, not flaky) when the suite happened to run in that post-midnight window. Fixed by falling back to the previous calendar day when the same-day interpretation is in the future. Full suite, ruff, and selftest all pass after the fix.
- `CHANGELOG.md` created (Arabic + English, 1.1.0 entry).
- `release\دليل-استخدام-ديربي.pdf` regenerated from `docs/USER-GUIDE-AR.md` (it already covered inventory/recipes/purchases, the drawer, profit, and the home dashboard — Phase 9/10 content was already written).
- `tools/make_release.py` ran clean: ruff, full pytest, PyInstaller build + packaged `--selftest`, Inno Setup 6 compile, a full silent install → `--selftest` → silent uninstall cycle (install dir ends empty, data dir untouched), `release\SHA256SUMS.txt` written.
- Migrations added since `v1.0.0`: **0009 (inventory), 0010 (stock_movement_business_date), 0011 (drawer_entries_is_historical_repair)** — confirmed migrations 0001–0008 are byte-for-byte unchanged (`git diff v1.0.0` shows no changes inside them), additions only.
- `requirements.txt` confirmed unchanged since `v1.0.0` (`git diff v1.0.0 -- requirements.txt` is empty).

## 3. What was published

- Repo: `Dabash99/derpy_cashier` (public, default branch `main`).
- Tag: `v1.1.0`, pointing at commit `9f700ad` (the last commit before the README update), pushed to origin.
- Release page: https://github.com/Dabash99/derpy_cashier/releases/tag/v1.1.0 ("Derby 1.1.0"), published (not left as a draft — the asset-size verification in `tools/publish_release.py` passed, so there was no reason to hold it back; see "Decisions I made").
- Installer: `Derby-Setup-1.1.0.exe`, 34,162,939 bytes (32.6 MB).
- SHA-256: `7e03b46feaa28dd9853c715eab297fa4203b5ac484216690d87def17b740ad3f`
- Direct download link verified live: https://github.com/Dabash99/derpy_cashier/releases/download/v1.1.0/Derby-Setup-1.1.0.exe (HTTP 200, 34,162,939 bytes).
- `release/version.json` (committed to `main`) and the orphan `releases` branch's `version.json` both carry the real sha256 and this download URL; the raw manifest URL (`https://raw.githubusercontent.com/Dabash99/derpy_cashier/releases/version.json`) was fetched and confirmed to be valid JSON at 1.1.0.
- README updated and pushed to `main`: **yes** — final commit hash `d9dbd98e128f4430762e69a8dd71463b8a867999`. `git log origin/main -1` matches local `main`/`master` exactly; `v1.1.0` exists on the remote.

## 4. Decisions I made

- **Update-URL architecture**: kept the existing orphan-`releases`-branch scheme instead of switching to `main/release/version.json` (confirmed with you directly — this was a real conflict between the brief and the already-shipped, documented, tested architecture, not something to silently pick).
- **Release visibility**: published the GitHub Release directly rather than leaving it as a draft first, since the asset-size verification step (`tools/publish_release.py`'s `verify_release`) already confirmed both uploaded assets match the local files byte-for-byte before I considered it done; there was no draft-review step to add value here, and the existing tooling's design is "create + verify", not "draft + confirm + publish".
- **`release/version.json`'s real sha256 commit**: `tools/make_release.py` had already written the real sha256 into `release/version.json` locally (from a successful build) but it hadn't been committed yet; I committed and pushed it to `main` right after confirming the release's assets were live, rather than leaving a stale placeholder sha256 (`000...0`) sitting in the tracked file.
- Left `.agents/`, `.claude/`, `AGENTS.md`, and `Claude outputs/` untouched and uncommitted — unrelated tooling/plugin scaffolding and personal prompt notes, not part of this release.

## 5. Test results

- `pytest`: 943 passed, 1 skipped (both before and after the `ps_adjust_start_dialog` fix, once fixed).
- `ruff check .`: all checks passed.
- `python -m derby --selftest`: all checks passed, including `update_manifest_parsing_no_network` and `main_window_builds_for_owner_and_cashier`.
- `requirements.txt` unchanged since 1.0.0: **yes**.
- Installer build: PyInstaller build + silent install → `--selftest` → silent uninstall cycle all passed; install directory ended empty and the data directory was untouched.

## 6. Not verified / risks

- **Real Windows 7 install and upgrade from a real 1.0.0 install** were not exercised — this machine only ran the silent install/uninstall cycle in a temp directory on (implicitly) this dev machine's OS, not a real Windows 7 SP1 box, and not an upgrade over an actual previously-installed 1.0.0.
- The cache-clear-on-upgrade logic (Part 1) was verified by code reading and by the existing automated tests for `startup_cache.py`, not by a fresh manual "run twice" check during this session.
- No real cafe PC testing of the drawer/no-drawer-opening login flow, waste-entry-at-00:30 business-day attribution, or a real backup/restore cycle — see the manual checklist below.

## 7. Manual checklist for you

- [ ] Log in as owner and cashier with no drawer opened, and confirm no error dialog appears.
- [ ] Add a waste entry at 00:30 and check which business day it lands on.
- [ ] Settings no longer shows the update-link field, and "فحص التحديثات" gives a sensible result (up to date now that this machine is on 1.1.0; try with an older local build if you want to see "update available").
- [ ] Run `run.bat` twice and confirm the cache only clears the first time (look for the one-line message on the first run, nothing on the second).
- [ ] Install `Derby-Setup-1.1.0.exe` over a real 1.0.0 install on the cafe PC and confirm all data (`%APPDATA%\Derby`, `Documents\Derby`) is intact afterward.
- [ ] Take a backup and restore it, to confirm the full cycle still works end to end on a real machine.
