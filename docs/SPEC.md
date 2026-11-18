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

1. **Foundation** (this phase) — project scaffold, SQLite + migrations,
   PIN auth with lockout, roles/permissions, settings screen, main window
   shell with placeholders, the manual update-check feature, and the full
   test/policy suite.
2. Menu management (items, categories, prices).
3. Cashier / POS screen (orders, line items, payment method).
4. Tables (if dine-in table tracking is needed) — TBD scope.
5. PlayStation corner (devices, sessions, billing per the rule above).
6. Expenses tracking.
7. Reports (sales, expenses, PlayStation usage, by business day).
8. Daily closing + backup (to the configured primary/secondary folders)
   + WhatsApp report send (manual, via `whatsapp_number` setting — exact
   send mechanism TBD in that phase; Phase 1 only stores the number).

Each phase builds directly on Phase 1's schema and conventions rather than
replacing them.
