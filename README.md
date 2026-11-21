# prediction-market-mcp

An MCP server that gives an AI agent the tools to reason about binary prediction
markets: exact Kalshi fee math, live public market data, and two-sided position
accounting.

**Read-only by construction.** The server issues only GET requests against
Kalshi's public endpoints and takes no credentials. An agent connected to it can
look, price and reason. It cannot place, change or cancel an order.

## Tools

| Tool | Network | What it answers |
|---|---|---|
| `kalshi_fee` | none | What does this order cost in fees, in dollars and per contract? |
| `kalshi_series_fees` | live | What fee type and multiplier does this series actually charge? |
| `kalshi_markets` | live | What is open in this series, and where is top of book? |
| `kalshi_orderbook` | live | What is resting on each side, and what ask does that imply? |
| `two_leg_position` | none | Given these fills, what is my P&L under each outcome, am I locked, and what is the most the second leg may pay? |
| `price_two_leg` | none | Does YES here plus NO there clear both fee schedules? |

All prices are dollars per contract between 0 and 1. Passing `52` for 52 cents is
rejected by input validation rather than silently producing a wrong fee.

## Why these tools

Fees decide most prediction-market questions, and a language model will happily
guess them. Kalshi's taker fee is `ceil_cents(0.07 * multiplier * C * P * (1 - P))`:
quadratic in price, rounded up per order, with a per-series multiplier. Three
things follow that an agent gets wrong without a tool:

- As a share of payout the fee is roughly 8x cheaper at 3 cents than at 50 cents.
- The round-up is a fixed cost, so a 1-lot at 50 cents pays 2% of payout while a
  100-lot pays 1.75%.
- The multiplier is per series. Assuming 1.0 is wrong for a meaningful share of
  the exchange.

## Design choices

- **Truncation is reported, never hidden.** `kalshi_markets` returns
  `truncated: true` when the server had more pages, so a short list is not
  mistaken for the whole series.
- **Empty is distinguishable from missing.** An empty orderbook returns
  `empty: true` with `null` best prices, not zeros.
- **Tickers are validated before they reach a URL.**
- **Known unknowns are in the output.** The maker-fee coefficient has not been
  reconciled against a real fill, and `price_two_leg` cannot check that two
  venues resolve on identical criteria. Both tools say so in their result.

## Install and run

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/prediction-market-mcp        # serves over stdio
```

Claude Code:

```bash
claude mcp add prediction-market -- /absolute/path/to/.venv/bin/prediction-market-mcp
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "prediction-market": {
      "command": "/absolute/path/to/.venv/bin/prediction-market-mcp"
    }
  }
}
```

## Tests

```bash
.venv/bin/pytest            # offline: fee conversions, position math, protocol round-trip
.venv/bin/pytest -m live    # also hits Kalshi's public API
```

The offline suite starts the real server as a subprocess and talks to it over
stdio with an MCP client, so the tool schemas and results are tested as an agent
would see them.
