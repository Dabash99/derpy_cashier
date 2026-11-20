"""Broad UI audit (item I/J of the UI fix pass): every main screen,
built with synthetic data, at the two target window sizes (1024x680 and
1366x768), under offscreen Qt. No PNG files are written -- every check
works against an in-memory QImage from widget.grab().

Checks, applied app-wide rather than one screen at a time:
  - invisible text: a visible QLabel/QPushButton with non-empty text
    must have SOME ink pixels (if 100% of its pixels are one color,
    the text is invisible -- same bug class as the sidebar/header one
    in test_shell_chrome_paint.py, generalized here with no need for a
    known-good reference image).
  - RTL: the sidebar sits to the right of the content area, and a
    table's first column is to the right of its last column.
  - text-fit: a label/button that doesn't opt into wrapping or elision
    must not need more width than it has been given.
  - table sizing: a table with no active internal scrollbar must be
    tall enough for its header + every row (not squeezed to near-zero
    by a plain QVBoxLayout outgrowing the window -- the reports-screen
    bug this was added for), and its header must not be vertically
    clipped.
  - no overlap: no two DIRECT siblings inside the same container may
    overlap (a combo box sitting on top of a table, for example).
"""
from __future__ import annotations

from collections import Counter

from PySide2.QtCore import QRect
from PySide2.QtGui import QColor
from PySide2.QtWidgets import QLabel, QPushButton, QTableView, QTableWidget, QTabWidget, QWidget

from derby.core.db import (
    addons_repo,
    categories_repo,
    expense_categories_repo,
    orders_repo,
    products_repo,
    ps_devices_repo,
    users_repo,
)
from derby.features.expenses import expenses_service
from derby.features.shell.idle_filter import IdleTimer
from derby.features.shell.main_window import MainWindow
from derby.features.supplies import supplies_service

_SIZES = ((1024, 680), (1366, 768))


def _dominant_color(image) -> QColor:
    counter = Counter()
    for y in range(0, image.height(), 3):
        for x in range(0, image.width(), 3):
            counter[image.pixelColor(x, y).rgb()] += 1
    most_common = counter.most_common(1)
    return QColor.fromRgb(most_common[0][0]) if most_common else QColor(255, 255, 255)


def _has_ink(image, tolerance: int = 24) -> bool:
    if image.width() == 0 or image.height() == 0:
        return True  # nothing to check; not this detector's concern
    bg = _dominant_color(image)
    for y in range(0, image.height(), 2):
        for x in range(0, image.width(), 2):
            pixel = image.pixelColor(x, y)
            if (
                abs(pixel.red() - bg.red()) > tolerance
                or abs(pixel.green() - bg.green()) > tolerance
                or abs(pixel.blue() - bg.blue()) > tolerance
            ):
                return True
    return False


def _seed_data(conn, owner_id: int) -> None:
    category_id = categories_repo.create_category(conn, "مشروبات")
    product_id = products_repo.create_product(conn, category_id, "قهوة عربي طويلة الاسم", "Arabic Coffee", 2500)
    group_id = addons_repo.create_group(conn, "الحجم", min_select=1, max_select=1)
    addons_repo.create_addon(conn, group_id, "كبير", 500)
    addons_repo.set_product_addon_groups(conn, product_id, [group_id])
    for name in ("كابتشينو", "شاي", "عصير برتقال", "كرواسون"):
        products_repo.create_product(conn, category_id, name, "", 1500)

    device = ps_devices_repo.list_devices(conn)[0]
    ps_devices_repo.set_rates(conn, device["id"], 4000, 6000)

    expense_category = expense_categories_repo.list_categories(conn)[0]
    for description in ("فاتورة اختبار طويلة النص", "صيانة ماكينة القهوة", "شراء أكواب ورقية"):
        expenses_service.create_expense(
            conn, expense_category["id"], 1000, expenses_service.today_business_date(conn), description, owner_id
        )
    supplies_service.add_supply(conn, "سكر أبيض ناعم", "كيلوجرامين", supplies_service.PRIORITY_URGENT, "ملاحظة تجريبية", owner_id)

    today = expenses_service.today_business_date(conn).isoformat()
    for index in range(4):
        order_id = orders_repo.create_order(conn, None, owner_id)
        orders_repo.create_order_item(conn, order_id, "product", product_id, "قهوة", 2500, 1, 2500)
        orders_repo.update_order_totals(conn, order_id, 2500, 0, 2500)
        orders_repo.mark_order_paid(
            conn, order_id, orders_repo.next_invoice_no(conn), owner_id, today, "cash" if index % 2 == 0 else "instapay"
        )


def _build_window(qapp, db_conn, tmp_path, user, size):
    mw = MainWindow(db_conn, user, IdleTimer(), tmp_path / "test_derby.db")
    mw.resize(*size)
    mw.show()
    for _ in range(30):
        qapp.processEvents()
    return mw


def _visible_text_widgets(root):
    widgets = list(root.findChildren(QLabel)) + list(root.findChildren(QPushButton))
    for widget in widgets:
        if not widget.isVisible():
            continue
        text = widget.text().strip() if hasattr(widget, "text") else ""
        if not text:
            continue
        if widget.width() <= 0 or widget.height() <= 0:
            continue
        yield widget, text


def _check_text_and_rtl(mw):
    # A widget grabbed on its own loses its real parent's painted
    # background (e.g. a muted-gray-on-black header label would render
    # as muted-gray-on-white in isolation and look "invisible" by
    # coincidence) -- crop every widget's rect out of ONE full-window
    # grab instead, which is what the user actually sees.
    full_image = mw.grab().toImage()
    window_rect = mw.rect()
    for widget, text in _visible_text_widgets(mw):
        top_left = widget.mapTo(mw, widget.rect().topLeft())
        full_rect = QRect(top_left, widget.size())
        widget_rect = full_rect.intersected(window_rect)
        if widget_rect.isEmpty():
            continue  # scrolled out of the visible viewport -- not this check's concern
        # Straddling the scroll viewport's edge (partially visible) is
        # normal for scrollable content and not meaningfully checkable
        # from a partial crop -- only check widgets that are at least
        # mostly on-screen.
        visible_area = widget_rect.width() * widget_rect.height()
        full_area = max(1, full_rect.width() * full_rect.height())
        if visible_area / full_area < 0.8:
            continue
        cropped = full_image.copy(widget_rect)
        assert _has_ink(cropped), "invisible text (no ink pixels at all): {0!r} on {1}".format(
            text, type(widget.parent()).__name__
        )
        if getattr(widget, "wordWrap", lambda: False)():
            continue
        metrics = widget.fontMetrics()
        needed = metrics.horizontalAdvance(text)
        available = widget.width() - 2 * 4  # rough padding allowance, not pixel-exact
        assert needed <= available + 12, "text may be clipped: {0!r} needs {1}px, widget is {2}px wide".format(
            text, needed, widget.width()
        )

    tables = list(mw.findChildren(QTableWidget)) + list(mw.findChildren(QTableView))
    for table in tables:
        header = table.horizontalHeader()
        if header.count() < 2:
            continue
        first_x = header.sectionViewportPosition(0)
        last_x = header.sectionViewportPosition(header.count() - 1)
        assert first_x >= last_x, "table column 0 must be on the right under RTL, got first_x={0} last_x={1}".format(
            first_x, last_x
        )


def _check_table_sizing(mw):
    """Catches the reports-screen bug: a table inside a plain
    QVBoxLayout that outgrows the window gets squeezed toward its
    near-zero minimum size hint instead of showing its real rows."""
    tables = list(mw.findChildren(QTableWidget)) + list(mw.findChildren(QTableView))
    for table in tables:
        if not table.isVisible():
            continue
        header = table.horizontalHeader()
        if header.count() == 0:
            continue
        header_font_height = header.fontMetrics().height()
        assert header.height() >= header_font_height, (
            "table header is vertically clipped: header height={0}px, font needs {1}px ({2} columns: {3})".format(
                header.height(), header_font_height, header.count(),
                [table.horizontalHeaderItem(c).text() if table.horizontalHeaderItem(c) else "" for c in range(header.count())],
            )
        )

        row_count = table.rowCount()
        if row_count == 0:
            continue
        vbar = table.verticalScrollBar()
        if vbar.isVisible() and vbar.maximum() > 0:
            continue  # intentionally capped height with its own internal scroll -- not a bug
        row_height = table.verticalHeader().defaultSectionSize()
        needed = header.height() + row_count * row_height
        assert table.height() >= needed - 8, (
            "table squeezed below its row content: height={0}px, needs ~{1}px for {2} rows + header".format(
                table.height(), needed, row_count
            )
        )


def _widget_label(widget):
    if isinstance(widget, (QLabel, QPushButton)):
        return "{0}({1!r})".format(type(widget).__name__, widget.text())
    return type(widget).__name__


def _check_no_overlapping_siblings(mw):
    """No two DIRECT siblings inside the same container may overlap --
    e.g. the top-items combo box that used to sit on top of its table
    instead of in the section's title row."""
    containers = [mw] + list(mw.findChildren(QWidget))
    for container in containers:
        siblings = [
            child for child in container.children()
            if isinstance(child, QWidget) and child.parent() is container and child.isVisible() and not child.isWindow()
        ]
        for i in range(len(siblings)):
            for j in range(i + 1, len(siblings)):
                a, b = siblings[i], siblings[j]
                rect_a = QRect(a.pos(), a.size())
                rect_b = QRect(b.pos(), b.size())
                overlap = rect_a.intersected(rect_b)
                assert overlap.width() <= 6 or overlap.height() <= 6, (
                    "{0} overlaps {1} inside {2} (overlap rect {3})".format(
                        _widget_label(a), _widget_label(b), type(container).__name__, overlap
                    )
                )


def _settle(qapp):
    """reload()/_clear_layout() patterns throughout the app replace a
    container's children via deleteLater(), which only actually removes
    the old widget on a later DeferredDelete event -- without flushing
    that explicitly, a stale (not-yet-destroyed) widget can still be a
    visible sibling at its old geometry, overlapping its replacement.
    That's a test-timing artifact, not a real bug: flush it before any
    geometry-based check runs.

    sendPostedEvents(None, ...) -- "for every object in the whole
    application" -- is deliberately avoided: this qapp is session-scoped
    across the entire test suite, and forcing deferred-delete delivery
    for objects left over from unrelated, already-finished tests caused
    a native access violation. Plain processEvents() cycles still
    deliver this test's own DeferredDelete events through the normal
    queue, just without reaching into every other test's leftovers."""
    for _ in range(15):
        qapp.processEvents()


def _check_screen_once(mw, qapp):
    _settle(qapp)
    _check_text_and_rtl(mw)
    _check_table_sizing(mw)
    _check_no_overlapping_siblings(mw)


def _check_screen(mw, qapp):
    _check_screen_once(mw, qapp)
    for tabs_widget in mw.findChildren(QTabWidget):
        if not tabs_widget.isVisible():
            continue
        original_index = tabs_widget.currentIndex()
        for index in range(tabs_widget.count()):
            tabs_widget.setCurrentIndex(index)
            qapp.processEvents()
            _check_screen_once(mw, qapp)
        tabs_widget.setCurrentIndex(original_index)
        qapp.processEvents()


def test_rtl_sidebar_is_right_of_content_at_both_sizes(qapp, db_conn, tmp_path):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    _seed_data(db_conn, owner_id)
    for size in _SIZES:
        mw = MainWindow(db_conn, users_repo.get_user(db_conn, owner_id), IdleTimer(), tmp_path / "test_derby.db")
        mw.resize(*size)
        mw.show()
        qapp.processEvents()
        assert mw._sidebar.x() > mw._content_stack.x(), "sidebar must be to the right of the content area"
        mw.close()


def test_every_owner_screen_at_both_sizes(qapp, db_conn, tmp_path):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    _seed_data(db_conn, owner_id)
    for size in _SIZES:
        mw = _build_window(qapp, db_conn, tmp_path, owner, size)
        for key, widget in mw._screens.items():
            mw._on_navigate(key)
            qapp.processEvents()
            _check_screen(mw, qapp)
        mw.close()


def test_every_cashier_screen_at_both_sizes(qapp, db_conn, tmp_path):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    _seed_data(db_conn, owner_id)
    cashier_id = users_repo.create_user(db_conn, "Cashier", users_repo.ROLE_CASHIER, "2222")
    cashier = users_repo.get_user(db_conn, cashier_id)
    for size in _SIZES:
        mw = _build_window(qapp, db_conn, tmp_path, cashier, size)
        for key, widget in mw._screens.items():
            mw._on_navigate(key)
            qapp.processEvents()
            _check_screen(mw, qapp)
        mw.close()


def test_closures_list_dialog_at_both_sizes(qapp, db_conn, tmp_path):
    """ClosuresListDialog isn't reached by normal screen/tab navigation
    (it's opened on demand from the backup/closing tab), so the main
    sweep above never builds it -- check it explicitly."""
    from derby.core.db import day_closures_repo
    from derby.features.closing.closures_list_dialog import ClosuresListDialog

    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    for index in range(4):
        day_closures_repo.create_closure(
            db_conn, "2026-01-{0:02d}".format(index + 1), "auto", "تقرير تجريبي", 3, 5000, 1000, 4000, 0, 0
        )

    for size in _SIZES:
        dialog = ClosuresListDialog(db_conn, owner, tmp_path / "test_derby.db")
        dialog.resize(*size)
        dialog.show()
        _settle(qapp)
        _check_screen_once(dialog, qapp)
        dialog.close()
