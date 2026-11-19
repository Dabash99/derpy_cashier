"""Broad UI audit (item I/J of the UI fix pass): every main screen,
built with synthetic data, at the two target window sizes (1024x680 and
1366x768), under offscreen Qt. No PNG files are written -- every check
works against an in-memory QImage from widget.grab().

Three checks, applied app-wide rather than one screen at a time:
  - invisible text: a visible QLabel/QPushButton with non-empty text
    must have SOME ink pixels (if 100% of its pixels are one color,
    the text is invisible -- same bug class as the sidebar/header one
    in test_shell_chrome_paint.py, generalized here with no need for a
    known-good reference image).
  - RTL: the sidebar sits to the right of the content area, and a
    table's first column is to the right of its last column.
  - text-fit: a label/button that doesn't opt into wrapping or elision
    must not need more width than it has been given.
"""
from __future__ import annotations

from collections import Counter

from PySide2.QtCore import QRect
from PySide2.QtGui import QColor
from PySide2.QtWidgets import QLabel, QPushButton, QTableView, QTableWidget

from derby.core.db import (
    addons_repo,
    categories_repo,
    expense_categories_repo,
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

    device = ps_devices_repo.list_devices(conn)[0]
    ps_devices_repo.set_rates(conn, device["id"], 4000, 6000)

    expense_category = expense_categories_repo.list_categories(conn)[0]
    expenses_service.create_expense(
        conn, expense_category["id"], 1000, expenses_service.today_business_date(conn), "فاتورة اختبار طويلة النص", owner_id
    )
    supplies_service.add_supply(conn, "سكر أبيض ناعم", "كيلوجرامين", supplies_service.PRIORITY_URGENT, "ملاحظة تجريبية", owner_id)


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


def _check_screen(mw, qapp):
    qapp.processEvents()
    # A widget grabbed on its own loses its real parent's painted
    # background (e.g. a muted-gray-on-black header label would render
    # as muted-gray-on-white in isolation and look "invisible" by
    # coincidence) -- crop every widget's rect out of ONE full-window
    # grab instead, which is what the user actually sees.
    full_image = mw.grab().toImage()
    window_rect = mw.rect()
    for widget, text in _visible_text_widgets(mw):
        top_left = widget.mapTo(mw, widget.rect().topLeft())
        widget_rect = QRect(top_left, widget.size()).intersected(window_rect)
        if widget_rect.isEmpty():
            continue  # scrolled out of the visible viewport -- not this check's concern
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
