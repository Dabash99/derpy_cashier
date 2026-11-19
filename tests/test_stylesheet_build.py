"""build_stylesheet() must produce valid QSS: no .format() KeyErrors, and
no "Unknown property"/"Could not parse" warnings from Qt's CSS parser when
actually applied to a QApplication."""
from __future__ import annotations

from PySide2.QtWidgets import QComboBox, QLabel, QLineEdit, QPushButton, QWidget

from derby.core.theme.stylesheet import build_stylesheet


def test_build_stylesheet_returns_nonempty_css():
    css = build_stylesheet()
    assert isinstance(css, str)
    assert len(css) > 0
    assert "QPushButton" in css


def test_stylesheet_applies_without_qt_css_warnings(qapp, capfd):
    qapp.setStyleSheet(build_stylesheet())

    widgets = [QPushButton("x"), QLabel("x"), QLineEdit(), QComboBox(), QWidget()]
    for widget in widgets:
        widget.setProperty("role", "title")
        widget.setProperty("danger", "true")
        widget.setProperty("variant", "primary")
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    captured = capfd.readouterr()
    combined = (captured.out + captured.err).lower()
    for marker in ("unknown property", "could not parse", "css parsing"):
        assert marker not in combined, "Qt CSS warning found: {0}".format(combined)


def test_all_declared_variant_selectors_are_well_formed():
    css = build_stylesheet()
    assert css.count("{") == css.count("}")
    for variant in ("primary", "secondary", "ghost", "danger", "card", "chip", "badge", "sidebar", "header", "table"):
        assert 'variant="{0}"'.format(variant) in css
