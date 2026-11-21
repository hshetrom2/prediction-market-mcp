"""Start the real server as a subprocess and talk to it over stdio."""
import asyncio
import sys

from mcp import Client, StdioServerParameters


def test_server_speaks_mcp_over_stdio():
    params = StdioServerParameters(command=sys.executable, args=["-m", "pm_mcp.server"])

    async def _run():
        async with Client(params) as c:
            tools = (await c.list_tools()).tools
            r = await c.call_tool("kalshi_fee", {"contracts": 100, "price": 0.5})
            return len(tools), r.is_error, r.structured_content["fee_usd"]

    assert asyncio.run(_run()) == (6, False, 1.75)
