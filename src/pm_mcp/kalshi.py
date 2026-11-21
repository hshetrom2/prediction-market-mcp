"""Minimal Kalshi PUBLIC-data client. Standard library only, read-only, no auth.

Nothing here can place, change or cancel an order: the module only issues GETs
against public endpoints and holds no credentials.
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.elections.kalshi.com/trade-api/v2"
UA = "prediction-market-mcp/0.1"

# Tickers go into the URL path, so they are validated before any request is built.
_TICKER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


class KalshiError(RuntimeError):
    pass


def check_ticker(ticker: str) -> str:
    if not isinstance(ticker, str) or not _TICKER.match(ticker):
        raise ValueError(
            f"invalid ticker {ticker!r}: letters, digits, '.', '_' and '-' only"
        )
    return ticker.upper()


def _get(path, params=None, timeout=15, retries=3, opener=urllib.request.urlopen):
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(
            {k: v for k, v in params.items() if v is not None}
        )
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with opener(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 404:
                raise KalshiError(f"not found: {path}") from e
            if e.code != 429 and e.code < 500:
                raise KalshiError(f"HTTP {e.code} from Kalshi on {path}") from e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last = e
        if attempt < retries - 1:
            time.sleep(min(2 ** attempt, 4))
    raise KalshiError(f"Kalshi unreachable on {path}: {last}")


def series(ticker):
    """One series record. Carries the per-series fee_type and fee_multiplier."""
    data = _get(f"/series/{check_ticker(ticker)}")
    rec = data.get("series")
    if not rec:
        raise KalshiError(f"no series record returned for {ticker}")
    return rec


def markets(series_ticker, status="open", limit=25):
    """One page of markets for a series, with top of book inline.

    Returns (markets, more) where `more` is True when the server had further
    pages, so a short list is never mistaken for a complete one.
    """
    data = _get("/markets", {
        "series_ticker": check_ticker(series_ticker),
        "status": status,
        "limit": limit,
    })
    return data.get("markets", []), bool(data.get("cursor"))


def orderbook(ticker, depth=10):
    """Resting bids on both sides of one market."""
    data = _get(f"/markets/{check_ticker(ticker)}/orderbook", {"depth": depth})
    book = data.get("orderbook_fp")
    if book is None:
        raise KalshiError(f"no orderbook returned for {ticker}")
    return book
