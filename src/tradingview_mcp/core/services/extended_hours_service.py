"""
Extended-hours price service for US stocks.

Why this exists: a paying customer (US Army officer who trades on mobile)
asked "can you pull real-time after/extended hours?". He's tracking stocks
in the pre-market 4:00-9:30am ET and after-hours 4:00-8:00pm ET sessions
where earnings reactions and overnight news land.

Yahoo Finance's chart endpoint with `includePrePost=true` returns 1-minute
candles for the full extended trading day. We walk through the candles,
classify each by which session window it falls in (using the response's
`currentTradingPeriod` boundaries), and report the most recent valid close
for each session.

Behavior across the trading day:
- Pre-market session (4:00-9:30am ET): pre_market populated, post null
- Regular session (9:30am-4:00pm ET): pre + regular populated, post null
- Post-market session (4:00-8:00pm ET): all three populated
- Overnight / weekend: returns whatever's most recent in each window

Returns `null` for whichever session has no data — Claude can quote that
back to the user as "no after-hours print yet" rather than guessing.
"""
from __future__ import annotations

import json
import time
import urllib.request
import urllib.error
from typing import Optional

_TIMEOUT = 12
_UA = "tradingview-mcp/0.8.1"
_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"


def _change_pct(price: Optional[float], reference: Optional[float]) -> Optional[float]:
    """Percentage change from reference to price; None if either is missing."""
    if price is None or reference is None or reference == 0:
        return None
    return round((price - reference) / reference * 100, 2)


def _fmt_time(ts: Optional[int]) -> Optional[str]:
    if ts is None:
        return None
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(ts))


def get_extended_hours_price(symbol: str) -> dict:
    """Fetch latest pre-market, regular-session, and post-market prices.

    Args:
        symbol: US stock symbol (e.g. AAPL, NVDA, SPY, ^GSPC).

    Returns:
        Dict with `pre_market`, `regular`, `post_market` blocks plus computed
        percentage changes. On upstream failure, returns `{symbol, error}`.
    """
    url = f"{_BASE}/{symbol}?interval=1m&range=1d&includePrePost=true"
    req = urllib.request.Request(
        url, headers={"User-Agent": _UA, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError) as e:
        return {"symbol": symbol.upper(), "error": f"{type(e).__name__}: {e}"}

    try:
        result = data["chart"]["result"][0]
        meta = result["meta"]
        period = meta["currentTradingPeriod"]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError) as e:
        return {"symbol": symbol.upper(), "error": f"unexpected response shape: {e}"}

    regular_start = period["regular"]["start"]
    regular_end = period["regular"]["end"]

    pre_price, pre_time = None, None
    regular_price_intraday, regular_time = None, None
    post_price, post_time = None, None

    for ts, c in zip(timestamps, closes):
        if c is None:
            continue
        if ts < regular_start:
            pre_price, pre_time = c, ts
        elif ts <= regular_end:
            regular_price_intraday, regular_time = c, ts
        else:
            post_price, post_time = c, ts

    # Prefer the meta `regularMarketPrice` (consolidated tape); fall back to
    # latest 1m candle if meta missing.
    regular_close = meta.get("regularMarketPrice") or regular_price_intraday
    previous_close = meta.get("previousClose") or meta.get("chartPreviousClose")

    out = {
        "symbol": symbol.upper(),
        "currency": meta.get("currency", "USD"),
        "exchange": meta.get("exchangeName"),
        "market_state": meta.get("marketState"),
        "previous_close": previous_close,
        "pre_market": None,
        "regular": None,
        "post_market": None,
        "source": "Yahoo Finance",
    }

    if pre_price is not None:
        out["pre_market"] = {
            "price": pre_price,
            "as_of_utc": _fmt_time(pre_time),
            "change_vs_previous_close_pct": _change_pct(pre_price, previous_close),
        }

    if regular_close is not None:
        out["regular"] = {
            "price": regular_close,
            "as_of_utc": _fmt_time(meta.get("regularMarketTime") or regular_time),
            "change_pct": _change_pct(regular_close, previous_close),
        }

    if post_price is not None:
        out["post_market"] = {
            "price": post_price,
            "as_of_utc": _fmt_time(post_time),
            "change_vs_regular_close_pct": _change_pct(post_price, regular_close),
        }

    return out
