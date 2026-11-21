"""Response shapes captured from Kalshi's public API on 2026-11-21.

The tests build their inputs from these rather than from an assumed shape: note
the numbers arrive as STRINGS and the orderbook lists bids worst-first.
"""

SERIES = {
    "ticker": "KXHIGHLAX", "title": "Highest temperature in Los Angeles",
    "category": "Climate and Weather", "fee_type": "quadratic",
    "fee_multiplier": 1, "frequency": "daily",
}

MARKET = {
    "ticker": "KXHIGHLAX-26NOV22-T72", "event_ticker": "KXHIGHLAX-26NOV22",
    "title": "Will the maximum temperature be >72° on Nov 22, 2026?",
    "yes_sub_title": "73° or above", "status": "active",
    "close_time": "2026-11-23T09:00:00Z",
    "yes_bid_dollars": "0.0100", "yes_ask_dollars": "0.0200",
    "no_bid_dollars": "0.9800", "no_ask_dollars": "0.9900",
    "yes_bid_size_fp": "132.00", "yes_ask_size_fp": "1390.06",
    "last_price_dollars": "0.0200", "volume_24h_fp": "208.00",
    "open_interest_fp": "208.00",
}

ORDERBOOK = {
    "no_dollars": [["0.9600", "183.00"], ["0.9700", "71.01"], ["0.9800", "1390.06"]],
    "yes_dollars": [["0.0100", "132.00"]],
}
