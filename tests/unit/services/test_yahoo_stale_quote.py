"""Regression tests for Yahoo's frozen quote block.

Yahoo serves a stale meta quote for some venues while the candle series stays
current. Observed 2026-08-28 on every EGX (.CA) symbol: ``regularMarketTime``
stuck at 2024-07-23 with ``regularMarketPrice`` from that day, while the daily
closes were current. Comparing the two produced fictional moves — CCAP.CA
reported price 2.2 against a real 5.75 close, i.e. "-61.74%".
"""
from __future__ import annotations

from tradingview_mcp.core.services.yahoo_finance_service import _format_quote

# 2024-07-23 20:00 UTC — the frozen timestamp Yahoo returns for EGX symbols.
STALE_TS = 1721764800
# Late-August 2026 daily bars.
FRESH_TS = [1756080000, 1756166400, 1756252800, 1756339200, 1756425600]


def _chart(closes, *, quote_price, quote_ts, timestamps=None):
    return {
        "meta": {
            "regularMarketPrice": quote_price,
            "regularMarketTime": quote_ts,
            "currency": "EGP",
            "chartPreviousClose": closes[0] if closes else None,
        },
        "timestamp": timestamps if timestamps is not None else FRESH_TS[: len(closes)],
        "indicators": {"quote": [{"close": closes}]},
    }


def test_stale_quote_falls_back_to_candle_closes():
    """CCAP.CA shape: 2024 quote price must not be compared to a 2026 close."""
    chart = _chart([5.60, 5.78, 5.71, 5.83, 5.75], quote_price=2.2, quote_ts=STALE_TS)
    q = _format_quote("CCAP.CA", chart)

    assert q["quote_stale"] is True
    assert q["price_source"] == "candle_close"
    assert q["price"] == 5.75                 # newest close, not the 2024 quote
    assert q["previous_close"] == 5.83
    assert q["change_pct"] == -1.37           # a real one-day move
    # The bug produced roughly -61%; anything near that is a regression.
    assert abs(q["change_pct"]) < 20


def test_stale_quote_with_empty_newest_candle():
    """Session with no trades yet: newest candle is None, older closes remain."""
    chart = _chart(
        [6.94, 6.99, 7.00, 6.97, 6.90, None],
        quote_price=1.635,
        quote_ts=STALE_TS,
        timestamps=FRESH_TS + [1756512000],
    )
    q = _format_quote("MENA.CA", chart)
    assert q["price"] == 6.90
    assert q["previous_close"] == 6.97
    assert abs(q["change_pct"]) < 5


def test_fresh_quote_is_trusted():
    """Normal venue: a current quote still drives price (intraday moves matter)."""
    fresh_ts = FRESH_TS[-1] + 3600
    chart = _chart([150.0, 152.5], quote_price=153.75, quote_ts=fresh_ts,
                   timestamps=FRESH_TS[:2])
    q = _format_quote("AAPL", chart)

    assert q["quote_stale"] is False
    assert q["price_source"] == "quote"
    assert q["price"] == 153.75               # live price, not the candle close
    assert q["previous_close"] == 150.0
    assert q["change_pct"] == 2.5


def test_missing_quote_price_uses_candles():
    chart = _chart([10.0, 10.5], quote_price=None, quote_ts=None)
    q = _format_quote("XYZ.CA", chart)
    assert q["quote_stale"] is True
    assert q["price"] == 10.5
    assert q["previous_close"] == 10.0


def test_single_close_leaves_change_none():
    """One usable close: report the price but never invent a change."""
    chart = _chart([5.75], quote_price=2.2, quote_ts=STALE_TS)
    q = _format_quote("CCAP.CA", chart)
    assert q["price"] == 5.75
    assert q["previous_close"] is None
    assert q["change"] is None
    assert q["change_pct"] is None
