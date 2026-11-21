"""Two-sided position math for a binary market.

Units, stated once:
  price = dollars per share, strictly between 0 and 1
  qty   = shares; a winning share pays exactly $1.00, a losing share $0
  fee   = dollars per fill
"""

from dataclasses import dataclass

PAYOUT = 1.0


@dataclass(frozen=True)
class Fill:
    side: str      # "YES" or "NO"
    qty: float
    price: float
    fee: float = 0.0

    def __post_init__(self):
        if self.side not in ("YES", "NO"):
            raise ValueError(f"side must be 'YES' or 'NO', got {self.side!r}")
        if self.qty <= 0:
            raise ValueError("fill qty must be positive")
        if not 0.0 < self.price < 1.0:
            raise ValueError(
                f"price must be DOLLARS per share between 0 and 1, got {self.price!r}"
            )
        if self.fee < 0:
            raise ValueError("fee cannot be negative")


class Position:
    """Built only from fills, never from what an order response claimed."""

    def __init__(self, fills=()):
        self.fills = list(fills)

    def qty(self, side):
        return sum(f.qty for f in self.fills if f.side == side)

    def cost(self, side):
        return sum(f.qty * f.price + f.fee for f in self.fills if f.side == side)

    def avg_cost(self, side):
        q = self.qty(side)
        return self.cost(side) / q if q else None

    def total_cost(self):
        return self.cost("YES") + self.cost("NO")

    def pnl_if(self, winner):
        return self.qty(winner) * PAYOUT - self.total_cost()

    def locked_pnl(self):
        """Worst case across both outcomes. Positive means genuinely locked."""
        return min(self.pnl_if("YES"), self.pnl_if("NO"))

    def leading_side(self):
        y, n = self.qty("YES"), self.qty("NO")
        if abs(y - n) < 1e-9:
            return None
        return "YES" if y > n else "NO"

    def unhedged_qty(self):
        return abs(self.qty("YES") - self.qty("NO"))


def second_leg_cap(pos, target_edge_per_share=0.0, fee_per_share=0.0):
    """Highest price the lagging side may pay to finish the hedge.

    After buying n = unhedged shares at price p both sides hold Q shares, and the
    locked profit is  Q - (total_cost + n * (p + fee_per_share)).
    Requiring at least target_edge_per_share * Q and solving for p:

        p <= (Q * (1 - target) - total_cost) / n - fee_per_share

    Returns None when the position is balanced, empty, or no price inside (0, 1)
    can meet the target.
    """
    lead = pos.leading_side()
    if lead is None:
        return None
    q_lead = pos.qty(lead)
    n = pos.unhedged_qty()
    cap = (q_lead * (PAYOUT - target_edge_per_share) - pos.total_cost()) / n - fee_per_share
    if cap <= 0.0:
        return None
    return min(cap, 0.99)
