from __future__ import annotations
import os
from typing import Set

ALLOWED_TIMEFRAMES: Set[str] = {"5m", "15m", "1h", "4h", "1D", "1W", "1M"}
_TIMEFRAME_ALIASES = {
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1D",
    "1w": "1W",
    "1m": "1M",
}

# Exchanges that represent stock markets (not crypto)
STOCK_EXCHANGES: Set[str] = {
    "egx", "bist", "nasdaq", "nyse",
    "amex", "nysearca", "pcx",          # NYSE Arca / AMEX (ETFs: GDX, GLD, XLE, SPY, QQQ, etc.)
    "bursa", "myx", "klse", "ace", "leap",
    "hkex", "hk", "hsi",
    "asx",
    "sse", "szse", "chn",
    "twse", "tpex",
    "tadawul", "tasi",                  # Saudi Stock Exchange (Tadawul) — All Share Index (TASI)
}

EXCHANGE_SCREENER = {
    "all": "crypto",
    "huobi": "crypto",
    "kucoin": "crypto",
    "coinbase": "crypto",
    "gateio": "crypto",
    "binance": "crypto",
    "bitfinex": "crypto",
    "bitget": "crypto",
    "bybit": "crypto",
    "okx": "crypto",
    "mexc": "crypto",
    "bist": "turkey",
    # Egyptian Stock Market Support
    "egx": "egypt",
    "nasdaq": "america",
    # Malaysia Stock Market Support
    "bursa": "malaysia",
    "myx": "malaysia",
    "klse": "malaysia",
    "ace": "malaysia",      # ACE Market (Access, Certainty, Efficiency)
    "leap": "malaysia",     # LEAP Market (Leading Entrepreneur Accelerator Platform)
    # Hong Kong Stock Market Support
    "hkex": "hongkong",     # Hong Kong Exchange
    "hk": "hongkong",       # Hong Kong (alternate)
    "hsi": "hongkong",      # Hang Seng Index constituents
    "nyse": "america",
    # NYSE Arca / AMEX — ETFs (GDX, GLD, XLE, SPY, QQQ …) are listed here in TradingView
    "amex": "america",      # TradingView canonical prefix for NYSE Arca ETFs
    "nysearca": "america",  # alias: NYSE Arca (official name used by issuers)
    "pcx": "america",       # alias: Pacific Exchange (historical MIC code for NYSE Arca)
    "asx": "australia",     # Australian Securities Exchange
    # China A-Share Market Support
    "sse": "china",         # Shanghai Stock Exchange (上海证券交易所)
    "szse": "china",        # Shenzhen Stock Exchange (深圳证券交易所)
    "chn": "china",         # China A-shares (combined alias)
    # Taiwan Stock Market Support
    "twse": "taiwan",       # Taiwan Stock Exchange (臺灣證券交易所)
    "tpex": "taiwan",       # Taipei Exchange (櫃買中心, OTC market)
    # Saudi Stock Market (Tadawul) — TradingView scanner uses /ksa/
    "tadawul": "ksa",
    "tasi": "ksa",          # alias: Tadawul All Share Index
}

# Venues TradingView serves for single-symbol TA (tradingview-ta) but NOT via the
# scanner (tradingview-screener returns 0 rows for the "forex"/"cfd" markets).
# Kept SEPARATE from EXCHANGE_SCREENER on purpose: scanner / multi-timeframe paths
# read EXCHANGE_SCREENER through get_market_type(), so isolating these here means
# those paths keep their existing behaviour and never query an unsupported market.
_TA_ONLY_SCREENERS: dict = {
    # Forex (currency pairs): EUR/USD, GBP/USD, USD/TRY, USD/JPY …
    "oanda": "forex",
    "fx_idc": "forex",
    "fxcm": "forex",
    # CFD: spot metals (GOLD, SILVER), indices (DXY, SPX) …
    "tvc": "cfd",
    "capitalcom": "cfd",
}

# Map validated exchange identifiers to their canonical TradingView symbol prefix.
# TradingView uses "AMEX" as the prefix for all NYSE Arca / ETF listings; passing
# "NYSE:GDX" returns no data even though GDX trades on NYSE Arca.
_EXCHANGE_TV_PREFIX: dict = {
    "amex": "AMEX",
    "nysearca": "AMEX",
    "pcx": "AMEX",
    "nasdaq": "NASDAQ",
    "nyse": "NYSE",
    "egx": "EGX",
    "bist": "BIST",
    "bursa": "MYX",
    "myx": "MYX",
    "klse": "MYX",
    "ace": "MYX",
    "leap": "MYX",
    "hkex": "HKEX",
    "hk": "HKEX",
    "hsi": "HSI",
    "asx": "ASX",
    "sse": "SSE",
    "szse": "SZSE",
    "chn": "SSE",
    "twse": "TWSE",
    "tpex": "TPEX",
    "tadawul": "TADAWUL",
    "tasi": "TADAWUL",
}

_YAHOO_SYMBOL_ALIASES: dict = {
    "TAIEX": "^TWII",
    "TAIEX.TW": "^TWII",
    "^TWII": "^TWII",
    "TWSE:TAIEX": "^TWII",
    "TWSE:IX0001": "^TWII",
}

_TRADINGVIEW_SYMBOL_ALIASES: dict = {
    "TAIEX": "TWSE:IX0001",
    "TAIEX.TW": "TWSE:IX0001",
    "^TWII": "TWSE:IX0001",
    "IX0001": "TWSE:IX0001",
    "TWSE:TAIEX": "TWSE:IX0001",
    "TWSE:IX0001": "TWSE:IX0001",
    # Spot metals in forex-pair notation — unambiguous (no venue lists a stock or
    # token called "XAUUSD"/"XAGUSD"), so these always map to the TVC CFD feed.
    "XAUUSD": "TVC:GOLD",
    "XAGUSD": "TVC:SILVER",
    # Precious-metal FUTURES + spot notations. AIs read these off market_snapshot
    # (e.g. "COMEX GC1!") and then feed the futures ticker straight into analysis;
    # without an alias they resolved to KUCOIN:GC1! and 404'd. The "1!/2!"
    # continuous-futures and X..USD spot forms are unambiguous (no venue lists a
    # stock/token by these names), so they always map to the verified TVC CFD
    # feeds. USOIL/COPPER/NATGAS TVC symbols don't resolve, so those are
    # deliberately omitted rather than aliased to a dead feed.
    "GC1!": "TVC:GOLD", "GC2!": "TVC:GOLD", "MGC1!": "TVC:GOLD", "GCUSD": "TVC:GOLD",
    "SI1!": "TVC:SILVER", "SIL1!": "TVC:SILVER", "SIUSD": "TVC:SILVER",
    "PL1!": "TVC:PLATINUM", "XPTUSD": "TVC:PLATINUM",
    "PA1!": "TVC:PALLADIUM", "XPDUSD": "TVC:PALLADIUM",
}

# "Soft" commodity aliases: bare tickers that ALSO exist as real equities/indices
# (e.g. NYSE:GOLD is Barrick Gold Corp). normalize_tradingview_symbol() applies
# these ONLY when the caller is not targeting a stock exchange — so NYSE:GOLD keeps
# resolving to the equity, while a crypto/default context maps "gold" to spot gold.
_COMMODITY_SOFT_ALIASES: dict = {
    "GOLD": "TVC:GOLD",
    "XAU": "TVC:GOLD",
    "SILVER": "TVC:SILVER",
    "XAG": "TVC:SILVER",
    "DXY": "TVC:DXY",
}


def get_tv_exchange_prefix(exchange: str) -> str:
    """Return the TradingView symbol prefix for *exchange* (e.g. ``AMEX`` for ``nysearca``).

    Falls back to ``exchange.upper()`` for exchanges not in the explicit map so
    that crypto exchanges (KUCOIN, BINANCE, …) still work as before.
    """
    return _EXCHANGE_TV_PREFIX.get(exchange.strip().lower(), exchange.upper())


def normalize_yahoo_symbol(symbol: str) -> str:
    """Return a provider-specific Yahoo Finance symbol for common user aliases."""
    raw = (symbol or "").strip().upper()
    return _YAHOO_SYMBOL_ALIASES.get(raw, raw)


def normalize_tradingview_symbol(symbol: str, exchange: str) -> str:
    """Return a fully-qualified TradingView symbol, resolving common index aliases."""
    raw = (symbol or "").strip().upper()
    if raw in _TRADINGVIEW_SYMBOL_ALIASES:
        return _TRADINGVIEW_SYMBOL_ALIASES[raw]
    if ":" in raw:
        return raw
    # Soft commodity aliases collide with real equities (NYSE:GOLD = Barrick Gold),
    # so only apply them for non-stock venues; stock exchanges keep the literal.
    if raw in _COMMODITY_SOFT_ALIASES and not is_stock_exchange(exchange):
        return _COMMODITY_SOFT_ALIASES[raw]
    return f"{get_tv_exchange_prefix(exchange)}:{raw}"

# Get absolute path to coinlist directory relative to this module
# This file is at: src/tradingview_mcp/core/utils/validators.py
# We want: src/tradingview_mcp/coinlist/
_this_file = __file__
_utils_dir = os.path.dirname(_this_file)  # core/utils
_core_dir = os.path.dirname(_utils_dir)   # core  
_package_dir = os.path.dirname(_core_dir) # tradingview_mcp
COINLIST_DIR = os.path.join(_package_dir, 'coinlist')


def sanitize_timeframe(tf: str, default: str = "5m") -> str:
    if not tf:
        return default
    normalized = tf.strip().lower()
    return _TIMEFRAME_ALIASES.get(normalized, default)


def sanitize_exchange(ex: str, default: str = "kucoin") -> str:
    if not ex:
        return default
    exs = ex.strip().lower()
    if exs in EXCHANGE_SCREENER or exs in _TA_ONLY_SCREENERS:
        return exs
    return default


# Strict variants used at the MCP tool boundary. The sanitize_* pair silently
# substitutes the default on bad input — an LLM asking for KRAKEN got KUCOIN
# data with no indication anything was wrong. These raise instead, and the
# tool wrapper converts the exception to a typed error envelope the caller
# can self-correct from. Empty/None still means "use the default": callers
# that omitted the parameter never asked for a specific market.

def validate_timeframe(tf: str, default: str = "5m") -> str:
    from tradingview_mcp.core.errors import ErrorCode, ScreenerServiceError

    if not tf:
        return default
    normalized = tf.strip().lower()
    if normalized in _TIMEFRAME_ALIASES:
        return _TIMEFRAME_ALIASES[normalized]
    raise ScreenerServiceError(
        ErrorCode.INVALID_TIMEFRAME,
        f"Invalid timeframe {tf!r}.",
        valid_timeframes=sorted(ALLOWED_TIMEFRAMES),
        retryable=False,
    )


def validate_exchange(ex: str, default: str = "kucoin") -> str:
    from tradingview_mcp.core.errors import ErrorCode, ScreenerServiceError

    if not ex:
        return default
    exs = ex.strip().lower()
    if exs in EXCHANGE_SCREENER or exs in _TA_ONLY_SCREENERS:
        return exs
    raise ScreenerServiceError(
        ErrorCode.INVALID_EXCHANGE,
        f"Invalid exchange {ex!r}.",
        valid_exchanges=sorted({*EXCHANGE_SCREENER, *_TA_ONLY_SCREENERS}),
        retryable=False,
    )


def is_stock_exchange(exchange: str) -> bool:
    """Return True if the exchange is a stock market (not crypto)."""
    return exchange.strip().lower() in STOCK_EXCHANGES


def get_market_type(exchange: str) -> str:
    """Return the TradingView market type for screener queries."""
    return EXCHANGE_SCREENER.get(exchange.strip().lower(), "crypto")


def resolve_screener_for_symbol(full_symbol: str, exchange: str) -> str:
    """Pick the TradingView screener for an already-resolved symbol.

    A single venue can host assets needing *different* screeners
    (``OANDA:EURUSD`` → ``forex`` but ``OANDA:XAUUSD`` → ``cfd``), and symbol
    aliases can redirect to another venue (``XAUUSD`` → ``TVC:GOLD``). So the
    screener must follow the *final* symbol's prefix, not the exchange the
    caller originally passed. Falls back to the exchange's screener (then
    ``crypto``) when the symbol carries no explicit prefix.
    """
    prefix = (full_symbol.split(":", 1)[0] if ":" in full_symbol
              else (exchange or "")).strip().lower()
    return (EXCHANGE_SCREENER.get(prefix)
            or _TA_ONLY_SCREENERS.get(prefix)
            or "crypto")
