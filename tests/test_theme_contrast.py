"""WCAG 2.1 contrast check for every text/background color pair actually
used by derby/core/theme/stylesheet.py (sourced from tokens.py, never
hardcoded hex here, so this stays in sync if a token changes).

Every pair below is normal-size text in the real stylesheet (even the
bold ones: 15-16px bold is still under WCAG's 18.66px/14pt-bold "large
text" threshold), so AA's 4.5:1 applies uniformly -- no pair needs the
weaker 3:1 large-text allowance. Disabled-state colors are WCAG-exempt
(disabled content has no contrast requirement) and are deliberately not
included here.
"""
from __future__ import annotations

import pytest

from derby.core.theme import tokens

AA_NORMAL_TEXT_MIN_RATIO = 4.5


def _srgb_to_linear(channel_255: int) -> float:
    c = channel_255 / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _relative_luminance(hex_color: str) -> float:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    r, g, b = _srgb_to_linear(r), _srgb_to_linear(g), _srgb_to_linear(b)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(color_a: str, color_b: str) -> float:
    l1, l2 = _relative_luminance(color_a), _relative_luminance(color_b)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


# (label, foreground token, background token) -- every text-on-background
# combination the stylesheet actually renders.
TEXT_BACKGROUND_PAIRS = [
    ("body text on content background", tokens.TEXT_PRIMARY, tokens.BACKGROUND),
    ("body text on card surface", tokens.TEXT_PRIMARY, tokens.SURFACE),
    ("subtitle/secondary text on content background", tokens.TEXT_SECONDARY, tokens.BACKGROUND),
    ("subtitle/secondary text on card surface", tokens.TEXT_SECONDARY, tokens.SURFACE),
    ("sidebar/header text on sidebar background", tokens.TEXT_ON_DARK, tokens.SIDEBAR_BACKGROUND),
    ("sidebar muted text on sidebar background", tokens.TEXT_ON_DARK_MUTED, tokens.SIDEBAR_BACKGROUND),
    ("sidebar text on active sidebar item", tokens.TEXT_ON_DARK, tokens.SIDEBAR_ACTIVE),
    ("active sidebar indicator text on active sidebar item", tokens.AMBER_500, tokens.SIDEBAR_ACTIVE),
    ("primary button text on primary fill", tokens.PRIMARY_TEXT, tokens.PRIMARY_FILL),
    ("secondary button text on secondary fill", tokens.SECONDARY_TEXT, tokens.SECONDARY_FILL),
    ("danger button text on danger fill", tokens.WHITE, tokens.DANGER),
    ("error label on content background", tokens.DANGER, tokens.BACKGROUND),
    ("error label on card surface", tokens.DANGER, tokens.SURFACE),
    ("badge text on badge fill", tokens.TEXT_ON_AMBER, tokens.AMBER_100),
    ("ghost button text on content background", tokens.GHOST_TEXT, tokens.BACKGROUND),
]


@pytest.mark.parametrize("label,fg,bg", TEXT_BACKGROUND_PAIRS, ids=[p[0] for p in TEXT_BACKGROUND_PAIRS])
def test_text_background_pair_meets_wcag_aa(label, fg, bg):
    ratio = contrast_ratio(fg, bg)
    assert ratio >= AA_NORMAL_TEXT_MIN_RATIO, "{0}: {1} on {2} is only {3:.2f}:1 (need >= {4}:1)".format(
        label, fg, bg, ratio, AA_NORMAL_TEXT_MIN_RATIO
    )


def test_amber_is_never_used_as_text_on_cream_or_white():
    """Amber-on-cream/white fails contrast outright (see docs/BRAND.md) --
    amber is a fill/accent on light backgrounds, never a text color
    there. Guard the actual failure, not just note it."""
    assert contrast_ratio(tokens.AMBER_500, tokens.BACKGROUND) < AA_NORMAL_TEXT_MIN_RATIO
    assert contrast_ratio(tokens.AMBER_500, tokens.SURFACE) < AA_NORMAL_TEXT_MIN_RATIO


def test_primary_button_text_is_black_not_white_or_cream():
    """Amber fill always pairs with black text -- white/cream on amber
    fails contrast (docs/BRAND.md)."""
    assert tokens.PRIMARY_TEXT == tokens.JET_BLACK
    assert contrast_ratio(tokens.WHITE, tokens.PRIMARY_FILL) < AA_NORMAL_TEXT_MIN_RATIO
    assert contrast_ratio(tokens.CREAM, tokens.PRIMARY_FILL) < AA_NORMAL_TEXT_MIN_RATIO
