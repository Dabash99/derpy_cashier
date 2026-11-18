# Derby — Approved Spec Summary

Short reference summary of the approved product spec. This is not the full
discussion history — just the decisions that shape the build.

## Context

- Cafe name: **Derby**, in Menoufia, Egypt. Has a PlayStation corner in
  addition to normal food/drink service.
- Target machines: Windows 7 SP1 64-bit and Windows 10 64-bit, same
  installer/codebase. Hardware can be weak (~4GB RAM), so the app must stay
  light (no heavy animations, no web engine, no background services beyond
  what's needed).
- Fully offline. The only network call in the whole app is a manual
  "check for updates" button; see [CLAUDE.md](../CLAUDE.md) for the exact
  rules.

## Roles and users

- Two roles: **owner** and **cashier**.
- Users: the owner, plus up to 3 cashiers (so cashier + 2 more users with
  cashier permissions) in Phase 1 — the schema does not hard-limit this,
  but that's the expected real-world count.
- Each user has their own PIN (4–6 digits). PINs must be unique across
  active users, since login identifies the user by PIN alone (no
  username/password).
- Owner: full access to everything, including Settings and user
  management. Cashier: no access to Expenses, Reports, or Settings.

## Business day

- The cafe's "business day" does not necessarily reset at midnight — it
  resets at a configurable close time (default 23:59). An order placed at
  01:30 when the close time is 03:00 belongs to the *previous* business
  day. See `derby/core/utils/business_date.py` for the exact rule and
  `derby/core/db` for where the close time is stored (`settings` table,
  key `business_close_time`).

## PlayStation pricing rules

- Each PS device has a **Single** rate and a **Multi** (multiplayer) rate,
  both hourly, in EGP.
- Billing uses **actual minutes played**, with a **minimum of 30 minutes**
  (configurable via `ps_min_minutes` setting).
- Price = hourly_rate × minutes ÷ 60, then **rounded to the nearest 5 EGP**
  (configurable via `rounding_step_egp` setting; round-half-up).
  - Example: 40 EGP/hour × 37 minutes = 24.666... EGP → rounds to 25 EGP.
- PlayStation screens/pricing/session tracking are built in a later phase
  (Phase 4-ish); Phase 1 only lays the settings groundwork.

## Payments

- Two payment methods: **cash** or **InstaPay**. The app only records
  *which* method was used per transaction — no integration, no
  reconciliation logic, no transaction fees modeled.
- No tax is calculated anywhere.
- No kitchen-display / kitchen-ticket flow.
- No receipt printer integration for now (may be added in a later phase).

## Phases

1. **Foundation** (done) — project scaffold, SQLite + migrations, PIN auth
   with lockout, roles/permissions, settings screen, main window shell
   with placeholders, the manual update-check feature, and the full
   test/policy suite.
2. **Menu** (done) — categories, products, add-ons, CSV import/export,
   product images.
3. **Cashier & tables** (this phase) — cart, add-ons, 3 tables that can be
   added/disabled, discounts with permission + audit log, payment
   cash/InstaPay, sales log.
4. PlayStation — 2 devices (more can be added), Single/Multi hourly rates,
   timed sessions, a session becomes an order line, changing Single/Multi
   stops and starts a new session on the same order, transferring the bill
   table↔device is rejected if the target is busy, timers are computed
   from a UTC `started_at` so they survive an app restart.
5. Printing — deferred; no printer integration yet.
6. Expenses, reports, profit, export to Excel/CSV/PDF.
7. Daily closing + backup (to the configured primary/secondary folders,
   including the `images` folder) + WhatsApp report send (manual, via
   `whatsapp_number` setting).
8. Delivery — PyInstaller exe for Windows 7/10, installer, real-PC tests,
   a short user guide.

Each phase builds directly on the previous phases' schema and conventions
rather than replacing them.
