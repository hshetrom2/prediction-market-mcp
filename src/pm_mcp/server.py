"""MCP server exposing prediction-market tools to an AI agent.

Read-only by construction: the only network calls are GETs against Kalshi's
public endpoints, and no tool takes or stores a credential. An agent using this
server can look, price and reason; it cannot trade.

Run over stdio:   prediction-market-mcp      (or: python -m pm_mcp.server)
"""

from decimal import Decimal
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from . import kalshi
from .fees import FEE_TYPE_WITH_MAKER, maker_fee_usd, taker_fee_usd
from .position import Fill, Position, second_leg_cap

mcp = MCPServer(
    "prediction-market-tools",
    version="0.1.0",
    instructions=(
        "Tools for reasoning about binary prediction markets. All prices are in "
        "DOLLARS per contract between 0 and 1 (52 cents is 0.52). Every tool is "
        "read-only; none can place or cancel an order. Fees on Kalshi are set per "
        "series: call kalshi_series_fees before kalshi_fee instead of assuming a "
        "multiplier of 1."
    ),
)

MAKER_NOTE = (
    "Maker coefficient 0.0175 is unverified against a real fill; treat the maker "
    "fee as an estimate."
)
# Every tool only reads. PURE tools touch nothing outside the process; LIVE tools
# GET from Kalshi's public API.
PURE = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
LIVE = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)

BASIS_NOTE = (
    "This assumes both legs resolve on IDENTICAL criteria. Different settlement "
    "sources or cut-off times make it a spread bet, not a lock; that is not "
    "checked here."
)


def _num(v):
    """Kalshi sends numbers as strings ('0.0200', '132.00'). None stays None."""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _money(d: Decimal) -> float:
    return float(d)


def _live(fn, *args, **kwargs):
    """Run a Kalshi call, turning expected failures into messages the agent can read.

    Without this the SDK treats a 404 or a bad ticker as a crash and tells the
    agent only "Error executing tool", which gives it nothing to correct.
    """
    try:
        return fn(*args, **kwargs)
    except (kalshi.KalshiError, ValueError) as e:
        raise ToolError(str(e)) from e


# ------------------------------------------------------------------ pure tools

@mcp.tool(annotations=PURE)
def kalshi_fee(
    contracts: int = Field(description="Number of contracts in ONE order", ge=1, le=1_000_000),
    price: float = Field(description="Price in DOLLARS per contract, 0 to 1. 52 cents is 0.52, not 52", ge=0, le=1),
    multiplier: float = Field(default=1.0, description="Series fee_multiplier from kalshi_series_fees", ge=0, le=10),
    maker: bool = Field(default=False, description="True for a resting (maker) order"),
    fee_type: str = Field(default="quadratic", description="Series fee_type from kalshi_series_fees"),
) -> dict[str, Any]:
    """Kalshi trading fee for one order, in dollars, plus what it costs per contract.

    The fee rounds UP to a whole cent per order, so small orders pay proportionally
    more. Positions held to settlement pay no exit fee.
    """
    fee = (maker_fee_usd(contracts, price, multiplier, fee_type) if maker
           else taker_fee_usd(contracts, price, multiplier))
    per_contract_cents = float(fee) / contracts * 100
    out = {
        "fee_usd": _money(fee),
        "fee_cents_per_contract": round(per_contract_cents, 4),
        "fee_pct_of_payout": round(per_contract_cents, 4),  # payout is $1, so cents == pct
        "min_edge_cents_to_break_even_held_to_settlement": round(per_contract_cents, 4),
        "inputs": {"contracts": contracts, "price": price, "multiplier": multiplier,
                   "maker": maker, "fee_type": fee_type},
    }
    if maker:
        out["note"] = (MAKER_NOTE if fee_type == FEE_TYPE_WITH_MAKER
                       else "This series fee_type charges no maker fee.")
    return out


class FillIn(BaseModel):
    side: Literal["YES", "NO"] = Field(description="Which outcome was bought")
    qty: float = Field(gt=0, description="Shares filled")
    price: float = Field(gt=0, lt=1, description="Fill price in dollars per share, 0 to 1")
    fee: float = Field(default=0.0, ge=0, description="Fee paid on this fill, dollars")


@mcp.tool(annotations=PURE)
def two_leg_position(
    fills: list[FillIn] = Field(description="Every fill so far, both sides, including partial fills", min_length=1, max_length=500),
    target_edge_per_share: float = Field(default=0.0, ge=0, lt=1, description="Dollars of locked profit wanted per hedged share"),
    second_leg_fee_per_share: float = Field(default=0.0, ge=0, lt=1, description="Fee per share on the remaining hedge, dollars"),
) -> dict[str, Any]:
    """State of a two-sided (YES/NO) position built from fills.

    Returns average cost per side, profit or loss under EACH outcome, whether the
    position is actually locked, how many shares are unhedged, and the highest
    price the lagging side may pay to finish the hedge at the target edge.
    """
    pos = Position(Fill(f.side, f.qty, f.price, f.fee) for f in fills)
    lead = pos.leading_side()
    cap = second_leg_cap(pos, target_edge_per_share, second_leg_fee_per_share)
    locked = pos.locked_pnl()
    return {
        "yes": {"qty": pos.qty("YES"), "avg_cost": pos.avg_cost("YES")},
        "no": {"qty": pos.qty("NO"), "avg_cost": pos.avg_cost("NO")},
        "total_cost_usd": round(pos.total_cost(), 6),
        "pnl_if_yes_usd": round(pos.pnl_if("YES"), 6),
        "pnl_if_no_usd": round(pos.pnl_if("NO"), 6),
        "locked_pnl_usd": round(locked, 6),
        "is_locked": locked > 0,
        "unhedged_qty": pos.unhedged_qty(),
        "unhedged_side": lead,
        "side_to_buy": None if lead is None else ("NO" if lead == "YES" else "YES"),
        "max_price_to_finish_hedge": None if cap is None else round(cap, 6),
        "hedge_possible_at_target": cap is not None,
    }


@mcp.tool(annotations=PURE)
def price_two_leg(
    yes_price: float = Field(gt=0, lt=1, description="Ask for YES on Kalshi, dollars"),
    no_price: float = Field(gt=0, lt=1, description="Ask for NO on the other venue, dollars"),
    contracts: int = Field(default=100, ge=1, le=1_000_000),
    kalshi_multiplier: float = Field(default=1.0, ge=0, le=10, description="Series fee_multiplier for the Kalshi leg"),
    other_venue_fee_bps: float = Field(default=0.0, ge=0, le=1000, description="Taker fee on the other venue in basis points of price"),
) -> dict[str, Any]:
    """Net result of buying YES on Kalshi and NO elsewhere, after both fees.

    Exactly one leg pays $1 per contract, so the gross is 1 - yes_price - no_price.
    """
    k_fee = float(taker_fee_usd(contracts, yes_price, kalshi_multiplier))
    o_fee = other_venue_fee_bps / 10_000.0 * no_price * contracts
    gross = (1.0 - yes_price - no_price) * contracts
    net = gross - k_fee - o_fee
    return {
        "gross_usd": round(gross, 4),
        "kalshi_fee_usd": round(k_fee, 4),
        "other_venue_fee_usd": round(o_fee, 4),
        "net_usd": round(net, 4),
        "net_cents_per_contract": round(net / contracts * 100, 4),
        "positive_after_fees": net > 0,
        "warning": BASIS_NOTE,
    }


# ------------------------------------------------------------------ live tools

@mcp.tool(annotations=LIVE)
def kalshi_series_fees(
    series_ticker: str = Field(description="Kalshi series ticker, e.g. KXHIGHLAX"),
) -> dict[str, Any]:
    """Live fee settings for one Kalshi series: fee_type and fee_multiplier.

    Fees are per series, not global. Use these values in kalshi_fee.
    """
    rec = _live(kalshi.series, series_ticker)
    return {
        "ticker": rec.get("ticker"),
        "title": rec.get("title"),
        "category": rec.get("category"),
        "frequency": rec.get("frequency"),
        "fee_type": rec.get("fee_type"),
        "fee_multiplier": _num(rec.get("fee_multiplier")),
        "charges_maker_fee": rec.get("fee_type") == FEE_TYPE_WITH_MAKER,
    }


def _market_row(m):
    return {
        "ticker": m.get("ticker"),
        "title": m.get("title"),
        "yes_means": m.get("yes_sub_title"),
        "status": m.get("status"),
        "close_time": m.get("close_time"),
        "yes_bid": _num(m.get("yes_bid_dollars")),
        "yes_ask": _num(m.get("yes_ask_dollars")),
        "no_bid": _num(m.get("no_bid_dollars")),
        "no_ask": _num(m.get("no_ask_dollars")),
        "yes_bid_size": _num(m.get("yes_bid_size_fp")),
        "yes_ask_size": _num(m.get("yes_ask_size_fp")),
        "last_price": _num(m.get("last_price_dollars")),
        "volume_24h": _num(m.get("volume_24h_fp")),
        "open_interest": _num(m.get("open_interest_fp")),
    }


@mcp.tool(annotations=LIVE)
def kalshi_markets(
    series_ticker: str = Field(description="Kalshi series ticker, e.g. KXHIGHLAX"),
    limit: int = Field(default=25, ge=1, le=100, description="Max markets to return"),
) -> dict[str, Any]:
    """Open markets in one Kalshi series with live top of book. Prices in dollars."""
    rows, more = _live(kalshi.markets, series_ticker, status="open", limit=limit)
    return {
        "series_ticker": series_ticker.upper(),
        "count": len(rows),
        "truncated": more,
        "markets": [_market_row(m) for m in rows],
    }


def _levels(raw, depth):
    """Kalshi lists bids worst-first; return best-first as price/size pairs."""
    out = []
    for lvl in reversed(raw or []):
        price, size = _num(lvl[0]), _num(lvl[1])
        if price is not None and size is not None:
            out.append({"price": price, "size": size})
    return out[:depth]


@mcp.tool(annotations=LIVE)
def kalshi_orderbook(
    ticker: str = Field(description="Kalshi market ticker, e.g. KXHIGHLAX-26NOV22-T72"),
    depth: int = Field(default=5, ge=1, le=50, description="Price levels per side"),
) -> dict[str, Any]:
    """Live resting bids on both sides of one Kalshi market, best price first.

    Kalshi books hold bids only. The ask on one side is implied by the best bid on
    the other: yes_ask = 1 - best_no_bid.
    """
    book = _live(kalshi.orderbook, ticker, depth=depth)
    yes = _levels(book.get("yes_dollars"), depth)
    no = _levels(book.get("no_dollars"), depth)
    best_yes = yes[0]["price"] if yes else None
    best_no = no[0]["price"] if no else None
    return {
        "ticker": ticker.upper(),
        "yes_bids": yes,
        "no_bids": no,
        "best_yes_bid": best_yes,
        "best_no_bid": best_no,
        "implied_yes_ask": None if best_no is None else round(1.0 - best_no, 4),
        "implied_no_ask": None if best_yes is None else round(1.0 - best_yes, 4),
        "empty": not yes and not no,
    }


def main():
    mcp.run()


if __name__ == "__main__":
    main()
