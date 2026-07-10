"""Correctness tests for the nine backtest strategy engines.

These are pure functions over a list of candle dicts — no network, no mocks.
Two of them shipped broken for want of exactly this file.
"""
from __future__ import annotations

import pytest

from tradingview_mcp.core.services.backtest_service import (
    _STRATEGY_MAP,
    _SMA200_STRATEGIES,
    _run_donchian,
)
from tradingview_mcp.core.services.indicators_calc import calc_donchian

from ._synthetic import breakout_closes, make_candles, regime_closes


@pytest.fixture(scope="module")
def regime_candles() -> list[dict]:
    return make_candles(regime_closes())


@pytest.fixture(scope="module")
def breakout_candles() -> list[dict]:
    return make_candles(breakout_closes())


# ─── No strategy is structurally dead ─────────────────────────────────────────

@pytest.mark.parametrize("name", sorted(_STRATEGY_MAP))
def test_strategy_produces_trades_on_a_series_designed_to_trigger_it(name, regime_candles):
    """Every strategy must fire on a series containing every regime.

    A strategy that returns zero trades on trending, oscillating, and crashing
    data is not conservative — it is broken. `donchian` returned zero trades on
    *every* input because its entry compared a bar's high against a channel
    window that included that same high, which is never satisfiable.
    """
    trades = _STRATEGY_MAP[name](regime_candles)
    assert trades, f"{name} produced no trades on a series built to trigger it"


@pytest.mark.parametrize("name", sorted(_STRATEGY_MAP))
def test_trades_are_well_formed_and_chronological(name, regime_candles):
    trades = _STRATEGY_MAP[name](regime_candles)
    for trade in trades:
        assert trade["entry_price"] > 0
        assert trade["exit_price"] > 0
        assert trade["entry_date"] < trade["exit_date"], "exit must follow entry"

    exits = [t["exit_date"] for t in trades]
    entries = [t["entry_date"] for t in trades]
    assert exits == sorted(exits), "trades must be emitted in order"
    for prev_exit, next_entry in zip(exits, entries[1:]):
        assert next_entry >= prev_exit, "positions must not overlap"


# ─── No lookahead ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", sorted(_STRATEGY_MAP))
def test_strategy_cannot_see_the_future(name, regime_candles):
    """Truncating the series must not change trades that already closed.

    If a strategy read any bar after a trade's exit, deleting those bars would
    perturb that trade. Run the full series, then re-run on a prefix, and demand
    the trades wholly inside the prefix are byte-identical.
    """
    full = _STRATEGY_MAP[name](regime_candles)
    assert full, f"{name}: no trades to check"

    # Cut a few bars after the first trade closes, so there is always at least
    # one settled trade to compare regardless of how often the strategy fires.
    dates = [c["date"] for c in regime_candles]
    cutoff = dates.index(full[0]["exit_date"]) + 4
    assert cutoff < len(regime_candles), f"{name}: first trade closes too late to truncate"

    prefix = _STRATEGY_MAP[name](regime_candles[:cutoff])

    boundary = regime_candles[cutoff - 1]["date"]
    settled = [t for t in full if t["exit_date"] < boundary]

    assert settled, f"{name}: no settled trades before the cutoff to compare"
    assert prefix[:len(settled)] == settled, (
        f"{name} changed a closed trade when future bars were removed — "
        "this is lookahead bias"
    )


# ─── Donchian: the F-01 regression ────────────────────────────────────────────

def test_donchian_enters_on_breakout_and_exits_on_breakdown(breakout_candles):
    trades = _run_donchian(breakout_candles, period=20)

    assert len(trades) == 1, f"expected one clean round trip, got {len(trades)}"
    trade = trades[0]
    assert trade["strategy"] == "donchian"

    # Entry must land on the breakout, above the 100-102 chop that formed the
    # channel — not inside it, and not at the very top of the run.
    assert trade["entry_price"] > 102.0

    # Exit must land on the way down, after the entry.
    assert trade["exit_date"] > trade["entry_date"]
    assert trade["exit_price"] < 132.0, "exit belongs on the breakdown, not the peak"


def test_donchian_channel_window_includes_its_own_bar():
    """Pin the invariant that made the original entry condition unsatisfiable.

    `calc_donchian` builds upper[i] from a window *including* bar i. So
    `highs[i] > upper[i]` is never true, and neither is `highs[i-1] >
    upper[i-1]`. The strategy must therefore compare against the *previous*
    bar's channel. If calc_donchian ever changes to an exclusive window, this
    test fails and the strategy needs revisiting.
    """
    highs = [10, 11, 12, 13, 14, 15, 20, 25, 30, 35]
    lows = [h - 1 for h in highs]
    dc = calc_donchian(highs, lows, period=3)

    for i, upper in enumerate(dc["upper"]):
        if upper is not None:
            assert highs[i] <= upper, "upper[i] must contain highs[i]"


def test_donchian_does_not_trade_inside_its_own_channel():
    """A flat series never breaks out. Guards against an over-eager fix."""
    candles = make_candles([100.0 + (i % 3) for i in range(60)])
    assert _run_donchian(candles, period=20) == []
