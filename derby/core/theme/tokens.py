"""Design tokens: the single source of truth for every color, spacing
value, radius, font size/weight, and control height used anywhere in the
app. derby/core/theme/stylesheet.py is the only consumer that turns these
into QSS; nothing else should hardcode a hex color or a pixel value that
belongs here.

The brand palette itself is fixed -- see docs/BRAND.md. These are not
"improve the colors" numbers; they are decisions.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Brand colors (fixed -- docs/BRAND.md)
# ---------------------------------------------------------------------------

JET_BLACK = "#0F0F10"
AMBER_GOLD = "#D98E04"
CREAM = "#FAF6F0"
WHITE = "#FFFFFF"

BLACK_900 = "#0F0F10"
BLACK_700 = "#292929"
BLACK_500 = "#454545"
BLACK_300 = "#777777"
BLACK_100 = "#B8B8BB"

AMBER_900 = "#9C6200"
AMBER_700 = "#B87900"
AMBER_500 = "#D98E04"
AMBER_300 = "#E9AD36"
AMBER_100 = "#F5D18A"

# ---------------------------------------------------------------------------
# Semantic colors, derived from the palette above. These are what
# stylesheet.py (and tests/test_theme_contrast.py) actually reason about --
# never a raw hex in a selector.
# ---------------------------------------------------------------------------

# Surfaces
BACKGROUND = CREAM
SURFACE = WHITE
SURFACE_BORDER = BLACK_100
SIDEBAR_BACKGROUND = JET_BLACK
SIDEBAR_ACTIVE = BLACK_700
HEADER_BACKGROUND = JET_BLACK

# Text
TEXT_PRIMARY = BLACK_900          # on cream/white
TEXT_SECONDARY = BLACK_500        # on cream/white
TEXT_ON_DARK = CREAM              # on black sidebar/header
TEXT_ON_DARK_MUTED = BLACK_100    # on black sidebar/header, de-emphasized
TEXT_ON_AMBER = JET_BLACK         # amber fill always pairs with black text
TEXT_ON_BLACK_FILL = CREAM        # black-fill secondary buttons use cream/white text

# Actions
PRIMARY_FILL = AMBER_500
PRIMARY_FILL_HOVER = AMBER_300
PRIMARY_FILL_PRESSED = AMBER_700
PRIMARY_TEXT = TEXT_ON_AMBER

SECONDARY_FILL = JET_BLACK
SECONDARY_FILL_HOVER = BLACK_700
SECONDARY_FILL_PRESSED = BLACK_900
SECONDARY_TEXT = TEXT_ON_BLACK_FILL

GHOST_BORDER = BLACK_100
GHOST_TEXT = TEXT_PRIMARY

# Semantic state colors. Amber shades stand in for "warning" per
# docs/BRAND.md (amber is the only accent besides black/cream/white); state
# must never be conveyed by color alone -- every usage pairs this with an
# icon or label text, not color by itself.
DANGER = "#B3261E"
DANGER_PRESSED = "#8C1D17"
SUCCESS = "#1E6F46"
WARNING = AMBER_900
INFO = BLACK_500

DISABLED_FILL = BLACK_100
DISABLED_TEXT = BLACK_300

# ---------------------------------------------------------------------------
# Spacing scale (px)
# ---------------------------------------------------------------------------

SPACE_1 = 4
SPACE_2 = 8
SPACE_3 = 12
SPACE_4 = 16
SPACE_6 = 24
SPACE_8 = 32

# ---------------------------------------------------------------------------
# Radius scale (px)
# ---------------------------------------------------------------------------

RADIUS_SM = 4
RADIUS_MD = 8
RADIUS_LG = 12
RADIUS_PILL = 999

# ---------------------------------------------------------------------------
# Control heights (px). Primary actions and list rows must stay touch-
# friendly even though this is a mouse-first desktop app, since the PS
# corner's device may be used from a touchscreen till.
# ---------------------------------------------------------------------------

CONTROL_HEIGHT_PRIMARY = 48   # primary call-to-action buttons (e.g. "دفع", login)
CONTROL_HEIGHT_DEFAULT = 40   # ordinary buttons -- same height as inputs
CONTROL_HEIGHT_INPUT = 40     # text inputs, combo boxes, spin boxes
CONTROL_HEIGHT_ROW = 44       # list/table rows

# ---------------------------------------------------------------------------
# Typography
# ---------------------------------------------------------------------------

FONT_SIZE_BODY = 15
FONT_SIZE_SMALL = 13
FONT_SIZE_SUBTITLE = 16
FONT_SIZE_TITLE = 20
FONT_SIZE_DISPLAY = 28        # big numeric displays: totals, prices, timers

FONT_WEIGHT_REGULAR = 400
FONT_WEIGHT_MEDIUM = 500
FONT_WEIGHT_SEMIBOLD = 600
FONT_WEIGHT_BOLD = 700
