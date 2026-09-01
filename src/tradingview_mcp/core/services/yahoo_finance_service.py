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

Two parallel APIs:
  ``get_price(symbol)``         — sync, used by internal callers that aren't
                                  running inside an event loop
  ``get_price_async(symbol)``   — async, used by FastMCP tool handlers so
                                  multiple parallel quote requests don't
                                  block the event loop
"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from typing import Optional

import httpx

from tradingview_mcp.core.services.proxy_manager import (
    build_opener_with_proxy,
    get_httpx_proxy,
)

_TIMEOUT = 12
_UA = "tradingview-mcp/0.5.0"
_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"


# ─── Shared helpers ─────────────────────────────────────────────────────────


# 5 days (not 2): when the newest session has no trades yet its close is None,
# and a 2-day window then leaves only ONE usable close — too few to derive a
# previous close, which used to fall back to chartPreviousClose (the same bar)
# and report a 0% or nonsense move.
_QUOTE_RANGE = "5d"

# How far meta.regularMarketTime may lag the newest candle before the whole
# quote block is treated as stale. One day covers normal intraday lag.
_STALE_QUOTE_SECONDS = 86_400


def _quote_url(symbol: str) -> str:
    return f"{_BASE}/{symbol}?interval=1d&range={_QUOTE_RANGE}"


def _valid_closes(chart_result: dict) -> list[float]:
    """Daily closes with empty (None) candles dropped, oldest first."""
    try:
        closes = chart_result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        return [c for c in closes if c is not None]
    except (IndexError, TypeError, KeyError):
        return []


def _quote_is_stale(chart_result: dict) -> bool:
    """True when meta's quote block is older than the candle data.

    Yahoo serves a frozen quote block for some venues while the chart series
    stays current — observed on every EGX (.CA) symbol, where
    ``regularMarketTime`` sits at 2024-07-23 and ``regularMarketPrice`` is the
    price from that day. Comparing that against a current close produced
    fictional moves (CCAP.CA: 2.2 vs a real 5.75 close, reported as -61%).
    ``regularMarketDayHigh``/``Low``/``Volume`` are None in that state too.
    """
    meta = chart_result.get("meta", {})
    if meta.get("regularMarketPrice") is None:
        return True
    quote_ts = meta.get("regularMarketTime")
    if quote_ts is None:
        return True
    timestamps = chart_result.get("timestamp") or []
    if not timestamps:
        return False
    try:
        return quote_ts < timestamps[-1] - _STALE_QUOTE_SECONDS
    except TypeError:
        return True


def _get_previous_close(chart_result: dict) -> Optional[float]:
    """Extract the previous trading day's close from candle data.

    The meta fields are unreliable: 'previousClose' is often None and
    'chartPreviousClose' returns the chart range's start price rather than
    yesterday's close.
    """
    closes = _valid_closes(chart_result)
    if len(closes) >= 2:
        return closes[-2]
    meta = chart_result.get("meta", {})
    return meta.get("previousClose") or meta.get("chartPreviousClose")


def _format_quote(symbol: str, chart_result: dict) -> dict:
    """Pure formatter — no I/O. Shared by sync and async paths."""
    meta = chart_result.get("meta", {})
    closes = _valid_closes(chart_result)
    stale = _quote_is_stale(chart_result)

    if stale and closes:
        # Fall back to the candle series, which stays current. Candle closes
        # arrive as float32 (6.900000095367432) — round so callers and the
        # wire format show a real price.
        price = round(closes[-1], 4)
        prev_close = round(closes[-2], 4) if len(closes) >= 2 else None
        price_source = "candle_close"
    else:
        price = meta.get("regularMarketPrice")
        prev_close = _get_previous_close(chart_result)
        if isinstance(prev_close, float):
            prev_close = round(prev_close, 4)
        price_source = "quote"

    # A missing previous close stays None — substituting the current price
    # silently reported change=0.0, indistinguishable from a genuinely flat
    # session.
    chg = round(price - prev_close, 4) if (price and prev_close) else None
    chg_pct = (
        round((price - prev_close) / prev_close * 100, 2)
        if (price and prev_close and prev_close != 0)
        else None
    )

    return {
        "symbol": symbol.upper(),
        "price": price,
        "previous_close": prev_close,
        "change": chg,
        "change_pct": chg_pct,
        "currency": meta.get("currency", "USD"),
        "exchange": meta.get("exchangeName", ""),
        "market_state": meta.get("marketState", ""),  # REGULAR, PRE, POST, CLOSED
        "52w_high": meta.get("fiftyTwoWeekHigh"),
        "52w_low": meta.get("fiftyTwoWeekLow"),
        "price_source": price_source,
        "quote_stale": stale,
        "source": "Yahoo Finance",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ─── Sync API (kept for internal callers) ───────────────────────────────────


def _fetch_quote(symbol: str) -> dict:
    """Fetch raw Yahoo Finance chart result for a symbol (meta + indicators)."""
    req = urllib.request.Request(_quote_url(symbol), headers={"User-Agent": _UA})
    opener = build_opener_with_proxy(_UA)
    with opener.open(req, timeout=_TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["chart"]["result"][0]


def get_price(symbol: str) -> dict:
    """Get real-time price data for any Yahoo Finance symbol (sync)."""
    try:
        return _format_quote(symbol, _fetch_quote(symbol))
    except Exception as e:
        return {"symbol": symbol.upper(), "error": str(e), "source": "Yahoo Finance"}


def get_prices_bulk(symbols: list[str]) -> list[dict]:
    """Get prices for multiple symbols at once (sync, sequential)."""
    return [get_price(sym) for sym in symbols]


def get_market_snapshot() -> dict:
    """Get a snapshot of major market indices and crypto prices (sync)."""
    groups = {
        "indices": ["^GSPC", "^DJI", "^IXIC", "^VIX"],
        "crypto": ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD"],
        "fx": ["EURUSD=X", "GBPUSD=X", "JPYUSD=X"],
        "etfs": ["SPY", "QQQ", "GLD"],
    }

    result: dict = {}
    for group, syms in groups.items():
        result[group] = []
        for sym in syms:
            data = get_price(sym)
            if "error" not in data:
                result[group].append({
                    "symbol": data["symbol"],
                    "price": data["price"],
                    "change_pct": data["change_pct"],
                    "currency": data["currency"],
                })

    result["timestamp"] = datetime.now(timezone.utc).isoformat()
    return result


# ─── Async API (used by FastMCP tool handlers) ──────────────────────────────


async def _afetch_quote(client: httpx.AsyncClient, symbol: str) -> dict:
    resp = await client.get(_quote_url(symbol))
    resp.raise_for_status()
    data = resp.json()
    return data["chart"]["result"][0]


async def get_price_async(symbol: str) -> dict:
    """Get real-time price (async). Mirrors :func:`get_price` shape exactly.

    Uses ``httpx.AsyncClient`` so concurrent FastMCP calls (e.g. several
    parallel ``yahoo_price`` requests) actually run in parallel instead of
    blocking the event loop.
    """
    proxy = get_httpx_proxy()
    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT,
            headers={"User-Agent": _UA},
            proxy=proxy,
        ) as client:
            chart_result = await _afetch_quote(client, symbol)
        return _format_quote(symbol, chart_result)
    except Exception as e:
        return {"symbol": symbol.upper(), "error": str(e), "source": "Yahoo Finance"}


async def get_market_snapshot_async() -> dict:
    """Async snapshot — fans all 14 symbols out in parallel via one client."""
    import asyncio

    groups = {
        "indices": ["^GSPC", "^DJI", "^IXIC", "^VIX"],
        "crypto": ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD"],
        "fx": ["EURUSD=X", "GBPUSD=X", "JPYUSD=X"],
        "etfs": ["SPY", "QQQ", "GLD"],
    }
    flat_symbols = [s for syms in groups.values() for s in syms]
    proxy = get_httpx_proxy()

    async with httpx.AsyncClient(
        timeout=_TIMEOUT,
        headers={"User-Agent": _UA},
        proxy=proxy,
    ) as client:
        async def _one(sym: str) -> dict:
            try:
                return _format_quote(sym, await _afetch_quote(client, sym))
            except Exception as e:
                return {"symbol": sym.upper(), "error": str(e), "source": "Yahoo Finance"}

        results = await asyncio.gather(*(_one(s) for s in flat_symbols))

    by_symbol = {r["symbol"]: r for r in results}
    out: dict = {}
    for group, syms in groups.items():
        out[group] = []
        for sym in syms:
            data = by_symbol.get(sym.upper())
            if data and "error" not in data:
                out[group].append({
                    "symbol": data["symbol"],
                    "price": data["price"],
                    "change_pct": data["change_pct"],
                    "currency": data["currency"],
                })
    out["timestamp"] = datetime.now(timezone.utc).isoformat()
    return out
