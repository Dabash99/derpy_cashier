from __future__ import annotations

from derby.core.utils.money import (
    format_egp,
    parse_egp_input,
    ps_session_price_piasters,
    round_to_nearest,
)


def test_format_egp_basic():
    assert format_egp(1234) == "12.34 ج.م"
    assert format_egp(100) == "1.00 ج.م"
    assert format_egp(0) == "0.00 ج.م"


def test_parse_egp_input_basic():
    assert parse_egp_input("12.34") == 1234
    assert parse_egp_input("12") == 1200
    assert parse_egp_input("12,5") == 1250
    assert parse_egp_input(".5") == 50


def test_round_to_nearest_half_up_500_step():
    # 24.67 EGP (2467 piasters) -> nearest 500 piasters (5 EGP) -> 2500 (25 EGP)
    assert round_to_nearest(2467, 500) == 2500
    # 22 EGP (2200 piasters) -> nearest 500 -> 2000 (20 EGP)
    assert round_to_nearest(2200, 500) == 2000
    # exact half rounds up: 250 piasters is exactly half of 500 -> rounds up to 500
    assert round_to_nearest(250, 500) == 500
    assert round_to_nearest(249, 500) == 0
    assert round_to_nearest(0, 500) == 0


def test_ps_session_price_example_from_spec():
    # 40 EGP/hour x 37 minutes = 24.666... EGP -> rounds to 25 EGP = 2500 piasters
    assert ps_session_price_piasters(4000, 37) == 2500
