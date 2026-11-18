"""Pure pricing math -- no DB, no Qt. Examples straight from the spec."""
from __future__ import annotations

from derby.features.playstation.pricing import (
    actual_minutes_from_seconds,
    billed_minutes_for_session,
    ps_price,
)


def test_ps_price_examples_from_spec():
    assert ps_price(4000, 37, 500) == 2500  # 40 EGP/h x 37 min -> 24.67 EGP -> 25 EGP
    assert ps_price(2200, 60, 500) == 2000  # 22 EGP stays 20 (half-up rounds down here)
    assert ps_price(3000, 45, 500) == 2500  # 30 EGP/h x 45 min -> 22.5 EGP -> 25 EGP (half-up)
    assert ps_price(4000, 30, 500) == 2000  # 40 EGP/h x 10 min, topped up to the 30-min minimum


def test_ps_price_rounding_step_changes():
    assert ps_price(6000, 37, 100) == 3700  # step = 1 EGP -> exact minute-rate price
    assert ps_price(6000, 37, 1000) == 4000  # step = 10 EGP


def test_actual_minutes_ceils_and_has_a_floor_of_one():
    assert actual_minutes_from_seconds(0) == 1
    assert actual_minutes_from_seconds(59) == 1
    assert actual_minutes_from_seconds(60) == 1
    assert actual_minutes_from_seconds(61) == 2
    assert actual_minutes_from_seconds(36 * 60 + 1) == 37  # 36m01s -> 37
    assert actual_minutes_from_seconds(5 * 3600) == 300  # 5 hours


def test_actual_minutes_never_negative_from_a_backwards_clock():
    assert actual_minutes_from_seconds(-500) == 1


def test_mode_switch_never_applies_the_minimum():
    assert billed_minutes_for_session(0, 10, 30, is_final=False) == 10


def test_final_stop_tops_up_to_the_minimum():
    assert billed_minutes_for_session(0, 10, 30, is_final=True) == 30


def test_visit_already_over_minimum_bills_actual_only():
    # 10 single (switch, no minimum) then 50 multi (final): cumulative 60 >= 30.
    assert billed_minutes_for_session(10, 50, 30, is_final=True) == 50


def test_minimum_not_reapplied_after_a_prior_final_stop_already_reached_it():
    # First final stop already billed 30 total. A later session's final
    # stop should never top up again.
    assert billed_minutes_for_session(30, 5, 30, is_final=True) == 5
