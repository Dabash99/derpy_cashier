# Derby — Brand Identity

This is the fixed brand spec for Derby's visual identity. These are
decisions, not suggestions: colors, ratios, and logo rules here must not
be "improved" or re-balanced by whoever touches the theme next. Changes to
this file are a deliberate brand decision, not a drive-by styling fix.

## Asset inventory (as found, A0)

`assets/logo/` contains three files, none modified by the brand/UI refresh
work:

| File | Format | Size (px) | Notes |
|---|---|---|---|
| `Derby_Logo.svg` | SVG, viewBox 0 0 1254 1254 | vector | 6 color groups (see below), 34 `<path>` elements, no gradients, no `<text>`, no embedded fonts — safe to render with `QSvgRenderer` |
| `Derby Logo.png` | PNG, RGBA | 1254 x 1254 | has alpha channel (transparent background) |
| `Derby Café & PlayStation Logo.png` | PNG, RGB | 1254 x 1254 | no alpha channel (flat/opaque background) |

`Derby_Logo.svg` groups and fills (by `<g id="...">`):

| Group id | Fill |
|---|---|
| `black` | `#000000` |
| `blue` | `#016DDC` |
| `green` | `#01AB64` |
| `orange` | `#D68502` |
| `purple` | `#A908D6` |
| `red` | `#E63022` |

These are the *source* logo colors (hand-traced bezier paths, likely from
a vectorized raster). They are **not** the brand palette below — the
amber/gold used across the app UI is a separate, fixed token
(`#D98E04`), not the SVG's `orange` group. `tools/render_assets.py`
renders this SVG as-is for the full-color mark; solid-color variants
(all-black, all-cream, all-amber) are produced by re-coloring a flattened
copy at render time, never by hand-editing the original SVG.

The design-guidance skill `ui-ux-pro-max` was consulted for general
layout/contrast/spacing principles (not for colors or logo — those are
fixed here). Its React-Native-oriented component library was not used;
only the platform-agnostic rules applied: 4/8px spacing rhythm, 44px
minimum touch target, 4.5:1 contrast for normal text / 3:1 for large
text and icons, "don't convey state by color alone," one icon
stroke-weight per hierarchy level, and semantic (not raw hex) color
tokens throughout the stylesheet. These match the token/contrast-test
requirements below, so no conflicting guidance had to be resolved.

## Color palette (fixed)

| Name | Hex | Role |
|---|---|---|
| Jet Black | `#0F0F10` | sidebar/header background, secondary action fill, text on cream/amber |
| Amber Gold | `#D98E04` | primary action fill, active indicators, accents |
| Warm Vanilla / Cream | `#FAF6F0` | main content background |
| White | `#FFFFFF` | cards, surfaces on cream |

Usage ratio across a screen: **45% cream, 30% black, 15% amber, 10%
white.** This is a visual balance target, not a per-pixel budget — the
sidebar/header being black and the content area being cream is what
naturally produces it.

### Black shades (tints for dark surfaces / text hierarchy)

| Token | Hex |
|---|---|
| `black.900` | `#0F0F10` |
| `black.700` | `#292929` |
| `black.500` | `#454545` |
| `black.300` | `#777777` |
| `black.100` | `#B8B8BB` |

### Amber shades

| Token | Hex |
|---|---|
| `amber.900` | `#9C6200` |
| `amber.700` | `#B87900` |
| `amber.500` | `#D98E04` |
| `amber.300` | `#E9AD36` |
| `amber.100` | `#F5D18A` |

## Contrast rules (hard constraint, enforced by `tests/test_theme_contrast.py`)

- Normal text ≥ 4.5:1 against its background.
- Large text (headings, totals/prices/timers) and icons ≥ 3:1.
- **Amber-on-cream fails contrast and must never be used for text.**
  Amber is a fill/accent color on light backgrounds (with black text on
  top of it) and a *text* color only on black backgrounds.
- Amber as a primary button fill always pairs with **black** text, never
  white or cream (fails contrast on amber).
- Black as a secondary button is a solid fill with white/cream text.
- State must never be conveyed by color alone (e.g. table free/busy,
  success/danger) — pair color with an icon or label text too.

## Typography

- **Arabic UI text**: Cairo (already bundled under `assets/fonts/`),
  Regular/SemiBold/Bold weights.
- **Latin brand wordmark, numbers, big numeric displays (totals, prices,
  timers), and Latin headings**: Montserrat, Bold/SemiBold/Medium/Regular.
  Static (non-variable) weights only — variable fonts are unreliable on
  Windows 7.
- `QFont.setFamilies` fallback chain ensures Arabic text always falls back
  to Cairo even where Montserrat is requested first for a mixed label.
- Montserrat TTF files are **not fetched over the network** by any
  automated step (no network access is permitted in this app's build or
  runtime at all). If `assets/fonts/Montserrat-*.ttf` are absent,
  `derby/core/theme/fonts.py` degrades gracefully to Cairo/Qt's default
  Latin font rather than failing — see that module for exactly which
  files it looks for and where to place them by hand.

## Logo

- Golden coffee bean inside viewfinder brackets, "DERBY" wordmark,
  "CAFÉ & PLAYSTATION" subtitle, and a small symbols row (green triangle,
  red circle, blue cross, white square — a nod to the PlayStation corner).
- Variations: on cream, on black, on amber backgrounds, plus a
  transparent-background version for arbitrary placement.
- Minimum rendered width: **120px**. Never scale below that (illegible
  wordmark/subtitle).
- Icon-only mark (bean + brackets, no wordmark) is used for the window/
  taskbar icon and anywhere space is tight.
- Supporting brand elements (not part of the logo itself, used
  decoratively/as UI icons elsewhere): coffee cup, gamepad, headset, wifi
  icons; a coffee-bean pattern; a cream paper texture (used only, very
  subtly, behind the login screen — never at a contrast level that
  competes with the login form).

## Where generated assets live

- `assets/brand/` — PNG renders of the logo (full mark + icon-only mark,
  background variants, 1x/2x at the sizes the UI needs) and the hand-drawn
  line-icon set, pre-rendered to PNG. All committed; all generated by
  `tools/render_assets.py`, which is the **only** regeneration path.
  Shipped app code loads these PNGs via `QIcon`/`QPixmap` and never
  imports `QtSvg` at runtime — only `tools/` (a dev-time-only script) is
  allowed to use `QtSvg`.
- `assets/fonts/` — Cairo (already present) + Montserrat static weights
  (added by hand per the note above), with the Google Fonts OFL license
  text alongside.

## Design tokens

The numeric scales (spacing, radius, font sizes, control heights) that
back every screen's styling live in code, not here, so they can't drift
from what's actually applied: see `derby/core/theme/tokens.py`. This file
is the source of truth for *colors and brand rules*; `tokens.py` is the
source of truth for *how those colors and the rest of the scale get
consumed* by `derby/core/theme/stylesheet.py`.
