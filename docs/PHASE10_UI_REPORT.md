# Phase 10 UI — home screen open orders + redesigned menu cards

## Status

- **Part A (الطلبات المفتوحة on الرئيسية):** done.
- **Part B (redesigned product cards in the cashier):** done.

## Files changed

New:
- `derby/features/dashboard/open_orders_service.py` — query/aggregation layer.
- `derby/features/dashboard/open_orders_panel.py` — the section widget + card.
- `derby/features/pos/product_card.py` — the new `ProductCard` component.
- `tools/render_phase10_previews.py` — dev-time screenshot script (not shipped).
- `tests/test_open_orders_panel.py`, `tests/test_product_card_and_grid.py`
- `docs/ui/phase10_home.png`, `docs/ui/phase10_menu_cards.png`

Modified:
- `derby/core/db/orders_repo.py` — added `list_open_orders_with_summary()` (one query, read-only, no schema change).
- `derby/core/i18n/ar.py` — removed the now-unused "الآن" block strings, added the open-orders section's strings.
- `derby/core/theme/stylesheet.py` — added `variant="chip"` (filter/category pills), `variant="openOrderCard"` (type-colored accent + stale highlight), `variant="productCard"`, `variant="pricePill"`.
- `derby/features/dashboard/daily_stats_screen.py` — swapped the plain-text "الآن" block for `OpenOrdersPanel`, kept the busy/free tables summary line, added an `order_opened` signal.
- `derby/features/shell/main_window.py` — wired that new signal the same way `TablesScreen.order_opened` already is.
- `derby/features/pos/product_grid.py` — rebuilt around `ProductCard`, pill category chips (horizontally scrollable), responsive column count, lazy image reveal on scroll.

## Decisions made

- **Stale-order threshold:** 2 hours, a module constant (`open_orders_service.STALE_ORDER_THRESHOLD_SECONDS`), not a settings-table row — the task is explicitly read-only/no-schema-change, so "configurable" became a code constant instead of a new setting.
- **Refresh cadence:** one DB query every 5s (`OpenOrdersPanel._refresh_timer`) + a separate 1s local-only timer that re-renders already-fetched elapsed times on running PlayStation cards (`tick_local()`), with both stopped in `hideEvent`. PlayStation provisional price/elapsed is read via `ps_service.current_state()` once per **active device** (not per order), the same bounded pattern `daily_stats_service.py` already used — so the "no per-card query" requirement is satisfied without a second heavy query.
- **Grid columns:** fixed 4 columns for the open-orders grid (matches every other grid in this codebase — Tables, PlayStation, the old product grid). The product grid is the one place made genuinely responsive (3–5 columns by viewport width), per the Part B spec wording; this is a deliberate asymmetry, not an oversight.
- **Takeaway drafts:** no special-casing needed — they're already `orders` rows with `status='open'` and `table_id`/`device_id` both NULL, so they fall out of the same one `list_open_orders_with_summary()` query as everything else.
- **Elapsed time format:** HH:MM:SS for every card kind (not just PlayStation), for one shared rendering path; cheap and harmless for table/takeaway cards too.
- **`daily_stats_service.py` left untouched.** Its `DailyStats.open_orders_count`/`running_sessions` fields are covered by their own existing test (`tests/test_daily_stats_service.py`) and may still be consumed elsewhere; the Home screen's new section gets its data from `open_orders_service` instead, so nothing there needed to change.
- **Placeholder image color:** a plain cream placeholder was visually indistinguishable from the page background in review (first screenshot pass) — switched to `tokens.AMBER_100` so a photo-less card still reads as an intentional tile.
- **Name-wrap measurement:** `product_card.py` measures with an explicit `QFont(Cairo, pixelSize=15)` rather than the label's own `.font()` — at construction time the label hasn't been polished against the app stylesheet yet, so its reported font under-measures the text and can let Qt's own word-wrap push a line onto a visual 3rd line. Caught via screenshot review, fixed, covered by `test_product_card_name_label_never_clips_a_very_long_arabic_name`.
- **Grid-stretch fix:** `QScrollArea.setWidgetResizable(True)` stretches the hosted widget to fill the viewport when content is shorter than it; without a wrapping `QVBoxLayout` + trailing stretch around the `QGridLayout`, that leftover space was spreading into the cards themselves (very tall cards with a dead gap under the price pill). Also caught via screenshot review.
- **Menu management / add-items dialogs:** grepped for other `ProductGrid` usages — `pos_screen.py` is the only caller, so no other screen needed updating for card consistency.

## Test results

- `pytest -q`: **947 passed, 1 skipped** (the skip pre-exists, unrelated to this change). 19 new tests across the two new files; full existing suite stayed green.
- `ruff check .`: **all checks passed**.
- `python -m derby --selftest`: **all checks passed**, including `main_window_builds_for_owner_and_cashier`.
- `requirements.txt`: **unchanged** (`git diff --stat requirements.txt` is empty).
- No database schema changes (`derby/core/db/migrations.py` untouched).

## Screenshots

- `docs/ui/phase10_home.png` — Home screen with 2 busy tables, 1 takeaway draft, 1 running PlayStation session, and one empty just-opened table, all four filter/sort rules visible.
- `docs/ui/phase10_menu_cards.png` — cashier product grid: short/medium/long Arabic names, no-image placeholders, category pills.

## Not verified

- Real Windows 7 performance with 100+ live product photos (only exercised functionally in tests/offscreen renders here, not profiled on period hardware).
- The lazy-image-reveal path (`ProductGrid._reveal_visible_cards`) under real mouse-wheel/scrollbar-drag scrolling — tests exercise it programmatically (resizing, calling it directly), not via a simulated user scroll gesture.
- Touch-input pressed/hover feedback on an actual touchscreen (only validated via `property("pressed")`/QSS rules, not physically).
- Visual contrast of the open-order card's 4px right-edge kind accent at a glance — present and testable via `property("kind")`, but subtle in the screenshot; worth a look on the real screen.

## Manual checks for you

1. Open a table and start a PlayStation session; confirm both appear as cards on الرئيسية and tapping each opens the correct bill in the cashier screen.
2. Let a running PlayStation card sit for a minute or two and confirm its `HH:MM:SS` timer keeps advancing without the screen needing a manual refresh.
3. Pay one of the open orders from the cashier screen, then return to الرئيسية and confirm that card disappears within 5 seconds.
4. In the cashier screen, scroll through the product grid with every product having a real photo and confirm it stays smooth with no stutter on the actual cafe PC.
5. Add a product with a very long Arabic name and confirm it wraps to exactly two lines with "…" and never gets visually clipped or pushed under the price pill.
