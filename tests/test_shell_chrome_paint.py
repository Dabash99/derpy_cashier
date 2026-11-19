"""Reproduces a real rendering bug: Header and Sidebar are plain QWidget
subclasses styled entirely through QSS (#Header/#Sidebar background-color).
A bare QWidget does NOT paint a stylesheet background unless
Qt.WA_StyledBackground is set on it (QFrame/QPushButton/QLabel do this
painting themselves and are unaffected) -- without it, Qt's paint/update
optimizations can skip repainting content that was never given an
explicit "this region is opaque and styled" hint, which is exactly why
grabbing the Sidebar/Header on their own (freshly shown, freshly
polished) looked fine while grabbing the real MainWindow -- where they
sit as siblings of a large QStackedWidget that forces extra layout/paint
cycles -- dropped their text. This is not an offscreen-platform quirk;
the user reported the same missing text in the real, on-screen app.
"""
from __future__ import annotations

from PySide2.QtCore import QPoint, QRect
from PySide2.QtGui import QColor

from derby.core.db import users_repo
from derby.core.theme import tokens
from derby.features.shell.idle_filter import IdleTimer
from derby.features.shell.main_window import MainWindow


def _count_ink_pixels(image, background_hex: str, tolerance: int = 24) -> int:
    bg = QColor(background_hex)
    count = 0
    for y in range(0, image.height(), 2):
        for x in range(0, image.width(), 2):
            pixel = image.pixelColor(x, y)
            if (
                abs(pixel.red() - bg.red()) > tolerance
                or abs(pixel.green() - bg.green()) > tolerance
                or abs(pixel.blue() - bg.blue()) > tolerance
            ):
                count += 1
    return count


def _build_shown_main_window(qapp, db_conn, tmp_path):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    owner = users_repo.get_user(db_conn, owner_id)
    mw = MainWindow(db_conn, owner, IdleTimer(), tmp_path / "test_derby.db")
    mw.resize(1100, 720)
    mw.show()
    for _ in range(30):
        qapp.processEvents()
    return mw


def test_sidebar_text_renders_inside_the_real_main_window(qapp, db_conn, tmp_path):
    mw = _build_shown_main_window(qapp, db_conn, tmp_path)

    # Reference: the sidebar grabbed directly -- already proven correct
    # (icons + Arabic labels both render here regardless of the bug below).
    reference_image = mw._sidebar.grab().toImage()
    reference_ink = _count_ink_pixels(reference_image, tokens.SIDEBAR_BACKGROUND)

    # Subject: the SAME sidebar widget, cropped out of a grab() of the
    # whole top-level MainWindow -- this is what the user actually sees.
    top_left = mw._sidebar.mapTo(mw, QPoint(0, 0))
    sidebar_rect = QRect(top_left, mw._sidebar.size())
    full_window_image = mw.grab().toImage()
    cropped = full_window_image.copy(sidebar_rect)
    subject_ink = _count_ink_pixels(cropped, tokens.SIDEBAR_BACKGROUND)

    assert subject_ink >= reference_ink * 0.85, (
        "sidebar text/icons are missing when rendered inside the real MainWindow: "
        "{0} ink pixels inside MainWindow vs {1} in the isolated (known-good) grab".format(subject_ink, reference_ink)
    )


def test_header_text_renders_inside_the_real_main_window(qapp, db_conn, tmp_path):
    from derby.core.db import settings_repo

    settings_repo.set_value(db_conn, "cafe_name", "ديربي")
    mw = _build_shown_main_window(qapp, db_conn, tmp_path)

    reference_image = mw._header.grab().toImage()
    reference_ink = _count_ink_pixels(reference_image, tokens.HEADER_BACKGROUND)

    top_left = mw._header.mapTo(mw, QPoint(0, 0))
    header_rect = QRect(top_left, mw._header.size())
    full_window_image = mw.grab().toImage()
    cropped = full_window_image.copy(header_rect)
    subject_ink = _count_ink_pixels(cropped, tokens.HEADER_BACKGROUND)

    assert subject_ink >= reference_ink * 0.85, (
        "header logo/cafe-name/user text is missing when rendered inside the real MainWindow: "
        "{0} ink pixels inside MainWindow vs {1} in the isolated (known-good) grab".format(subject_ink, reference_ink)
    )
