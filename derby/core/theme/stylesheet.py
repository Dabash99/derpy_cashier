"""Builds the app-wide Qt stylesheet.

No gradients, shadows, or transition effects — those are the kind of
GPU-ish work that visibly lags on old office PCs. Buttons and inputs are
sized generously (big tap targets) since a touchscreen may be used.
"""
from __future__ import annotations

from derby.core.theme import colors

FONT_FAMILY = "Cairo"


def build_stylesheet() -> str:
    return """
    * {{
        font-family: "{font}";
        font-size: 15px;
        color: {text_primary};
    }}

    QWidget {{
        background-color: {background};
    }}

    QMainWindow, QDialog {{
        background-color: {background};
    }}

    QPushButton {{
        background-color: {accent};
        color: {text_on_accent};
        border: none;
        border-radius: 6px;
        padding: 12px 20px;
        min-height: 28px;
    }}

    QPushButton:hover {{
        background-color: {accent};
    }}

    QPushButton:pressed {{
        background-color: {accent_pressed};
    }}

    QPushButton:disabled {{
        background-color: {border};
        color: {text_secondary};
    }}

    QPushButton[flat="true"] {{
        background-color: transparent;
        color: {text_primary};
        border: 1px solid {border};
    }}

    QPushButton[danger="true"] {{
        background-color: {danger};
    }}

    QPushButton[danger="true"]:pressed {{
        background-color: {danger_pressed};
    }}

    QLineEdit, QComboBox, QSpinBox {{
        background-color: {surface};
        border: 1px solid {border};
        border-radius: 6px;
        padding: 10px 12px;
        min-height: 24px;
    }}

    QLabel {{
        background-color: transparent;
    }}

    QLabel[role="title"] {{
        font-size: 20px;
        font-weight: bold;
    }}

    QLabel[role="subtitle"] {{
        color: {text_secondary};
    }}

    QLabel[role="error"] {{
        color: {danger};
    }}

    #Sidebar {{
        background-color: {sidebar_background};
    }}

    #Sidebar QPushButton {{
        background-color: transparent;
        color: {sidebar_text};
        text-align: right;
        border-radius: 6px;
        padding: 14px 18px;
        font-size: 16px;
    }}

    #Sidebar QPushButton:hover {{
        background-color: {sidebar_active};
    }}

    #Sidebar QPushButton[active="true"] {{
        background-color: {sidebar_active};
        color: {sidebar_text};
        font-weight: bold;
    }}

    #Header {{
        background-color: {surface};
        border-bottom: 1px solid {border};
    }}
    """.format(
        font=FONT_FAMILY,
        text_primary=colors.TEXT_PRIMARY,
        text_secondary=colors.TEXT_SECONDARY,
        text_on_accent=colors.TEXT_ON_ACCENT,
        background=colors.BACKGROUND,
        surface=colors.SURFACE,
        border=colors.BORDER,
        accent=colors.ACCENT,
        accent_pressed=colors.ACCENT_PRESSED,
        danger=colors.DANGER,
        danger_pressed=colors.DANGER_PRESSED,
        sidebar_background=colors.SIDEBAR_BACKGROUND,
        sidebar_text=colors.SIDEBAR_TEXT,
        sidebar_active=colors.SIDEBAR_ACTIVE,
    )
