from __future__ import annotations
import os
from typing import Set

ALLOWED_TIMEFRAMES: Set[str] = {"5m", "15m", "30m", "1h", "4h", "1D", "1W", "1M"}
_TIMEFRAME_ALIASES = {
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1D",
    "1w": "1W",
    "1m": "1M",
}

# Exchanges that represent stock markets (not crypto)
STOCK_EXCHANGES: Set[str] = {"egx", "bist", "nasdaq", "nyse", "bursa", "myx", "klse", "ace", "leap", "hkex", "hk", "hsi", "asx"}

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
    "asx": "australia",     # Australian Securities Exchange
}

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
    return exs if exs in EXCHANGE_SCREENER else default


def is_stock_exchange(exchange: str) -> bool:
    """Return True if the exchange is a stock market (not crypto)."""
    return exchange.strip().lower() in STOCK_EXCHANGES


def get_market_type(exchange: str) -> str:
    """Return the TradingView market type for screener queries."""
    return EXCHANGE_SCREENER.get(exchange.strip().lower(), "crypto")
