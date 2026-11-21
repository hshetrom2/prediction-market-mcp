import io
import json
import urllib.error

import pytest

from pm_mcp import kalshi
from tests.fixtures import MARKET, ORDERBOOK, SERIES


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_returning(payload, seen=None):
    def _open(req, timeout=None):
        if seen is not None:
            seen.append(req.full_url)
        return FakeResp(json.dumps(payload).encode())
    return _open


def http_error(code):
    return urllib.error.HTTPError("u", code, "x", {}, None)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(kalshi.time, "sleep", lambda s: None)


@pytest.mark.parametrize("bad", ["", "../etc", "KX/..", "KX?x=1", "a b", "-KX", "K" * 81, None, 7])
def test_bad_tickers_never_reach_a_url(bad):
    with pytest.raises(ValueError):
        kalshi.check_ticker(bad)


def test_ticker_is_upper_cased():
    assert kalshi.check_ticker("kxhighlax-26nov22-t72") == "KXHIGHLAX-26NOV22-T72"


def test_get_builds_url_and_drops_none_params():
    seen = []
    kalshi._get("/markets", {"series_ticker": "KX", "status": None, "limit": 5},
                opener=opener_returning({}, seen))
    assert seen == [kalshi.BASE + "/markets?series_ticker=KX&limit=5"]


def test_404_is_not_retried():
    calls = []

    def _open(req, timeout=None):
        calls.append(1)
        raise http_error(404)

    with pytest.raises(kalshi.KalshiError, match="not found"):
        kalshi._get("/series/NOPE", opener=_open)
    assert len(calls) == 1


def test_5xx_is_retried_then_succeeds():
    calls = []

    def _open(req, timeout=None):
        calls.append(1)
        if len(calls) < 3:
            raise http_error(503)
        return FakeResp(b'{"ok": true}')

    assert kalshi._get("/x", opener=_open) == {"ok": True}
    assert len(calls) == 3


def test_gives_up_after_retries():
    def _open(req, timeout=None):
        raise http_error(500)

    with pytest.raises(kalshi.KalshiError, match="unreachable"):
        kalshi._get("/x", opener=_open, retries=2)


def test_series_markets_orderbook_unwrap(monkeypatch):
    monkeypatch.setattr(kalshi, "_get", lambda path, params=None: {"series": SERIES})
    assert kalshi.series("KXHIGHLAX")["fee_multiplier"] == 1

    monkeypatch.setattr(kalshi, "_get", lambda path, params=None: {"markets": [MARKET], "cursor": "abc"})
    rows, more = kalshi.markets("KXHIGHLAX", limit=1)
    assert rows == [MARKET] and more is True

    monkeypatch.setattr(kalshi, "_get", lambda path, params=None: {"markets": [], "cursor": ""})
    assert kalshi.markets("KXHIGHLAX") == ([], False)

    monkeypatch.setattr(kalshi, "_get", lambda path, params=None: {"orderbook_fp": ORDERBOOK})
    assert kalshi.orderbook("KXHIGHLAX-26NOV22-T72") == ORDERBOOK


def test_missing_payload_raises_instead_of_returning_empty(monkeypatch):
    monkeypatch.setattr(kalshi, "_get", lambda path, params=None: {})
    with pytest.raises(kalshi.KalshiError):
        kalshi.series("KXHIGHLAX")
    with pytest.raises(kalshi.KalshiError):
        kalshi.orderbook("KXHIGHLAX-26NOV22-T72")
