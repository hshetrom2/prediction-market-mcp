"""The tools as an agent sees them: through an MCP client, not by direct call."""
import asyncio

import pytest
from mcp import Client

from pm_mcp import kalshi
from pm_mcp.server import mcp
from tests.fixtures import MARKET, ORDERBOOK, SERIES

EXPECTED = {"kalshi_fee", "kalshi_series_fees", "kalshi_markets", "kalshi_orderbook",
            "two_leg_position", "price_two_leg"}


def call(name, args):
    async def _run():
        async with Client(mcp) as c:
            return await c.call_tool(name, args)
    return asyncio.run(_run())


def ok(name, args):
    r = call(name, args)
    assert r.is_error is False, r.content
    return r.structured_content


def test_exactly_six_tools_all_marked_read_only():
    async def _run():
        async with Client(mcp) as c:
            return (await c.list_tools()).tools
    tools = asyncio.run(_run())
    assert {t.name for t in tools} == EXPECTED
    for t in tools:
        assert t.annotations.read_only_hint is True, t.name
        assert t.description, t.name


def test_kalshi_fee_matches_hand_computed_points():
    assert ok("kalshi_fee", {"contracts": 100, "price": 0.5})["fee_usd"] == 1.75
    one = ok("kalshi_fee", {"contracts": 1, "price": 0.5})
    assert one["fee_usd"] == 0.02 and one["fee_cents_per_contract"] == 2.0
    assert ok("kalshi_fee", {"contracts": 100, "price": 0.5, "multiplier": 0})["fee_usd"] == 0.0


def test_kalshi_fee_maker_branches_are_labelled():
    free = ok("kalshi_fee", {"contracts": 100, "price": 0.5, "maker": True})
    assert free["fee_usd"] == 0.0 and "no maker fee" in free["note"]
    paid = ok("kalshi_fee", {"contracts": 100, "price": 0.5, "maker": True,
                             "fee_type": "quadratic_with_maker_fees"})
    assert paid["fee_usd"] == 0.44 and "unverified" in paid["note"]


@pytest.mark.parametrize("args", [
    {"contracts": 100, "price": 52},          # cents, not dollars
    {"contracts": 0, "price": 0.5},
    {"contracts": 100, "price": -0.1},
])
def test_kalshi_fee_rejects_bad_input(args):
    assert call("kalshi_fee", args).is_error is True


def test_two_leg_position_partial_second_leg():
    out = ok("two_leg_position", {
        "fills": [{"side": "YES", "qty": 100, "price": 0.42},
                  {"side": "NO", "qty": 40, "price": 0.50}],
        "target_edge_per_share": 0.02,
    })
    assert out["pnl_if_yes_usd"] == 38.0 and out["pnl_if_no_usd"] == -22.0
    assert out["is_locked"] is False
    assert out["unhedged_qty"] == 60 and out["unhedged_side"] == "YES"
    assert out["side_to_buy"] == "NO"
    assert out["max_price_to_finish_hedge"] == 0.6


def test_two_leg_position_balanced_and_locked():
    out = ok("two_leg_position", {"fills": [{"side": "YES", "qty": 100, "price": 0.42},
                                            {"side": "NO", "qty": 100, "price": 0.53}]})
    assert out["is_locked"] is True and out["locked_pnl_usd"] == 5.0
    assert out["unhedged_side"] is None and out["side_to_buy"] is None
    assert out["max_price_to_finish_hedge"] is None


def test_two_leg_position_rejects_empty_and_cent_prices():
    assert call("two_leg_position", {"fills": []}).is_error is True
    assert call("two_leg_position",
                {"fills": [{"side": "YES", "qty": 1, "price": 42}]}).is_error is True


def test_price_two_leg_nets_both_fees_and_warns():
    out = ok("price_two_leg", {"yes_price": 0.42, "no_price": 0.53, "contracts": 100,
                               "other_venue_fee_bps": 100})
    # gross 5.00; kalshi 0.07*100*0.42*0.58 = 1.7052 -> 1.71; other 1% of 0.53*100 = 0.53
    assert out["gross_usd"] == 5.0 and out["kalshi_fee_usd"] == 1.71
    assert out["other_venue_fee_usd"] == 0.53 and out["net_usd"] == 2.76
    assert out["positive_after_fees"] is True and "IDENTICAL" in out["warning"]


def test_price_two_leg_gross_positive_but_fees_kill_it():
    out = ok("price_two_leg", {"yes_price": 0.50, "no_price": 0.49, "contracts": 100})
    assert out["gross_usd"] == 1.0 and out["net_usd"] == -0.75
    assert out["positive_after_fees"] is False


def test_series_fees_from_real_shape(monkeypatch):
    monkeypatch.setattr(kalshi, "series", lambda t: SERIES)
    out = ok("kalshi_series_fees", {"series_ticker": "KXHIGHLAX"})
    assert out["fee_type"] == "quadratic" and out["fee_multiplier"] == 1.0
    assert out["charges_maker_fee"] is False


def test_markets_converts_string_prices_and_reports_truncation(monkeypatch):
    monkeypatch.setattr(kalshi, "markets", lambda t, status="open", limit=25: ([MARKET], True))
    out = ok("kalshi_markets", {"series_ticker": "kxhighlax", "limit": 1})
    assert out["series_ticker"] == "KXHIGHLAX" and out["count"] == 1 and out["truncated"] is True
    m = out["markets"][0]
    assert (m["yes_bid"], m["yes_ask"], m["no_bid"], m["no_ask"]) == (0.01, 0.02, 0.98, 0.99)
    assert m["yes_ask_size"] == 1390.06 and m["yes_means"] == "73° or above"


def test_markets_empty_series_is_empty_not_error(monkeypatch):
    monkeypatch.setattr(kalshi, "markets", lambda t, status="open", limit=25: ([], False))
    out = ok("kalshi_markets", {"series_ticker": "KXHIGHLAX"})
    assert out == {"series_ticker": "KXHIGHLAX", "count": 0, "truncated": False, "markets": []}


def test_orderbook_is_best_first_with_implied_asks(monkeypatch):
    monkeypatch.setattr(kalshi, "orderbook", lambda t, depth=10: ORDERBOOK)
    out = ok("kalshi_orderbook", {"ticker": "KXHIGHLAX-26NOV22-T72", "depth": 2})
    assert out["no_bids"] == [{"price": 0.98, "size": 1390.06}, {"price": 0.97, "size": 71.01}]
    assert out["best_yes_bid"] == 0.01 and out["best_no_bid"] == 0.98
    assert out["implied_yes_ask"] == 0.02 and out["implied_no_ask"] == 0.99
    assert out["empty"] is False


def test_orderbook_empty_gives_nulls_not_zeros(monkeypatch):
    monkeypatch.setattr(kalshi, "orderbook", lambda t, depth=10: {"yes_dollars": [], "no_dollars": []})
    out = ok("kalshi_orderbook", {"ticker": "KXHIGHLAX-26NOV22-T72"})
    assert out["empty"] is True
    assert out["best_yes_bid"] is None and out["implied_yes_ask"] is None


def test_one_sided_orderbook(monkeypatch):
    monkeypatch.setattr(kalshi, "orderbook", lambda t, depth=10: {"yes_dollars": [["0.4000", "5.00"]]})
    out = ok("kalshi_orderbook", {"ticker": "KXHIGHLAX-26NOV22-T72"})
    assert out["best_yes_bid"] == 0.4 and out["implied_no_ask"] == 0.6
    assert out["best_no_bid"] is None and out["implied_yes_ask"] is None and out["empty"] is False


def test_bad_ticker_and_upstream_failure_surface_as_tool_errors(monkeypatch):
    bad = call("kalshi_series_fees", {"series_ticker": "../../etc"})
    assert bad.is_error is True and "invalid ticker" in bad.content[0].text

    def boom(t):
        raise kalshi.KalshiError("not found: /series/NOPE")
    monkeypatch.setattr(kalshi, "series", boom)
    r = call("kalshi_series_fees", {"series_ticker": "NOPE"})
    assert r.is_error is True and "not found" in r.content[0].text
