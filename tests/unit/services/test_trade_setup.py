"""Regression tests for compute_trade_setup's entry-anchored scenario math.

The 2026-08 bug: entries came from EMA20/resistance while the stop and R:R
stayed anchored to the close. On stocks trading far above their EMA20
(observed live on EGX:CCAP) the suggested pullback entry landed BELOW the
stop-loss, and R:R graded a trade nobody planned to take (false-rejecting
EGX:COMI's valid pullback at "1.9 < 2").
"""
from __future__ import annotations

import pytest

from tradingview_mcp.core.services.indicators import compute_trade_setup


def _assert_long_invariants(sc: dict) -> None:
    """Every scenario must describe a coherent long trade."""
    entry, stop = sc["entry"], sc["stop_loss"]
    t1, t2 = sc["targets"]["target_1"], sc["targets"]["target_2"]
    assert stop < entry, f"stop {stop} must sit below entry {entry}"
    assert t1 > entry, f"target_1 {t1} must sit above entry {entry}"
    assert t2 > entry, f"target_2 {t2} must sit above entry {entry}"
    rr1 = sc["risk_reward"]["to_target_1"]
    assert rr1 == pytest.approx((t1 - entry) / (entry - stop), abs=0.05), \
        "R:R must be measured from the scenario's own entry"


def test_ccap_shape_entry_never_below_stop():
    """Live CCAP shape: close 5.75 far above EMA20 5.49, support at 5.60.

    Old code: stop = max(5.60 - 0.5*ATR, close - 1.5*ATR) ≈ 5.50-5.52 while
    the pullback entry was 5.49 — entry below stop.
    """
    ind = {
        "close": 5.75,
        "high": 5.80,
        "low": 5.70,
        "ATR": 0.1667,
        "EMA20": 5.49,
        "Pivot.M.Classic.S1": 5.60,
        "Pivot.M.Classic.R1": 5.78,
        "Pivot.M.Classic.R2": 5.83,
    }
    setup = compute_trade_setup(ind)
    assert setup is not None

    scenarios = setup["scenarios"]
    assert "pullback" in scenarios and "breakout" in scenarios
    for sc in scenarios.values():
        _assert_long_invariants(sc)

    # Legacy top-level fields must mirror ONE coherent scenario.
    primary = scenarios[setup["primary_scenario"]]
    assert setup["stop_loss"] == primary["stop_loss"]
    assert setup["targets"] == primary["targets"]
    assert setup["risk_reward"]["to_target_1"] == primary["risk_reward"]["to_target_1"]
    assert setup["risk_reward"]["measured_from_entry"] == primary["entry"]
    # The displayed entry (pullback preferred) must sit above the displayed stop.
    assert setup["entry_points"]["pullback_entry"] > setup["stop_loss"]


def test_comi_shape_no_false_reject():
    """Live COMI shape: entry-anchored R:R must clear 2.0 where the old
    close-anchored math false-rejected at ~1.9."""
    ind = {
        "close": 139.28,
        "high": 140.9,
        "low": 138.5,
        "ATR": 1.0133,
        "EMA20": 138.89,
        "Pivot.M.Classic.S1": 138.30,
        "Pivot.M.Classic.R1": 142.13,
    }
    setup = compute_trade_setup(ind)
    assert setup is not None
    pullback = setup["scenarios"]["pullback"]
    _assert_long_invariants(pullback)

    entry, stop = pullback["entry"], pullback["stop_loss"]
    t1 = pullback["targets"]["target_1"]
    # Old (close-anchored) math graded this < 2; entry-anchored clears it.
    old_rr = (t1 - ind["close"]) / (ind["close"] - stop)
    assert old_rr < 2.0
    assert pullback["risk_reward"]["to_target_1"] >= 2.0


def test_market_fallback_when_no_sr_levels():
    """No pivots/EMAs/BB → still returns one coherent at-market scenario."""
    ind = {"close": 10.0, "high": 10.2, "low": 9.8, "ATR": 0.2}
    setup = compute_trade_setup(ind)
    assert setup is not None
    assert setup["primary_scenario"] == "market"
    market = setup["scenarios"]["market"]
    _assert_long_invariants(market)
    assert market["entry"] == 10.0
    assert "market" in setup["setup_types"]


def test_breakout_targets_sit_above_breakout_entry():
    """Breakout scenario must not reuse its own entry level as target_1."""
    ind = {
        "close": 5.75,
        "high": 5.80,
        "low": 5.70,
        "ATR": 0.1667,
        "EMA20": 5.49,
        "Pivot.M.Classic.S1": 5.60,
        "Pivot.M.Classic.R1": 5.78,
        "Pivot.M.Classic.R2": 5.83,
    }
    setup = compute_trade_setup(ind)
    breakout = setup["scenarios"]["breakout"]
    assert breakout["entry"] == 5.78
    assert breakout["targets"]["target_1"] == 5.83  # next resistance, not 5.78


def test_returns_none_without_atr():
    assert compute_trade_setup({"close": 10.0}) is None
    assert compute_trade_setup({"close": 10.0, "ATR": 0}) is None
