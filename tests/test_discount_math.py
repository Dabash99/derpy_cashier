from __future__ import annotations

import pytest

from derby.features.pos.discount_math import compute_discount_piasters


def test_fixed_discount_is_passthrough():
    assert compute_discount_piasters("fixed", 500, 10000) == 500


def test_percent_discount_half_up():
    # 10% of 7500 = 750 exactly
    assert compute_discount_piasters("percent", 10, 7500) == 750
    # 10% of 2501 = 250.1 -> rounds to 250
    assert compute_discount_piasters("percent", 10, 2501) == 250
    # 50% of 2501 = 1250.5 -> rounds up to 1251 (half-up)
    assert compute_discount_piasters("percent", 50, 2501) == 1251


def test_percent_out_of_range_rejected():
    with pytest.raises(ValueError):
        compute_discount_piasters("percent", 0, 1000)
    with pytest.raises(ValueError):
        compute_discount_piasters("percent", 101, 1000)


def test_unknown_kind_rejected():
    with pytest.raises(ValueError):
        compute_discount_piasters("bogus", 10, 1000)
