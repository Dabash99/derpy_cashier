"""Pure PlayStation pricing math -- no DB, no Qt, so every rule has a
plain unit test. Everything is integer math on piasters/minutes/seconds.
"""
from __future__ import annotations

from derby.core.utils.money import ps_session_price_piasters


def actual_minutes_from_seconds(elapsed_seconds: int) -> int:
    """ceil(elapsed_seconds / 60), at least 1. A negative elapsed (clock
    moved backwards) is treated as 0 by the caller before this is reached."""
    elapsed_seconds = max(0, elapsed_seconds)
    minutes = (elapsed_seconds + 59) // 60
    return max(1, minutes)


def billed_minutes_for_session(prior_billed_total: int, this_actual_minutes: int, min_minutes: int, is_final: bool) -> int:
    """The per-visit minimum (settings.ps_min_minutes) is applied once per
    order, only at a FINAL stop, by topping up the billed minutes of that
    one final session so the visit's cumulative billed total reaches the
    minimum. A mode switch never applies it (billed = actual). Once a
    previous final stop already reached the minimum, prior_billed_total
    alone satisfies the first branch below, so it is never reapplied."""
    if not is_final:
        return this_actual_minutes
    if prior_billed_total + this_actual_minutes >= min_minutes:
        return this_actual_minutes
    return min_minutes - prior_billed_total


def ps_price(hourly_rate_piasters: int, billed_minutes: int, step_piasters: int) -> int:
    """price = hourly_rate x billed_minutes / 60, rounded to the nearest step."""
    return ps_session_price_piasters(hourly_rate_piasters, billed_minutes, step_piasters)
