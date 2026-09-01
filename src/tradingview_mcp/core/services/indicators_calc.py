"""
Technical Indicators Calculator — pure Python stdlib, zero dependencies.

All functions take a list of float closing prices (or OHLCV dicts)
and return computed indicator values.

Indicators:
  - EMA, SMA
  - RSI (Wilder's smoothing)
  - Bollinger Bands
  - MACD
  - ATR (Average True Range)
  - Supertrend
  - Donchian Channel
  - ADX (Average Directional Index)
"""
from __future__ import annotations

import math
from typing import Optional


# ─── EMA ──────────────────────────────────────────────────────────────────────

def calc_ema(closes: list[float], period: int) -> list[Optional[float]]:
    """Exponential Moving Average. First (period-1) values are None."""
    result: list[Optional[float]] = [None] * len(closes)
    if len(closes) < period:
        return result
    k = 2 / (period + 1)
    # seed with SMA
    sma = sum(closes[:period]) / period
    result[period - 1] = sma
    for i in range(period, len(closes)):
        result[i] = closes[i] * k + result[i - 1] * (1 - k)
    return result


# ─── SMA ──────────────────────────────────────────────────────────────────────

def calc_sma(closes: list[float], period: int) -> list[Optional[float]]:
    """Simple Moving Average."""
    result: list[Optional[float]] = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        result[i] = sum(closes[i - period + 1 : i + 1]) / period
    return result


# ─── RSI ──────────────────────────────────────────────────────────────────────

def calc_rsi(closes: list[float], period: int = 14) -> list[Optional[float]]:
    """
    Relative Strength Index (Wilder's smoothing).
    First (period) values are None.
    """
    result: list[Optional[float]] = [None] * len(closes)
    if len(closes) < period + 1:
        return result

    gains, losses = [], []
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100 - (100 / (1 + rs))

    for i in range(period + 1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gain = max(diff, 0)
        loss = max(-diff, 0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        if avg_loss == 0:
            result[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i] = 100 - (100 / (1 + rs))

    return result


# ─── Bollinger Bands ──────────────────────────────────────────────────────────

def calc_bollinger(
    closes: list[float], period: int = 20, std_mult: float = 2.0
) -> dict[str, list[Optional[float]]]:
    """
    Bollinger Bands.
    Returns dict with 'upper', 'middle' (SMA), 'lower' lists.
    """
    middle = calc_sma(closes, period)
    upper: list[Optional[float]] = [None] * len(closes)
    lower: list[Optional[float]] = [None] * len(closes)

    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1 : i + 1]
        mean = middle[i]
        variance = sum((x - mean) ** 2 for x in window) / period
        std = math.sqrt(variance)
        upper[i] = mean + std_mult * std
        lower[i] = mean - std_mult * std

    return {"upper": upper, "middle": middle, "lower": lower}


# ─── MACD ─────────────────────────────────────────────────────────────────────

def calc_macd(
    closes: list[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> dict[str, list[Optional[float]]]:
    """
    MACD = EMA(fast) - EMA(slow).
    Signal = EMA(MACD, signal_period).
    Histogram = MACD - Signal.
    """
    ema_fast = calc_ema(closes, fast)
    ema_slow = calc_ema(closes, slow)

    n = len(closes)
    macd_line: list[Optional[float]] = [None] * n
    for i in range(n):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            macd_line[i] = ema_fast[i] - ema_slow[i]

    # Signal line = EMA of MACD line (only over non-None values)
    signal_line: list[Optional[float]] = [None] * n
    histogram: list[Optional[float]] = [None] * n

    # Find first valid macd index
    macd_values = [(i, v) for i, v in enumerate(macd_line) if v is not None]
    if len(macd_values) >= signal:
        # Compute EMA of macd values
        macd_only = [v for _, v in macd_values]
        sig_ema = calc_ema(macd_only, signal)
        for j, (orig_i, _) in enumerate(macd_values):
            if sig_ema[j] is not None:
                signal_line[orig_i] = sig_ema[j]
                histogram[orig_i] = macd_line[orig_i] - sig_ema[j]

    return {"macd": macd_line, "signal": signal_line, "histogram": histogram}


# ─── ATR (Average True Range) ─────────────────────────────────────────────────

def calc_atr(
    highs: list[float], lows: list[float], closes: list[float], period: int = 14
) -> list[Optional[float]]:
    """
    Average True Range — measures market volatility.
    True Range = max(H-L, |H-prevC|, |L-prevC|)
    ATR = Wilder's smoothed average of TR.
    """
    n = len(closes)
    result: list[Optional[float]] = [None] * n
    if n < period + 1:
        return result

    trs = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)

    # Seed with simple average
    atr = sum(trs[:period]) / period
    result[period] = atr
    for i in range(period + 1, n):
        atr = (atr * (period - 1) + trs[i - 1]) / period
        result[i] = atr

    return result


# ─── Supertrend ───────────────────────────────────────────────────────────────

def calc_supertrend(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    atr_period: int = 10,
    multiplier: float = 3.0,
) -> dict[str, list]:
    """
    Supertrend indicator.
    Returns dict with:
      'direction': 1 (bullish) or -1 (bearish) per candle (None before warmup)
      'upper': upper band values
      'lower': lower band values
    """
    n = len(closes)
    atr = calc_atr(highs, lows, closes, atr_period)

    direction: list[Optional[int]] = [None] * n
    upper: list[Optional[float]] = [None] * n
    lower: list[Optional[float]] = [None] * n

    # prev values for smoothing
    prev_upper = None
    prev_lower = None
    prev_dir   = None

    for i in range(1, n):
        if atr[i] is None:
            continue

        hl2  = (highs[i] + lows[i]) / 2.0
        u    = hl2 + multiplier * atr[i]
        l    = hl2 - multiplier * atr[i]

        # Adjust bands to avoid widening
        if prev_upper is not None:
            u = min(u, prev_upper) if closes[i - 1] < prev_upper else u
            l = max(l, prev_lower) if closes[i - 1] > prev_lower else l

        upper[i] = u
        lower[i] = l

        # Determine direction
        if prev_dir is None:
            direction[i] = 1 if closes[i] > u else -1
        elif prev_dir == 1:
            direction[i] = 1 if closes[i] >= l else -1
        else:
            direction[i] = -1 if closes[i] <= u else 1

        prev_upper = u
        prev_lower = l
        prev_dir   = direction[i]

    return {"direction": direction, "upper": upper, "lower": lower}


# ─── Donchian Channel ─────────────────────────────────────────────────────────

def calc_donchian(
    highs: list[float], lows: list[float], period: int = 20
) -> dict[str, list[Optional[float]]]:
    """
    Donchian Channel.
    Returns dict with 'upper' (highest high), 'lower' (lowest low), 'middle'.
    """
    n = len(highs)
    upper: list[Optional[float]] = [None] * n
    lower: list[Optional[float]] = [None] * n
    middle: list[Optional[float]] = [None] * n

    for i in range(period - 1, n):
        u = max(highs[i - period + 1 : i + 1])
        l = min(lows[i - period + 1 : i + 1])
        upper[i]  = u
        lower[i]  = l
        middle[i] = (u + l) / 2

    return {"upper": upper, "lower": lower, "middle": middle}
