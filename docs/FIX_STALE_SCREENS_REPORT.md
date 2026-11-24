# Fix: invoices/sessions not showing up until the app is restarted

## Root cause (proved, not guessed)

Read `derby/features/shell/main_window.py` (`_build_screens`/`_on_navigate`,
before this fix) together with every screen module under
`derby/features/*/*_screen.py`:

- `MainWindow._build_screens()` constructs every screen **once** and adds
  it to a single `QStackedWidget`. It is never rebuilt — only shown/hidden
  as the sidebar is clicked.
- Every screen's constructor calls `self.reload()` exactly once, right
  after building its UI (e.g. `sales_log_screen.py:58`,
  `reports_screen.py:87`, `drawer_screen.py:59`, `inventory_screen.py:50`,
  `customers_screen.py:38`, `audit_log_screen.py:50`,
  `expenses_screen.py:55`, `supplies_screen.py:52`).
- `MainWindow._on_navigate()` (old code) called `.reload()` again for
  exactly two screens — `"tables"` and `"playstation"` — on every
  navigation. Every other screen (سجل المبيعات، التقارير، الخزنة،
  المخزون، العملاء، سجل المراجعة، الورديات والموظفون، المصروفات،
  التوريدات) had **no further reload path at all**: once built, its table/
  labels stayed frozen at whatever the database looked like the first time
  that screen was shown, for the rest of the process's life. The only way
  to see new data on those screens was to close and reopen the app, which
  rebuilds `MainWindow` and every screen inside it from scratch.
- الرئيسية (`daily_stats_screen.py`) and `open_orders_panel.py` were
  **not** affected — both already override `showEvent` to reload every
  time they become visible (`daily_stats_screen.py:301-304`), plus a
  1-second timer while shown.
- الكاشير itself was not affected either: every cart mutation
  (`add_item`/`pay`/...) calls `self._cart_panel.reload()` directly in the
  same handler, in the same (visible) screen.

Transaction discipline, connection handling, and caching were all **ruled
out** as contributing causes, by direct code reading:

- The whole app shares **one** `sqlite3.Connection` (`derby/app.py:265`,
  passed into every screen/service) — there is no second, stale-snapshot
  connection for the UI to read from (the only other connections in the
  codebase are `backup_service.py`'s one-shot backup/restore connections
  and `closing_worker.py`'s background-thread connection, both opened,
  used, and closed in one call — never held open or read from the UI).
- Every write path in `orders_service.py`, `ps_service.py`,
  `stock_service.py`, `drawer_service.py`, `expenses_service.py`,
  `customer_service.py`, and `shift_service.py` already followed the
  documented discipline: every repo call passes `commit=False` and the
  function finishes with exactly one `conn.commit()` (directly, or via
  `audit_repo.log`/`audit_service.log`, which commit as a side effect),
  wrapped in `try/except: conn.rollback(); raise`. No function left a
  write uncommitted or exited while mid-transaction. `tests/
  test_live_refresh.py::test_pay_void_cancel_never_leave_the_connection_
  mid_transaction` pins this with `conn.in_transaction is False` checks
  after `pay`/`void`/`cancel`.
- No `lru_cache`/memoized query exists anywhere in `derby/features/reports`,
  `dashboard`, or the repo layer (grepped `lru_cache`/`functools.cache`/
  `_cache` across `derby/` — the only hits are unrelated image thumbnail
  caches in `menu/images.py`, `expenses/receipts.py`, `pos/product_card.py`,
  none of which touch invoice/order/drawer data).
- No date/status filter mismatch: `sales_log_screen.reload()` and
  `report_service.build_report()` both use `business_date`/
  `compute_business_date` consistently; the bug reproduced with same-day,
  same-business-day orders, so filtering was never the cause.
- No refresh timer was paused incorrectly — the only such timers
  (`daily_stats_screen`, `playstation_screen`'s 1s elapsed-time tick) were
  already running and unaffected.

So the cause is **#3 from the investigation list**: screens built once
and never refreshed, apart from two hand-picked exceptions.

## What changed

1. **`derby/core/events.py`** (new) — a tiny central "data changed" bus:
   `events.bus.notify()` (called by services after a real commit) and
   `events.bus.changed` (a Qt signal screens subscribe to). A 200ms
   debounce timer collapses a burst of `notify()` calls from one user
   action (e.g. `pay()` touches orders, stock, and the drawer) into a
   single `changed` emission, so a screen's `reload()` runs once per
   action, not three times.

2. **`derby/core/utils/screen_refresh.py`** (new) —
   `RefreshOnChangeMixin`: a screen that mixes this in subscribes to the
   bus and reloads immediately if it is the one currently on screen, or
   otherwise just remembers it is stale (`_dirty`) and reloads the moment
   it is shown again (`showEvent`, fired for free by `QStackedWidget`).
   A refresh failure is caught and logged through the existing
   `derby.core.utils.error_log`, never raised into Qt's event loop.

3. Mixed into every screen that previously had no live-refresh path:
   `SalesLogScreen`, `ReportsScreen`, `DrawerScreen`, `InventoryScreen`,
   `CustomersScreen`, `AuditLogScreen`, `ShiftsEmployeesScreen`,
   `ExpensesScreen`, `SuppliesScreen` — plus `TablesScreen` and
   `PlaystationScreen` (converted from the old main_window special-case to
   the same mechanism as everything else). `daily_stats_screen.py` and
   `open_orders_panel.py` were left as they were (already correct).
   `ShiftsEmployeesScreen.reload()` was also corrected to reload whichever
   tab is actually current (it only ever reloaded الوردية, regardless of
   which tab was visible — a pre-existing bug this fix would otherwise
   have papered over for every tab but the first).

4. **`MainWindow._on_navigate()`** (`derby/features/shell/main_window.py`)
   — the old two-screen special case was generalized to call `.reload()`
   on *every* screen that has one, on every navigation to it, as a cheap
   safety net on top of the bus (a refresh failure here is also caught
   and logged, never crashes the UI).

5. **`events.bus.notify()`** calls added to the services layer, right
   after each function's own commit succeeds (never before, never inside
   the `try` before the commit is known to have happened):
   `orders_service.py` (add_item, change_qty, remove_item, apply_discount,
   remove_discount, cancel, pay, void, move_order, remove_ps_item,
   auto_cancel_empty_open_orders), `ps_service.py` (start_session,
   switch_mode, stop_session), `stock_service.py` (record_purchase,
   mark_purchase_paid, record_waste, record_stocktake),
   `drawer_service.py` (open_drawer, record_deposit, record_withdrawal,
   record_cash_refund, record_count), `expenses_service.py`
   (create_expense, void_expense, replace_expense), `customer_service.py`
   (credit_sale, record_payment), `shift_service.py` (open_shift,
   close_shift — `handover_shift` composes both, so it is covered too).

No database schema change, no new dependency, no new network call. The
app's existing behavior, numbers, and permissions are unchanged — only
freshness.

## Decisions made

- Chose a navigate-time safety net **and** a bus-driven dirty/showEvent
  mechanism (as the task asked), rather than either alone: the bus alone
  would miss anything a future code path forgets to call `bus.notify()`
  after; the navigate-time reload alone would not refresh a screen that
  stays visible without navigating away and back (not currently possible
  in this single-pane UI, but the bus makes the app correct even if that
  changes later, e.g. a background PS-session tick).
- Did **not** wire `bus.notify()` into every single mutating function in
  every service (e.g. `customer_service.create_customer`,
  `supplies_service.add_supply`, expense-category/recurring-template
  management). Those mutate data that only their own screen shows, and
  that screen already calls `self.reload()` directly, synchronously, in
  its own button/dialog handler — the exact "same-screen action" case
  that was never broken. Wiring them in anyway would be free (the bus
  debounces), but it is not what reproduces the reported bug, so it was
  left out to keep the service-layer diff centered on the actual fix per
  "no features beyond what the task requires."
- Left `daily_stats_screen.py`/`open_orders_panel.py` untouched —
  converting them to the new mixin would conflict with their existing
  `showEvent` override and timer, for a screen that was never part of the
  bug.

## Test results

- `pytest`: **1085 passed, 1 skipped** (was 1077 passed, 1 skipped before
  `tests/test_live_refresh.py` was added — no existing test changed
  behavior or broke).
- `ruff check .`: **all checks passed**.
- `python -m derby --selftest`: **"passed": true**, 0 failed checks
  (including the existing `main_window_builds_for_owner_and_cashier`
  check).
- `requirements.txt`/`pyproject.toml` dependencies: **unchanged**.
- New file `tests/test_live_refresh.py` adds 8 tests, all passing against
  the fix:
  - `test_bus_debounces_a_burst_of_notifications_into_one_signal` —
    proves the 200ms debounce collapses a burst to one emission.
  - `test_hidden_screen_does_not_reload_immediately_but_reloads_on_next_show`
    — a hidden `SalesLogScreen` does not requery while hidden, and does
    the instant it is shown.
  - `test_visible_screen_reloads_on_its_own_without_navigation` — a
    visible `SalesLogScreen` picks up a payment with no navigation at
    all.
  - `test_drawer_screen_reflects_a_cash_sale_without_manual_reload` —
    الخزنة.
  - `test_customers_screen_reflects_a_credit_sale_balance_without_manual_reload`
    — العملاء / آجل.
  - `test_reports_screen_totals_update_after_a_sale_while_visible` —
    التقارير.
  - `test_pay_void_cancel_never_leave_the_connection_mid_transaction` —
    transaction-discipline guard (`conn.in_transaction is False` after
    every call).
  - `test_a_second_connection_sees_a_payment_immediately` — proves `pay()`
    actually commits to the file, not just to an in-process cache.
  - Every test here imports `derby.core.events`/
    `derby.core.utils.screen_refresh`, which did not exist before this
    change — so by construction they would fail (`ImportError`) against
    the pre-fix code, in addition to the root-cause code reading above.

## Not verified

- Real Windows 7 hardware/timing. The 200ms debounce and the per-screen
  `reload()` queries were chosen to stay cheap (same queries the screens
  already ran at construction time — nothing new or heavier is queried),
  but actual responsiveness on a weak Windows 7 PC was not measured here.

## Manual checklist

1. افتح طلب لترابيزة وتأكد إن الترابيزة في شاشة **الترابيزات** وبيانات
   **الرئيسية** (الطلبات المفتوحة) تتحدث فورًا بدون أي تنقل بين الشاشات.
2. ادفع الفاتورة وتأكد إن **سجل المبيعات**، **الرئيسية**، و**الخزنة**
   تتحدث فورًا (بدون الضغط على أي زر تحديث) — جرّب كاش وInstaPay.
3. أبطل الفاتورة (كمالك) وتأكد إن كل الشاشات السابقة ترجع لحالتها الأصلية
   فورًا.
4. ابدأ وأوقف جلسة بلايستيشن وتأكد إن شاشة **البلايستيشن** و**الرئيسية**
   تتحدثان فورًا.
5. كرر الخطوات 1-4 بحساب كاشير (لا مالك) وتأكد من نفس السلوك.
6. أغلق البرنامج وافتحه تاني، وتأكد إن مفيش أي بيانات ضاعت أو تغيرت —
   التحديث الجديد ما يغيّرش أي رقم أو صلاحية، فقط يجعل الشاشات تتحدث
   أسرع.
