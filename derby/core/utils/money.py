"""Money is always an integer number of piasters (1 EGP = 100 piasters).

Floats must never be used for money — float rounding errors would eventually
make totals not add up. All arithmetic here is plain integer math.
"""
from __future__ import annotations

PIASTERS_PER_EGP = 100
DEFAULT_ROUNDING_STEP_PIASTERS = 500  # 5 EGP, the cafe's default PS rounding


def egp_to_piasters(egp: int) -> int:
    return egp * PIASTERS_PER_EGP


def piasters_to_plain_text(piasters: int) -> str:
    """Formats piasters as a plain "12.34" string -- no currency label, for
    pre-filling an editable price field or writing a CSV value."""
    sign = "-" if piasters < 0 else ""
    whole_piasters = abs(piasters)
    egp_part = whole_piasters // PIASTERS_PER_EGP
    fraction_part = whole_piasters % PIASTERS_PER_EGP
    return "{sign}{egp}.{fraction:02d}".format(sign=sign, egp=egp_part, fraction=fraction_part)


def format_egp(piasters: int) -> str:
    """Format piasters as an Arabic-friendly "12.34 ج.م" style string."""
    return "{0} ج.م".format(piasters_to_plain_text(piasters))


def parse_egp_input(text: str) -> int:
    """Parse a user-typed EGP amount (e.g. "12.5", "12,5", "12") to piasters.

    Raises ValueError on anything that isn't a plain non-negative number.
    """
    cleaned = text.strip().replace(",", ".")
    if not cleaned:
        raise ValueError("empty amount")
    if cleaned.count(".") > 1:
        raise ValueError("invalid amount")
    if "." in cleaned:
        egp_str, fraction_str = cleaned.split(".")
    else:
        egp_str, fraction_str = cleaned, ""
    egp_str = egp_str or "0"
    if not egp_str.isdigit() or (fraction_str and not fraction_str.isdigit()):
        raise ValueError("invalid amount")
    fraction_str = (fraction_str + "00")[:2]
    return int(egp_str) * PIASTERS_PER_EGP + int(fraction_str)


def round_to_nearest(piasters: int, step_piasters: int = DEFAULT_ROUNDING_STEP_PIASTERS) -> int:
    """Round to the nearest multiple of step_piasters, half rounds up.

    Pure integer math: e.g. 40 EGP/h x 37 min / 60 = 2466.67 piasters,
    rounds to the nearest 500 piasters (5 EGP) -> 2500 piasters (25 EGP).
    """
    if step_piasters <= 0:
        raise ValueError("step_piasters must be positive")
    quotient, remainder = divmod(piasters, step_piasters)
    if remainder * 2 >= step_piasters:
        quotient += 1
    return quotient * step_piasters


def ps_session_price_piasters(hourly_rate_piasters: int, minutes: int, step_piasters: int = DEFAULT_ROUNDING_STEP_PIASTERS) -> int:
    """price = hourly_rate x minutes / 60, rounded to the nearest step.

    Uses integer math throughout (scaled by 60) to avoid float error before
    the final rounding step.
    """
    exact_scaled_by_60 = hourly_rate_piasters * minutes  # == price_piasters * 60
    quotient, remainder = divmod(exact_scaled_by_60, 60)
    if remainder * 2 >= 60:
        quotient += 1
    return round_to_nearest(quotient, step_piasters)
