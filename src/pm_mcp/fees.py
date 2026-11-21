"""Kalshi fee model.

Formula (Kalshi published schedule):

    taker fee = ceil_cents( 0.07   * multiplier * C * P * (1 - P) )
    maker fee = ceil_cents( 0.0175 * multiplier * C * P * (1 - P) )   only when the
                series fee_type is "quadratic_with_maker_fees"; 0 otherwise

C = contracts, P = price in DOLLARS (0..1). The result rounds UP to the next whole
cent, per order.

Two consequences an agent should know before it reasons about edge:

1. As a fraction of the $1 payout the fee is far cheaper at the tails than at the
   money: 1.75% at P=0.50 vs about 0.20% at P=0.03.
2. The ceil-to-cent is a fixed cost: negligible on a 100-lot, brutal on a 1-lot.

`multiplier` and `fee_type` are per-SERIES fields. Read them from the series
record; never assume 1.0.

UNVERIFIED: the 0.0175 maker coefficient comes from public secondary sources and
has not been reconciled against a real fill. Treat maker fees as an estimate.
"""

from decimal import ROUND_CEILING, Decimal

TAKER_COEFF = Decimal("0.07")
MAKER_COEFF = Decimal("0.0175")  # UNVERIFIED - see module docstring
FEE_TYPE_WITH_MAKER = "quadratic_with_maker_fees"

_CENT = Decimal("0.01")


def _ceil_cents(amount: Decimal) -> Decimal:
    return amount.quantize(_CENT, rounding=ROUND_CEILING)


def _quadratic(coeff: Decimal, contracts, price, multiplier) -> Decimal:
    c = Decimal(str(contracts))
    p = Decimal(str(price))
    m = Decimal(str(multiplier))
    if not (0 <= p <= 1):
        raise ValueError(
            f"price must be in DOLLARS between 0 and 1, got {price!r} "
            "(52 cents is 0.52, not 52)"
        )
    if c < 0:
        raise ValueError(f"contracts must be non-negative, got {contracts!r}")
    if m < 0:
        raise ValueError(f"multiplier must be non-negative, got {multiplier!r}")
    if m == 0 or c == 0:
        return Decimal("0.00")
    return _ceil_cents(coeff * m * c * p * (Decimal("1") - p))


def taker_fee_usd(contracts, price, multiplier=1) -> Decimal:
    """Taker fee in dollars for ONE order of `contracts` at `price` (dollars)."""
    return _quadratic(TAKER_COEFF, contracts, price, multiplier)


def maker_fee_usd(contracts, price, multiplier=1, fee_type="quadratic") -> Decimal:
    """Maker fee in dollars. Zero unless the series charges maker fees."""
    if fee_type != FEE_TYPE_WITH_MAKER:
        return Decimal("0.00")
    return _quadratic(MAKER_COEFF, contracts, price, multiplier)
