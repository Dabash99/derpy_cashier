"""Hand-drawn line-icon set for Derby, authored directly as SVG path/shape
data (no external icon library, no network fetch -- see docs/BRAND.md).

Every icon shares one visual language per the design guidance consulted in
A0 (ui-ux-pro-max: "one icon stroke-weight per hierarchy level", "SVG
icons, not emoji"): 24x24 viewBox, stroke-only (no fill except the literal
dot in the warning icon), stroke-width 2, round caps/joins. `{S}` is a
format placeholder for the stroke color, substituted by render_assets.py
once per dark/light variant -- these strings are never modified by hand
per-variant, only recolored.
"""
from __future__ import annotations

import math

_COMMON = 'fill="none" stroke="{S}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'


def _gear_teeth(cx: float, cy: float, r_in: float, r_out: float, count: int):
    lines = []
    for i in range(count):
        angle = math.radians(i * (360 / count))
        x1 = cx + r_in * math.cos(angle)
        y1 = cy + r_in * math.sin(angle)
        x2 = cx + r_out * math.cos(angle)
        y2 = cy + r_out * math.sin(angle)
        lines.append('<line x1="{0:.2f}" y1="{1:.2f}" x2="{2:.2f}" y2="{3:.2f}" {4}/>'.format(x1, y1, x2, y2, _COMMON))
    return lines


ICONS = {
    "cashier": [
        '<rect x="4" y="9" width="16" height="10" rx="1" {0}/>'.format(_COMMON),
        '<rect x="8" y="4" width="8" height="5" rx="1" {0}/>'.format(_COMMON),
        '<line x1="7" y1="16" x2="9" y2="16" {0}/>'.format(_COMMON),
        '<line x1="15" y1="16" x2="17" y2="16" {0}/>'.format(_COMMON),
    ],
    "tables": [
        '<rect x="3" y="6" width="18" height="3" rx="0.5" {0}/>'.format(_COMMON),
        '<line x1="6" y1="9" x2="6" y2="20" {0}/>'.format(_COMMON),
        '<line x1="18" y1="9" x2="18" y2="20" {0}/>'.format(_COMMON),
    ],
    "playstation": [
        '<rect x="2" y="8" width="20" height="10" rx="5" {0}/>'.format(_COMMON),
        '<line x1="7" y1="11" x2="7" y2="15" {0}/>'.format(_COMMON),
        '<line x1="5" y1="13" x2="9" y2="13" {0}/>'.format(_COMMON),
        '<circle cx="16" cy="11.5" r="1" {0}/>'.format(_COMMON),
        '<circle cx="18.5" cy="14" r="1" {0}/>'.format(_COMMON),
    ],
    "menu": [
        '<path d="M5 8h12v6a6 6 0 0 1-6 6a6 6 0 0 1-6-6V8z" {0}/>'.format(_COMMON),
        '<path d="M17 10h2a2 2 0 0 1 0 4h-2" {0}/>'.format(_COMMON),
        '<line x1="9" y1="3" x2="9" y2="5" {0}/>'.format(_COMMON),
        '<line x1="13" y1="3" x2="13" y2="5" {0}/>'.format(_COMMON),
    ],
    "expenses": [
        '<path d="M6 3h12v17l-2-1.3L14 20l-2-1.3L10 20l-2-1.3L6 20V3z" {0}/>'.format(_COMMON),
        '<line x1="8.5" y1="8" x2="15.5" y2="8" {0}/>'.format(_COMMON),
        '<line x1="8.5" y1="12" x2="15.5" y2="12" {0}/>'.format(_COMMON),
    ],
    "reports": [
        '<line x1="4" y1="20" x2="20" y2="20" {0}/>'.format(_COMMON),
        '<rect x="6" y="13" width="3" height="7" {0}/>'.format(_COMMON),
        '<rect x="11" y="9" width="3" height="11" {0}/>'.format(_COMMON),
        '<rect x="16" y="5" width="3" height="15" {0}/>'.format(_COMMON),
    ],
    "settings": [
        '<circle cx="12" cy="12" r="3" {0}/>'.format(_COMMON),
    ] + _gear_teeth(12, 12, 6.5, 9.5, 8),
    "lock": [
        '<rect x="5" y="11" width="14" height="9" rx="1.5" {0}/>'.format(_COMMON),
        '<path d="M8 11V8a4 4 0 0 1 8 0v3" {0}/>'.format(_COMMON),
        '<circle cx="12" cy="15.5" r="1" {0}/>'.format(_COMMON),
    ],
    "search": [
        '<circle cx="10.5" cy="10.5" r="6.5" {0}/>'.format(_COMMON),
        '<line x1="15.5" y1="15.5" x2="20" y2="20" {0}/>'.format(_COMMON),
    ],
    "plus": [
        '<line x1="12" y1="5" x2="12" y2="19" {0}/>'.format(_COMMON),
        '<line x1="5" y1="12" x2="19" y2="12" {0}/>'.format(_COMMON),
    ],
    "minus": [
        '<line x1="5" y1="12" x2="19" y2="12" {0}/>'.format(_COMMON),
    ],
    "trash": [
        '<path d="M5 7h14" {0}/>'.format(_COMMON),
        '<path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" {0}/>'.format(_COMMON),
        '<path d="M7 7l1 13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1l1-13" {0}/>'.format(_COMMON),
        '<line x1="10" y1="11" x2="10" y2="17" {0}/>'.format(_COMMON),
        '<line x1="14" y1="11" x2="14" y2="17" {0}/>'.format(_COMMON),
    ],
    "check": [
        '<polyline points="5,13 10,18 19,6" {0}/>'.format(_COMMON),
    ],
    "warning": [
        '<path d="M12 3l10 18H2L12 3z" {0}/>'.format(_COMMON),
        '<line x1="12" y1="10" x2="12" y2="14" {0}/>'.format(_COMMON),
        '<line x1="12" y1="17" x2="12" y2="17.1" {0}/>'.format(_COMMON),
    ],
    "download": [
        '<path d="M12 3v12" {0}/>'.format(_COMMON),
        '<polyline points="7,11 12,16 17,11" {0}/>'.format(_COMMON),
        '<path d="M5 19h14" {0}/>'.format(_COMMON),
    ],
    "backup": [
        '<path d="M12 3v9" {0}/>'.format(_COMMON),
        '<polyline points="8,9 12,13 16,9" {0}/>'.format(_COMMON),
        '<path d="M4 14v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4" {0}/>'.format(_COMMON),
    ],
    "send": [
        '<path d="M3 11l18-8-8 18-2-7-8-3z" {0}/>'.format(_COMMON),
    ],
    "user": [
        '<circle cx="12" cy="8" r="4" {0}/>'.format(_COMMON),
        '<path d="M4 20c0-4.4 3.6-7 8-7s8 2.6 8 7" {0}/>'.format(_COMMON),
    ],
}


def icon_svg(name: str, stroke: str) -> str:
    body = "".join(ICONS[name]).format(S=stroke)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        'width="24" height="24">{0}</svg>'
    ).format(body)
