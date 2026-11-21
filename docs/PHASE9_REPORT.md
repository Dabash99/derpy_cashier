# Phase 9 — Inventory & Profit: final report

## Status per step

- (a) Migration + models + stock_service + tests — **done** (built in the
  prior session; this run fixed the drawer historical-backfill bug and
  added the migration-idempotency test).
- (b) Stock / Purchases / Suppliers screens — **done**.
- (c) Recipes + checkout deduction/void reversal through the UI — **done**.
- (d) Dashboard (الرئيسية) home screen + new-invoice flow — **done**, with
  a simplification: see "Decisions I made".
- (e) الخزنة (cash drawer ledger + count + goods review) — **done**.
- (f) Profit report (owner only) + dashboard profit/stock cards — **done**.
- (g) Reports/export/backup/WhatsApp integration — **done**; user guide
  updated. PDF guide file under `release/` was **not** regenerated (that's
  a release step via `tools/make_release.py`, not run here).

## What changed

**New migration**: `0009_inventory` (`derby/core/db/migrations.py`) —
`stock_items`, `suppliers`, `purchases`/`purchase_lines`, `recipe_lines`,
`stock_movements`, `drawer_entries`/`drawer_counts`; `order_items.cost_at_sale_piasters`;
`ps_devices.hourly_cost_piasters`; auto-inserts a "مشتريات" expense
category; backfills existing paid-cash orders/expenses into
`drawer_entries` flagged `is_historical=1`.

**New repos** (`derby/core/db/`): `stock_items_repo.py`, `suppliers_repo.py`,
`purchases_repo.py`, `recipes_repo.py`, `stock_movements_repo.py`,
`drawer_repo.py`; `orders_repo.set_cost_at_sale`; `reports_repo.py`'s
product/PS item queries now also return `cost_piasters`.

**New feature package** `derby/features/inventory/`:
- `stock_service.py` — weighted-average purchase costing, paid/unpaid
  purchase → auto expense (no double counting), recipe-based deduction
  (product + add-ons) wired into `orders_service.pay()`, reversal wired
  into `orders_service.void()`, waste, stocktake, `recompute_current_qty`
  repair, `stock_value_piasters`.
- `drawer_service.py` — opening balance, deposit/withdrawal/refund (note
  required), physical count with optional denominations and an
  auto-filed `count_adjustment` entry. The live expected-cash balance
  only ever sums from the most recent **live** `opening` entry — a
  backfilled historical row never counts toward it.
- `inventory_screen.py` / `inventory_dialogs.py` — stock/purchases/suppliers
  tabs (owner only).
- `drawer_screen.py` / `drawer_dialogs.py` — ledger, count, goods review
  (owner-only section inside a screen both roles can open).
- `recipe_editor_dialog.py` — shared recipe editor, opened from the
  product dialog and the add-on panel.
- `exceptions.py`.

**Modified**:
- `derby/features/pos/orders_service.py` — `pay()` now calls
  `stock_service.apply_sale_deductions` and (for cash) files a
  `drawer_entries` sale_cash row; `void()` calls
  `stock_service.reverse_sale_deductions`.
- `derby/features/expenses/expenses_service.py` — create/void/replace
  now feed/reverse `drawer_entries`.
- `derby/features/auth/permissions.py` — `manage_inventory`, `view_drawer`,
  `manage_drawer`, `view_goods_review`, `view_profit_report`, `view_cost_data`.
- `derby/features/menu/product_dialog.py`, `addon_groups_panel.py` — a
  "الوصفة" button opens `RecipeEditorDialog`.
- `derby/features/dashboard/daily_stats_screen.py` — "فاتورة بيع جديدة"
  button + type-chooser dialog, cash-in-drawer/low-stock tiles (both
  roles), gross-profit tile (owner).
- `derby/features/shell/sidebar.py` / `main_window.py` — إحصائيات اليوم
  moved to the first/home position (visible to every role), new المخزون
  (owner) and الخزنة (both roles) sections wired in.
- `derby/features/reports/report_service.py` — `ReportResult` gains
  `cogs_piasters`, `gross_profit_piasters`, `operating_expenses_piasters`,
  `net_profit_piasters`, `food_drinks_revenue_piasters`,
  `top_items_by_profit`, `low_margin_items`, `waste_cost_piasters`.
- `derby/features/reports/reports_screen.py` — a new الأرباح section.
- `derby/features/reports/export_service.py` — profit figures in the
  existing report export, plus new `stock_sections`/`purchases_sections`/
  `drawer_sections` and their CSV/Excel convenience functions, wired into
  `InventoryScreen`/`DrawerScreen` via the existing `ExportPanel`.
- `derby/features/closing/closing_text.py` / `closing_service.py` — gross/
  net profit, waste cost, a low-stock warning line, and the day's drawer-
  count result (if one was taken that business day) in the daily close
  text and WhatsApp message.
- `docs/USER-GUIDE-AR.md`, `tools/make_user_guide_pdf.py` — new sections.

**Tests**: `test_stock_service.py`, `test_drawer_service.py`,
`test_inventory_permissions.py`, `test_inventory_screen.py`,
`test_drawer_screen.py`, `test_recipe_editor_dialog.py`,
`test_pos_recipe_ui_flow.py`, `test_new_invoice_flow.py`,
`test_profit_report.py`, `test_phase9_export.py`,
`test_restore_then_migrate_phase9.py`, plus additions to
`test_migrations.py`, `test_closing_text.py`, and two pre-existing tests
fixed for the new 7th expense category.

## Decisions I made

1. **Dashboard scope** (confirmed with you mid-session): extended the
   existing `daily_stats_screen.py`/`السايدبار` entry into الرئيسية,
   rather than building a second, separate home screen.
2. **New-invoice flow for ترابيزة/بلايستيشن**: rather than rebuilding
   table/device picking inside the dashboard, the chooser just navigates
   to the existing Tables/PlayStation screens, which already show live
   status and attach to an open bill or start one — this is a literal
   reuse of that flow, not a re-implementation, per the spec's "reuse
   existing... logic; do not duplicate it".
3. **Drawer historical backfill**: added `drawer_entries.is_historical`
   (not in my first pass) after review — the live expected-cash balance
   must start from zero/the most recent **live** `opening` entry, never
   from a lifetime backfill of old cash sales.
4. **Recipe button only for an already-saved product/add-on**: a brand
   new, unsaved product has no id for `recipe_lines` to point at, so the
   "الوصفة" button is disabled until the owner saves once and reopens —
   mirrors how image upload already behaves elsewhere in this dialog.
5. **Low-margin threshold**: no number was specified in the spec; I used
   <10% margin (or negative) as "low margin" — a sensible cafe default,
   easy to tune later if you want a different cutoff.
6. **Waste-cost date range**: `stock_movements` has no `business_date`
   column (unlike orders/expenses), so waste cost in a report/close is
   summed over the plain UTC calendar date range, not the cafe's
   late-close business day. Close enough for a report figure; flagged
   below as a caveat.
7. **Drawer operate permission**: both owner and cashier can open/deposit/
   withdraw/count the drawer (it's the shared till a cashier works from
   day to day) — only the goods-review figures (stock value, unpaid
   supplier balances) are owner-only.
8. **Expense void drawer reversal**: voiding or replacing an expense now
   also files a reversing `drawer_entries` row (not explicitly spec'd,
   but required for "the drawer balance must always be recomputable from
   the ledger" to stay true after a correction).
9. **Commit granularity**: committed in 4 logical chunks (schema+service,
   screens, dashboard, reports/export/closing) rather than literally one
   commit per lettered step — some work (e.g. drawer_service) spans two
   steps and splitting it further would have meant half-working
   intermediate commits.

## Test results

- Full suite: **903 passed, 1 skipped**, 0 failed.
- `ruff check .`: all checks passed.
- `requirements.txt`: **unchanged** (verified via `git diff --stat`).
- `python -m derby --selftest` (offscreen): all scenarios pass, including
  `main_window_builds_for_owner_and_cashier`.

## Not verified / risks

- **Not run on real Windows 7 hardware** — this session is Windows 11.
  Nothing Phase 9 added uses anything beyond PySide2 QtWidgets/QtCore/
  QtGui and stdlib `json`/`sqlite3`, so I have no specific reason to
  expect a Windows 7 regression, but it hasn't been manually checked
  there per `docs/WIN7-CHECKLIST.md`.
- **Performance with 1+ year of data**: I added indexes on
  `stock_movements(stock_item_id, created_at_utc)` and
  `(ref_type, ref_id)`, on `drawer_entries`/`drawer_counts(created_at_utc)`,
  and on `purchases(is_paid)`/`purchase_lines(purchase_id)` — but I did
  not load-test the profit report (`report_service.build_report`) against
  a year of order_items; it reuses the existing paid-orders/product-rows
  queries (already indexed from earlier phases) plus one new aggregate
  query for waste cost, so it should scale similarly to the existing
  daily/monthly report, but this is inference, not a measured benchmark.
- **Waste-cost date boundary** (see decision 6 above): uses UTC calendar
  dates, not the cafe's business-day boundary. For a cafe that closes
  well after midnight, waste recorded between midnight and close time
  could land in the "wrong" day's report by a few hours. Low-impact
  (waste entries are occasional, not every transaction) but worth knowing.
  A **separate deliberate choice** by default: the daily close computes
  this as the Phase 9 commit describes — the WhatsApp/close text pulls it
  from `report_service.build_report`'s own waste figure, so both places
  are consistent with each other, just not perfectly aligned to the
  business-day boundary.
- **Existing behavior touched**: `orders_service.pay()` and `void()` now
  do additional DB work (stock deduction/reversal, a drawer entry) inside
  the same transaction as before — if this ever raises, the whole
  payment/void rolls back (same `try/except: conn.rollback(); raise`
  pattern already used everywhere else), so a stock-related bug would
  show up as "payment failed" rather than silently losing stock data.
  I did not find a bug in testing, but this is the main place a Phase 9
  regression could visibly break an everyday cashier action, so it's
  worth extra attention on first real use.
- **Low-margin threshold (10%)** and the **new-invoice reuse decision**
  (above) are both judgment calls, not written requirements — easy to
  change if they don't match how you actually want it to behave.
- **PDF guide file under `release/`** was not regenerated — run
  `tools/make_user_guide_pdf.py` (or `make_release.py`) before cutting an
  actual release if you want the shipped PDF to include the new sections.

## Manual test checklist

1. **New takeaway invoice**: log in, on الرئيسية press "فاتورة بيع
   جديدة" → تيك أواي. Confirm it opens the Cashier screen on a fresh
   takeaway draft.
2. **New table invoice**: "فاتورة بيع جديدة" → ترابيزة → pick a free
   table. Confirm it opens the Cashier screen for that table. Add an
   item, go back to الرئيسية, repeat the same table pick again — confirm
   it re-opens the SAME order (doesn't create a second one).
3. **PlayStation device invoice**: "فاتورة بيع جديدة" → بلايستيشن → start
   a session on a free device as usual.
4. **Add a stock item + a purchase**: المخزون → "+ عنصر جديد" (e.g.
   دقيق, جرام, حد أدنى 500) → شراء → enter qty/cost, mark "تم الدفع",
   save. Confirm the item's quantity/avg cost update, and an expense
   appears under "مشتريات".
5. **Recipe + deduction**: from المنيو, edit a product → "الوصفة" → add
   the stock item with a qty per unit → save. Sell that product in a
   normal cashier flow, pay. Back in المخزون, confirm the quantity
   dropped by the expected amount.
6. **Void reversal**: void that same paid order (سجل المبيعات). Confirm
   the stock quantity in المخزون goes back up to what it was before the
   sale.
7. **Drawer count**: الخزنة → "فتح الدرج" with a starting amount → "جرد
   الدرج" → enter a counted amount different from expected → confirm the
   زيادة/عجز shown matches your math, and the ledger shows a تسوية جرد
   row afterward.
8. **Profit report**: التقارير → اليوم, scroll to الأرباح. Confirm the
   numbers look sane (gross profit ≤ net sales, net profit = gross minus
   operating expenses).
9. **Daily close**: الإعدادات → إقفال اليوم (or wait for auto-close).
   Confirm the generated text/WhatsApp message includes الربح الإجمالي/
   الصافي lines and (if you did a drawer count and have low-stock items)
   the warning lines.
10. **Backup/restore**: take a manual backup now, then from الإعدادات →
    استرجاع choose that same backup file and confirm the app restarts
    with everything intact (this also exercises the ordinary, same-
    version restore path, not just the cross-version one already covered
    by the automated test).

## Known issues / suggested next steps

- No dedicated icon assets exist yet for المخزون/الخزنة in the sidebar
  (reusing the "expenses" icon shape) — render real ones via
  `tools/render_assets.py` when convenient, same follow-up already noted
  for supplies' icon.
- The low-margin threshold (10%) and whether cashiers should be able to
  operate the drawer unsupervised are both easy to revisit if real-world
  use suggests a different default.
- Consider tightening the waste-cost date boundary to the business-day
  rule if waste near midnight ever causes a visibly wrong daily figure.
