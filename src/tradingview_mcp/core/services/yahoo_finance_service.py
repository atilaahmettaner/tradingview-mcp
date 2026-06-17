"""
Yahoo Finance Price Service via Webshare Rotating Proxy.

Provides real-time quotes for stocks, ETFs, crypto pairs, indices
using the Yahoo Finance Chart API (no API key required).

Works with any symbol Yahoo Finance supports:
  Stocks:  AAPL, TSLA, MSFT, NVDA, GOOGL
  Crypto:  BTC-USD, ETH-USD, SOL-USD, BNB-USD
  ETFs:    SPY, QQQ, VTI
  Indices: ^GSPC (S&P500), ^DJI (Dow), ^IXIC (NASDAQ)
  FX:      EURUSD=X, GBPUSD=X
  Turkish: THYAO.IS, SASA.IS
"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from typing import Optional

from tradingview_mcp.core.services.proxy_manager import build_opener_with_proxy

_TIMEOUT = 12
_UA = "tradingview-mcp/0.5.0"
_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"


def _fetch_quote(symbol: str) -> dict:
    """Fetch raw Yahoo Finance chart result for a symbol (meta + indicators)."""
    url = f"{_BASE}/{symbol}?interval=1d&range=2d"
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    opener = build_opener_with_proxy(_UA)
    with opener.open(req, timeout=_TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["chart"]["result"][0]


def _get_previous_close(chart_result: dict) -> Optional[float]:
    """Extract previous trading day's close from candle data.

    The meta fields 'previousClose' and 'chartPreviousClose' are unreliable:
    - 'previousClose' is often None
    - 'chartPreviousClose' returns the chart range start price, not yesterday's close

    Instead, we use the actual close prices from the 2-day candle data.
    With range=2d, indicators.quote[0].close gives [prev_day_close, today_close].
    """
    try:
        closes = chart_result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        # Filter out None values (can happen for incomplete candles)
        valid_closes = [c for c in closes if c is not None]
        if len(valid_closes) >= 2:
            return valid_closes[-2]
    except (IndexError, TypeError, KeyError):
        pass
    # Fallback to meta fields if candle data unavailable
    meta = chart_result.get("meta", {})
    return meta.get("previousClose") or meta.get("chartPreviousClose")


def get_price(symbol: str) -> dict:
    """
    Get real-time price data for any Yahoo Finance symbol.

    Args:
        symbol: Yahoo Finance symbol (e.g. "AAPL", "BTC-USD", "THYAO.IS", "^GSPC")

    Returns:
        dict with price, change, change_pct, currency, exchange, market_state
    """
    try:
        chart_result = _fetch_quote(symbol)
        meta = chart_result.get("meta", {})
        price      = meta.get("regularMarketPrice")
        prev_close = _get_previous_close(chart_result) or price
        chg        = round(price - prev_close, 4) if (price and prev_close) else None
        chg_pct    = round((price - prev_close) / prev_close * 100, 2) if (price and prev_close and prev_close != 0) else None

        return {
            "symbol":        symbol.upper(),
            "price":         price,
            "previous_close": prev_close,
            "change":        chg,
            "change_pct":    chg_pct,
            "currency":      meta.get("currency", "USD"),
            "exchange":      meta.get("exchangeName", ""),
            "market_state":  meta.get("marketState", ""),  # REGULAR, PRE, POST, CLOSED
            "52w_high":      meta.get("fiftyTwoWeekHigh"),
            "52w_low":       meta.get("fiftyTwoWeekLow"),
            "source":        "Yahoo Finance",
            "timestamp":     datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        return {"symbol": symbol.upper(), "error": str(e), "source": "Yahoo Finance"}


def get_prices_bulk(symbols: list[str]) -> list[dict]:
    """
    Get prices for multiple symbols at once.

    Args:
        symbols: List of Yahoo Finance symbols

    Returns:
        List of price dicts
    """
    results = []
    for sym in symbols:
        results.append(get_price(sym))
    return results


from tradingview_mcp.core.utils.save_utils import save_result_to_json


def get_market_snapshot() -> dict:
    """
    Get a snapshot of major market indices and crypto prices.

    Returns:
        Dict with stocks (S&P500, NASDAQ, Dow), crypto (BTC, ETH), and FX
    """
    groups = {
        "indices": ["^GSPC", "^DJI", "^IXIC", "^VIX"],
        "etfs":    ["SPY", "QQQ", "GLD", "SLV", "ARKK", "SOXX"],
        "fx":      ["USDJPY=X", "EURUSD=X", "GBPUSD=X"],
        "crypto":  ["BTC-USD", "ETH-USD"],
    }

    result = {}
    for group, syms in groups.items():
        result[group] = []
        for sym in syms:
            data = get_price(sym)
            if "error" not in data:
                result[group].append({
                    "symbol":     data["symbol"],
                    "price":      data["price"],
                    "change_pct": data["change_pct"],
                    "currency":   data["currency"],
                })

    result["timestamp"] = datetime.now(timezone.utc).isoformat()
    save_result_to_json(result, "snapshot", "market")
    return result
