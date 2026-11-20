"""Builds the single app-wide Qt stylesheet from derby/core/theme/tokens.py.

No gradients, shadows (QGraphicsEffect), or transition effects — those
visibly lag on old office PCs with weak/no GPU. Buttons and inputs are
sized generously (big tap targets) since the PlayStation corner's device
may be used from a touchscreen.

Backward-compatible selectors already used across every screen keep
working unchanged: role="title"/"subtitle"/"error" on QLabel, danger="true"
and flat="true" on QPushButton, active="true"/"false" on sidebar buttons,
and the #Sidebar/#Header object names. `variant="..."` is the newer,
broader hook (primary/secondary/ghost/card/chip/badge/table) screens can
opt into per docs/BRAND.md's visual language. A QPushButton with no
variant set renders as a neutral white/bordered button, NOT amber --
amber is reserved for variant="primary" on the handful of genuine
primary call-to-action buttons (pay, login, confirm payment), matching
docs/BRAND.md's 15%-amber usage ratio; tagging every button amber would
blow well past that and make nothing stand out.
"""
from __future__ import annotations

from derby.core.theme import tokens

FONT_FAMILY = "Cairo"


def build_stylesheet() -> str:
    return """
    * {{
        font-family: "{font}";
        font-size: {font_size_body}px;
        color: {text_primary};
    }}

    QWidget {{
        background-color: {background};
    }}

    QMainWindow, QDialog {{
        background-color: {background};
    }}

    /* ---- Buttons --------------------------------------------------- */

    QPushButton {{
        background-color: {surface};
        color: {text_primary};
        border: 1px solid {surface_border};
        border-radius: {radius_md}px;
        padding: {space_2}px {space_4}px;
        min-height: {control_height_default}px;
        font-weight: 600;
    }}

    QPushButton:hover {{
        background-color: {background};
    }}

    QPushButton:pressed {{
        background-color: {surface_border};
    }}

    QPushButton:disabled {{
        background-color: {disabled_fill};
        color: {disabled_text};
        border: none;
    }}

    QPushButton[variant="primary"] {{
        background-color: {primary_fill};
        color: {primary_text};
        border: none;
        min-height: {control_height_primary}px;
        font-size: {font_size_subtitle}px;
    }}

    QPushButton[variant="primary"]:hover {{
        background-color: {primary_fill_hover};
    }}

    QPushButton[variant="primary"]:pressed {{
        background-color: {primary_fill_pressed};
    }}

    QPushButton[variant="secondary"] {{
        background-color: {secondary_fill};
        color: {secondary_text};
    }}

    QPushButton[variant="secondary"]:hover {{
        background-color: {secondary_fill_hover};
    }}

    QPushButton[variant="secondary"]:pressed {{
        background-color: {secondary_fill_pressed};
    }}

    QPushButton[flat="true"], QPushButton[variant="ghost"] {{
        background-color: transparent;
        color: {ghost_text};
        border: 1px solid {ghost_border};
        font-weight: 500;
    }}

    QPushButton[flat="true"]:hover, QPushButton[variant="ghost"]:hover {{
        background-color: {surface_border};
    }}

    QPushButton[danger="true"], QPushButton[variant="danger"] {{
        background-color: {danger};
        color: {white};
    }}

    QPushButton[danger="true"]:hover, QPushButton[variant="danger"]:hover {{
        background-color: {danger};
    }}

    QPushButton[danger="true"]:pressed, QPushButton[variant="danger"]:pressed {{
        background-color: {danger_pressed};
    }}

    /* ---- Inputs ------------------------------------------------------ */

    QLineEdit, QComboBox, QSpinBox {{
        background-color: {surface};
        border: 1px solid {surface_border};
        border-radius: {radius_md}px;
        padding: {space_2}px {space_3}px;
        min-height: {control_height_input}px;
    }}

    QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
        border: 1px solid {primary_fill};
    }}

    /* ---- Labels -------------------------------------------------- */

    QLabel {{
        background-color: transparent;
    }}

    QLabel[role="title"] {{
        font-size: {font_size_title}px;
        font-weight: 700;
        padding-right: 8px;
    }}

    QLabel[role="subtitle"] {{
        color: {text_secondary};
    }}

    QLabel[role="error"] {{
        color: {danger};
    }}

    QLabel[role="success"] {{
        color: {success};
        font-weight: 600;
    }}

    QLabel[variant="chip"] {{
        background-color: {surface};
        border: 1px solid {surface_border};
        border-radius: {radius_pill}px;
        padding: {space_1}px {space_3}px;
    }}

    QLabel[variant="badge"] {{
        background-color: {amber_100};
        color: {text_on_amber};
        border-radius: {radius_sm}px;
        padding: 2px {space_2}px;
        font-weight: 600;
    }}

    /* ---- Cards / surfaces ------------------------------------------- */

    QFrame[variant="card"], QWidget[variant="card"] {{
        background-color: {surface};
        border: 1px solid {surface_border};
        border-radius: {radius_lg}px;
    }}

    QWidget[variant="banner"] {{
        background-color: {amber_100};
        border-bottom: 1px solid {amber_300};
    }}

    /* ---- Sidebar / header -------------------------------------------- */

    #Sidebar, QWidget[variant="sidebar"] {{
        background-color: {sidebar_background};
    }}

    #SidebarScrollArea, #SidebarScrollArea QWidget {{
        background-color: transparent;
        border: none;
    }}

    #Sidebar QPushButton, QWidget[variant="sidebar"] QPushButton {{
        background-color: transparent;
        color: {text_on_dark};
        text-align: right;
        border-radius: {radius_md}px;
        padding: {space_3}px {space_4}px;
        font-size: {font_size_subtitle}px;
        font-weight: 500;
    }}

    #Sidebar QPushButton:hover, QWidget[variant="sidebar"] QPushButton:hover {{
        background-color: {sidebar_active};
    }}

    #Sidebar QPushButton[active="true"], QWidget[variant="sidebar"] QPushButton[active="true"] {{
        background-color: {sidebar_active};
        color: {amber_500};
        font-weight: 700;
        border-right: 3px solid {amber_500};
    }}

    #Header, QWidget[variant="header"] {{
        background-color: {header_background};
        color: {text_on_dark};
    }}

    #Header QLabel, QWidget[variant="header"] QLabel {{
        color: {text_on_dark};
        background-color: transparent;
    }}

    #Header QLabel[role="subtitle"], QWidget[variant="header"] QLabel[role="subtitle"] {{
        color: {text_on_dark_muted};
    }}

    #Header QPushButton, QWidget[variant="header"] QPushButton {{
        background-color: transparent;
        color: {text_on_dark};
        border: 1px solid {text_on_dark_muted};
        min-height: {control_height_default}px;
        font-weight: 500;
    }}

    #Header QPushButton:hover, QWidget[variant="header"] QPushButton:hover {{
        background-color: {sidebar_active};
    }}

    /* ---- Tables -------------------------------------------------- */

    QTableWidget, QTableView, QWidget[variant="table"] {{
        background-color: {surface};
        alternate-background-color: {background};
        gridline-color: {surface_border};
        border: 1px solid {surface_border};
        border-radius: {radius_md}px;
    }}

    QHeaderView::section {{
        background-color: {background};
        color: {text_secondary};
        border: none;
        border-bottom: 1px solid {surface_border};
        padding: {space_3}px {space_3}px;
        min-height: {header_min_height}px;
        font-weight: 600;
    }}

    QTableWidget::item, QTableView::item {{
        min-height: {control_height_row}px;
        padding: {space_1}px {space_2}px;
    }}

    QListWidget {{
        background-color: {surface};
        border: 1px solid {surface_border};
        border-radius: {radius_md}px;
    }}

    QListWidget::item {{
        min-height: {control_height_row}px;
        padding: {space_2}px {space_3}px;
    }}

    QListWidget::item:selected {{
        background-color: {amber_100};
        color: {text_on_amber};
    }}

    /* ---- Simple proportional bars (dashboard category/PS split) ---- */

    QWidget[variant="barTrack"] {{
        background-color: {surface_border};
        border-radius: {radius_sm}px;
    }}

    QWidget[variant="barFill"] {{
        background-color: {sidebar_background};
        border-radius: {radius_sm}px;
    }}

    QWidget[variant="barFillAccent"] {{
        background-color: {amber_500};
        border-radius: {radius_sm}px;
    }}

    /* ---- Tabs -------------------------------------------------- */

    QTabBar::tab {{
        min-height: {header_min_height}px;
        padding: {space_2}px {space_4}px;
        margin-right: {space_1}px;
        font-weight: 600;
    }}

    QTabBar::tab:selected {{
        color: {amber_900};
        border-bottom: 2px solid {amber_500};
    }}
    """.format(
        font=FONT_FAMILY,
        font_size_body=tokens.FONT_SIZE_BODY,
        font_size_title=tokens.FONT_SIZE_TITLE,
        font_size_subtitle=tokens.FONT_SIZE_SUBTITLE,
        text_primary=tokens.TEXT_PRIMARY,
        text_secondary=tokens.TEXT_SECONDARY,
        text_on_dark=tokens.TEXT_ON_DARK,
        text_on_dark_muted=tokens.TEXT_ON_DARK_MUTED,
        text_on_amber=tokens.TEXT_ON_AMBER,
        background=tokens.BACKGROUND,
        surface=tokens.SURFACE,
        surface_border=tokens.SURFACE_BORDER,
        white=tokens.WHITE,
        amber_100=tokens.AMBER_100,
        amber_300=tokens.AMBER_300,
        amber_500=tokens.AMBER_500,
        amber_900=tokens.AMBER_900,
        header_min_height=40,
        primary_fill=tokens.PRIMARY_FILL,
        primary_fill_hover=tokens.PRIMARY_FILL_HOVER,
        primary_fill_pressed=tokens.PRIMARY_FILL_PRESSED,
        primary_text=tokens.PRIMARY_TEXT,
        secondary_fill=tokens.SECONDARY_FILL,
        secondary_fill_hover=tokens.SECONDARY_FILL_HOVER,
        secondary_fill_pressed=tokens.SECONDARY_FILL_PRESSED,
        secondary_text=tokens.SECONDARY_TEXT,
        ghost_text=tokens.GHOST_TEXT,
        ghost_border=tokens.GHOST_BORDER,
        danger=tokens.DANGER,
        danger_pressed=tokens.DANGER_PRESSED,
        success=tokens.SUCCESS,
        disabled_fill=tokens.DISABLED_FILL,
        disabled_text=tokens.DISABLED_TEXT,
        sidebar_background=tokens.SIDEBAR_BACKGROUND,
        sidebar_active=tokens.SIDEBAR_ACTIVE,
        header_background=tokens.HEADER_BACKGROUND,
        radius_sm=tokens.RADIUS_SM,
        radius_md=tokens.RADIUS_MD,
        radius_lg=tokens.RADIUS_LG,
        radius_pill=tokens.RADIUS_PILL,
        space_1=tokens.SPACE_1,
        space_2=tokens.SPACE_2,
        space_3=tokens.SPACE_3,
        space_4=tokens.SPACE_4,
        control_height_primary=tokens.CONTROL_HEIGHT_PRIMARY,
        control_height_default=tokens.CONTROL_HEIGHT_DEFAULT,
        control_height_input=tokens.CONTROL_HEIGHT_INPUT,
        control_height_row=tokens.CONTROL_HEIGHT_ROW,
    )
