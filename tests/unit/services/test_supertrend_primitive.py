"""Regression tests for calc_supertrend.

The indicator used to compare every close against its OWN bar's bands. Those
bands sit multiplier*ATR either side of that same bar's midpoint, so a close
could never clear its own upper band: direction initialised to -1 and stayed
there for every bar of every series. ``calc_supertrend`` returned "bearish"
unconditionally and never flipped, which silently disabled the ``supertrend``
backtest strategy — it enters on a -1 -> 1 flip that could not occur.

These tests pin the three properties that were broken: a rising series reads
bullish, a falling series reads bearish, and a real reversal produces exactly
one flip.
"""
from tradingview_mcp.core.services.backtest_service import _run_supertrend
from tradingview_mcp.core.services.indicators_calc import calc_supertrend


def _series(n, start=100.0, step=1.0, rng=1.0):
    out, px = [], start
    for i in range(n):
        out.append({
            "date": f"2026-01-{(i % 28) + 1:02d}",
            "open": px, "high": px + rng, "low": px - rng, "close": px, "volume": 1,
        })
        px += step
    return out


def _directions(candles):
    st = calc_supertrend(
        [c["high"] for c in candles],
        [c["low"] for c in candles],
        [c["close"] for c in candles],
    )
    return st["direction"]


def _flips(direction):
    return sum(
        1 for i in range(1, len(direction))
        if direction[i] is not None and direction[i - 1] is not None
        and direction[i] != direction[i - 1]
    )


def test_rising_series_reads_bullish():
    known = [d for d in _directions(_series(120, step=1.0)) if d is not None]
    assert known, "no direction computed at all"
    assert set(known) == {1}, "a monotonically rising series must read bullish"


def test_falling_series_reads_bearish():
    known = [d for d in _directions(_series(120, start=220.0, step=-1.0)) if d is not None]
    assert known
    assert set(known) == {-1}, "a monotonically falling series must read bearish"


def test_direction_is_not_constant_across_a_reversal():
    # The headline regression: before the fix this was 0 flips for every input.
    candles = _series(60, step=1.0) + _series(40, start=159.0, step=-15.0)
    direction = _directions(candles)
    assert _flips(direction) == 1
    assert direction[-1] == -1


def test_zigzag_produces_a_flip_per_reversal():
    candles = (
        _series(40, step=1.0)
        + _series(30, start=139.0, step=-15.0)
        + _series(40, start=-300.0, step=20.0)
    )
    assert _flips(_directions(candles)) == 2


def test_direction_persists_between_band_penetrations():
    # Supertrend is trend-following: inside the bands the direction carries
    # forward rather than being recomputed per bar.
    candles = _series(80, step=0.2)  # drifts up, never penetrates a band
    known = [d for d in _directions(candles) if d is not None]
    assert len(set(known)) == 1


def test_bands_are_populated_alongside_direction():
    candles = _series(60, step=1.0)
    st = calc_supertrend(
        [c["high"] for c in candles],
        [c["low"] for c in candles],
        [c["close"] for c in candles],
    )
    idx = [i for i, d in enumerate(st["direction"]) if d is not None]
    assert idx, "no warmed-up bars"
    for i in idx:
        assert st["upper"][i] is not None and st["lower"][i] is not None
        assert st["lower"][i] < st["upper"][i]


def test_supertrend_backtest_strategy_can_open_a_trade():
    # The downstream consequence of the bug: _run_supertrend enters on a
    # bearish -> bullish flip, so with a constant direction it never traded.
    series = (
        _series(40, start=200.0, step=-1.0)     # downtrend -> bearish
        + _series(30, start=180.0, step=15.0)   # sharp rally -> flip bullish (entry)
        + _series(30, start=200.0, step=-20.0)  # crash -> flip bearish (exit)
    )
    assert len(_run_supertrend(series)) >= 1
