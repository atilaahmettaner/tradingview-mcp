"""Deterministic synthetic OHLCV series for strategy tests.

No randomness and no network: every strategy test must fail for exactly one
reason — the strategy logic changed — never because a seed moved.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone


def make_candles(closes: list[float], *, start: str = "2024-01-01") -> list[dict]:
    """Wrap a close series into candles with a plausible high/low envelope."""
    day = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    candles = []
    for i, close in enumerate(closes):
        prev = closes[i - 1] if i else close
        candles.append({
            "date":   (day + timedelta(days=i)).strftime("%Y-%m-%d"),
            "open":   round(prev, 4),
            "high":   round(max(prev, close) * 1.005, 4),
            "low":    round(min(prev, close) * 0.995, 4),
            "close":  round(close, 4),
            "volume": 1_000_000,
        })
    return candles


def regime_closes(n: int = 420) -> list[float]:
    """A series with every regime the nine strategies need to fire.

    Long enough to clear the 220-bar SMA200 warmup, and shaped so that each
    strategy sees at least one entry *and* one exit: a slow uptrend carries the
    trend followers, a superimposed oscillation carries the mean-reverters, and
    two sharp drawdowns force exits and channel breakdowns.
    """
    closes = []
    for i in range(n):
        trend = 100.0 * (1.0 + 0.0035 * i)          # steady drift up
        wave  = 9.0 * math.sin(i / 7.0)             # mean-reversion fodder
        swell = 4.0 * math.sin(i / 41.0)            # slower breathing
        shock = 0.0
        if 250 <= i < 280:                          # sharp drawdown
            shock = -38.0 * math.sin((i - 250) / 30.0 * math.pi)
        if 360 <= i < 385:                          # second, shallower one
            shock = -22.0 * math.sin((i - 360) / 25.0 * math.pi)
        closes.append(trend + wave + swell + shock)
    return closes


def breakout_closes() -> list[float]:
    """Flat channel, clean upside breakout, then a clean breakdown.

    Purpose-built for Donchian: bars 0-29 define a tight channel, bars 30-44
    break decisively above it, bars 45-69 collapse decisively below it.
    """
    return (
        [100.0 + (i % 3) for i in range(30)]        # chop between 100 and 102
        + [104.0 + 2.0 * i for i in range(15)]      # breakout up to 132
        + [130.0 - 3.0 * i for i in range(25)]      # breakdown through the floor
    )
