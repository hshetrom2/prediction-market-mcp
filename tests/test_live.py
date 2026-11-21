"""Hits Kalshi's public API. Run with: pytest -m live"""
import asyncio

import pytest
from mcp import Client

from pm_mcp.server import mcp

pytestmark = pytest.mark.live
SERIES = "KXHIGHLAX"


def ok(name, args):
    async def _run():
        async with Client(mcp) as c:
            return await c.call_tool(name, args)
    r = asyncio.run(_run())
    assert r.is_error is False, r.content
    return r.structured_content


def test_live_series_markets_orderbook_chain():
    fees = ok("kalshi_series_fees", {"series_ticker": SERIES})
    assert fees["ticker"] == SERIES and fees["fee_type"] and fees["fee_multiplier"] is not None

    mk = ok("kalshi_markets", {"series_ticker": SERIES, "limit": 3})
    assert mk["count"] >= 1, "no open markets in the probe series"
    m = mk["markets"][0]
    for k in ("yes_bid", "yes_ask"):
        assert m[k] is None or 0.0 <= m[k] <= 1.0, (k, m[k])

    ob = ok("kalshi_orderbook", {"ticker": m["ticker"], "depth": 3})
    for side in ("yes_bids", "no_bids"):
        prices = [lvl["price"] for lvl in ob[side]]
        assert prices == sorted(prices, reverse=True), f"{side} not best-first"
        assert all(0.0 < p < 1.0 for p in prices)


def test_live_unknown_series_is_a_tool_error():
    async def _run():
        async with Client(mcp) as c:
            return await c.call_tool("kalshi_series_fees", {"series_ticker": "ZZZNOTASERIES"})
    assert asyncio.run(_run()).is_error is True
