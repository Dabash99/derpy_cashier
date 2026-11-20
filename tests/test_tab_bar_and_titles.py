"""Tab-bar clipping bug: under RTL, Qt's native tab width/paint margin
left the first Arabic glyph touching (or past) the tab's right edge
regardless of declared QSS padding -- "المصروفات" rendered as
"لمصروفات". Checked at both target window sizes, for every
QTabWidget's every tab, and for every role="title" page label.
"""
from __future__ import annotations

from PySide2.QtCore import QRect
from PySide2.QtGui import QFontMetrics
from PySide2.QtWidgets import QLabel, QTabWidget

from derby.core.db import users_repo
from derby.features.expenses.expenses_screen import ExpensesScreen
from derby.features.menu.menu_screen import MenuScreen
from derby.features.playstation.playstation_screen import PlaystationScreen
from derby.features.reports.reports_screen import ReportsScreen
from derby.features.settings.settings_screen import SettingsScreen
from derby.features.tables.tables_screen import TablesScreen

_SIZES = ((1024, 680), (1366, 768))
_MIN_SIDE_PADDING = 8  # px of real slack required on each side, not a pixel-exact fit


def _owner(db_conn):
    owner_id = users_repo.create_user(db_conn, "Owner", users_repo.ROLE_OWNER, "1111")
    return users_repo.get_user(db_conn, owner_id)


def _build_screens(conn, owner, db_path):
    return {
        "expenses": ExpensesScreen(conn, owner),
        "menu": MenuScreen(conn, owner["id"]),
        "playstation": PlaystationScreen(conn, owner),
        "reports": ReportsScreen(conn, owner),
        "settings": SettingsScreen(conn, owner, db_path),
        "tables": TablesScreen(conn, owner),
    }


def _assert_tabs_not_clipped(qapp, screen_name, screen, full_image, window_rect):
    for tabs_widget in screen.findChildren(QTabWidget):
        bar = tabs_widget.tabBar()
        for index in range(bar.count()):
            text = bar.tabText(index)
            if not text:
                continue
            rect = bar.tabRect(index)
            metrics = QFontMetrics(bar.font())
            needed = metrics.horizontalAdvance(text)
            assert needed + 2 * _MIN_SIDE_PADDING <= rect.width(), (
                "{0}: tab {1!r} needs {2}px + padding but only has {3}px (tab {4} of {5})".format(
                    screen_name, text, needed, rect.width(), index, type(tabs_widget).__name__
                )
            )

            top_left = bar.mapTo(screen, rect.topLeft())
            crop_rect = QRect(top_left, rect.size()).intersected(window_rect)
            if crop_rect.isEmpty():
                continue
            cropped = full_image.copy(crop_rect)
            if cropped.width() < 3 or cropped.height() < 3:
                continue
            # Background reference: top padding strip, just below the top
            # border -- blank for any single-line tab, never glyph ink.
            background_ref = cropped.pixelColor(cropped.width() // 2, 2)
            # Exclude the top/bottom few pixels: the selected indicator
            # is an intentional full-width border there, not a glyph --
            # only the text band in the vertical middle is checked.
            band_top = max(0, cropped.height() // 2 - 6)
            band_height = min(12, cropped.height() - band_top)
            if band_height <= 0:
                continue
            edge_width = 1
            left_edge = cropped.copy(0, band_top, edge_width, band_height)
            right_edge = cropped.copy(max(0, cropped.width() - edge_width), band_top, edge_width, band_height)
            # The very edge column of the tab, in the text's own vertical
            # band, must be background -- otherwise a glyph is literally
            # cut off at the tab boundary (not just rendered close to it).
            for edge_name, edge_image in (("right", right_edge), ("left", left_edge)):
                assert not _has_dark_ink_near_edge(edge_image, background_ref), (
                    "{0}: tab {1!r} has ink touching its {2} edge (clipped glyph)".format(screen_name, text, edge_name)
                )


def _has_dark_ink_near_edge(edge_image, background_ref) -> bool:
    if edge_image.width() == 0 or edge_image.height() == 0:
        return False
    tolerance = 60
    for y in range(edge_image.height()):
        for x in range(edge_image.width()):
            pixel = edge_image.pixelColor(x, y)
            if (
                abs(pixel.red() - background_ref.red()) > tolerance
                or abs(pixel.green() - background_ref.green()) > tolerance
                or abs(pixel.blue() - background_ref.blue()) > tolerance
            ):
                return True
    return False


def _assert_titles_not_clipped(screen_name, screen):
    for label in screen.findChildren(QLabel):
        if label.property("role") != "title" or not label.isVisible():
            continue
        text = label.text()
        if not text:
            continue
        metrics = QFontMetrics(label.font())
        needed = metrics.horizontalAdvance(text)
        assert needed + _MIN_SIDE_PADDING <= label.width(), (
            "{0}: title label {1!r} needs {2}px but only has {3}px".format(screen_name, text, needed, label.width())
        )


def test_no_clipped_tabs_or_titles_at_both_sizes(qapp, db_conn, tmp_path):
    owner = _owner(db_conn)
    db_path = tmp_path / "test_derby.db"
    screens = _build_screens(db_conn, owner, db_path)

    for size in _SIZES:
        for name, screen in screens.items():
            screen.resize(*size)
            screen.show()
            for _ in range(10):
                qapp.processEvents()

            full_image = screen.grab().toImage()
            window_rect = screen.rect()
            _assert_tabs_not_clipped(qapp, name, screen, full_image, window_rect)
            _assert_titles_not_clipped(name, screen)
            screen.hide()
