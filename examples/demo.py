"""Drive the server the way an agent would: start it over stdio, list its tools,
then chain live data into the fee and position tools.

Run:  .venv/bin/python examples/demo.py [SERIES_TICKER]
"""
import asyncio
import json
import sys

from mcp import Client, StdioServerParameters

SERIES = sys.argv[1] if len(sys.argv) > 1 else "KXHIGHLAX"


def show(label, result):
    print(f"\n> {label}")
    if result.is_error:
        print("  ERROR:", result.content[0].text)
        return None
    print("  " + json.dumps(result.structured_content, indent=2).replace("\n", "\n  "))
    return result.structured_content


async def main():
    params = StdioServerParameters(command=sys.executable, args=["-m", "pm_mcp.server"])
    async with Client(params) as c:
        tools = (await c.list_tools()).tools
        print("Tools:", ", ".join(t.name for t in tools))

        fees = show(f"kalshi_series_fees({SERIES})",
                    await c.call_tool("kalshi_series_fees", {"series_ticker": SERIES}))
        mk = show(f"kalshi_markets({SERIES}, limit=1)",
                  await c.call_tool("kalshi_markets", {"series_ticker": SERIES, "limit": 1}))
        if fees and mk and mk["markets"]:
            m = mk["markets"][0]
            show(f"kalshi_orderbook({m['ticker']}, depth=2)",
                 await c.call_tool("kalshi_orderbook", {"ticker": m["ticker"], "depth": 2}))
            if m["yes_ask"] and 0 < m["yes_ask"] < 1:
                show(f"kalshi_fee(100 contracts at the live ask {m['yes_ask']})",
                     await c.call_tool("kalshi_fee", {
                         "contracts": 100, "price": m["yes_ask"],
                         "multiplier": fees["fee_multiplier"], "fee_type": fees["fee_type"]}))

        show("two_leg_position(100 YES at 0.42, 40 NO at 0.50, target 2c)",
             await c.call_tool("two_leg_position", {
                 "fills": [{"side": "YES", "qty": 100, "price": 0.42},
                           {"side": "NO", "qty": 40, "price": 0.50}],
                 "target_edge_per_share": 0.02}))
        show("kalshi_series_fees(ZZZNOTASERIES)  <- an error the agent can read",
             await c.call_tool("kalshi_series_fees", {"series_ticker": "ZZZNOTASERIES"}))


asyncio.run(main())
