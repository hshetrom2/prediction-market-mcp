"""Fee conversions asserted at hand-computed points, not at downstream outcomes."""
from decimal import Decimal

import pytest

from pm_mcp.fees import maker_fee_usd, taker_fee_usd


def test_taker_at_the_money_100_lot():
    # 0.07 * 100 * 0.5 * 0.5 = 1.75 exactly
    assert taker_fee_usd(100, 0.50) == Decimal("1.75")


def test_taker_rounds_up_per_order():
    # 0.07 * 1 * 0.5 * 0.5 = 0.0175 -> 2 cents
    assert taker_fee_usd(1, 0.50) == Decimal("0.02")


def test_taker_tail_price():
    # 0.07 * 100 * 0.03 * 0.97 = 0.2037 -> 21 cents
    assert taker_fee_usd(100, 0.03) == Decimal("0.21")


def test_taker_is_symmetric_in_price():
    assert taker_fee_usd(100, 0.30) == taker_fee_usd(100, 0.70)


def test_multiplier_scales_and_zero_means_free():
    # 0.07 * 0.5 * 100 * 0.25 = 0.875 -> 88 cents
    assert taker_fee_usd(100, 0.50, 0.5) == Decimal("0.88")
    assert taker_fee_usd(100, 0.50, 0) == Decimal("0.00")


def test_boundary_prices_cost_nothing():
    assert taker_fee_usd(100, 0) == Decimal("0.00")
    assert taker_fee_usd(100, 1) == Decimal("0.00")


def test_maker_free_unless_series_charges_it():
    assert maker_fee_usd(100, 0.50) == Decimal("0.00")
    # 0.0175 * 100 * 0.25 = 0.4375 -> 44 cents
    assert maker_fee_usd(100, 0.50, 1, "quadratic_with_maker_fees") == Decimal("0.44")


@pytest.mark.parametrize("bad", [52, 1.01, -0.1])
def test_price_in_cents_or_out_of_range_is_rejected(bad):
    with pytest.raises(ValueError, match="DOLLARS"):
        taker_fee_usd(100, bad)


def test_negative_contracts_and_multiplier_rejected():
    with pytest.raises(ValueError):
        taker_fee_usd(-1, 0.5)
    with pytest.raises(ValueError):
        taker_fee_usd(1, 0.5, -1)
