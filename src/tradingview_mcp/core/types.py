"""
Shared type definitions and primitive helpers for the TradingView MCP package.

Keeping these in one place avoids circular imports between service modules
and lets server.py import cleanly without depending on any service.
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from typing_extensions import TypedDict


# ── Indicator containers ───────────────────────────────────────────────────────

class IndicatorMap(TypedDict, total=False):
    open: Optional[float]
    close: Optional[float]
    SMA20: Optional[float]
    BB_upper: Optional[float]
    BB_lower: Optional[float]
    EMA50: Optional[float]
    RSI: Optional[float]
    volume: Optional[float]


class Row(TypedDict):
    symbol: str
    changePercent: float
    indicators: IndicatorMap


class MultiRow(TypedDict):
    symbol: str
    changes: dict[str, Optional[float]]
    base_indicators: IndicatorMap


# ── Primitive helpers ──────────────────────────────────────────────────────────

def map_indicators(raw: Dict[str, Any]) -> IndicatorMap:
    """Map a raw TradingView indicators dict to the typed IndicatorMap subset."""
    return IndicatorMap(
        open=raw.get("open"),
        close=raw.get("close"),
        SMA20=raw.get("SMA20"),
        BB_upper=raw.get("BB.upper") if "BB.upper" in raw else raw.get("BB_upper"),
        BB_lower=raw.get("BB.lower") if "BB.lower" in raw else raw.get("BB_lower"),
        EMA50=raw.get("EMA50"),
        RSI=raw.get("RSI"),
        volume=raw.get("volume"),
    )


def percent_change(o: Optional[float], c: Optional[float]) -> Optional[float]:
    """Safe percentage change calculation: (close - open) / open * 100."""
    try:
        if o in (None, 0) or c is None:
            return None
        return (c - o) / o * 100
    except Exception:
        return None


def tf_to_tv_resolution(tf: Optional[str]) -> Optional[str]:
    """Map human-readable timeframe strings to TradingView resolution codes."""
    if not tf:
        return None
    return {
        "5m": "5",
        "15m": "15",
        "30m": "30",
        "1h": "60",
        "4h": "240",
        "1D": "1D",
        "1W": "1W",
        "1M": "1M",
    }.get(tf)


def safe_round(value: Any, decimals: int = 4) -> Optional[float]:
    """Round a value safely, returning None if the value is None or invalid."""
    if value is None:
        return None
    try:
        return round(float(value), decimals)
    except (TypeError, ValueError):
        return None
