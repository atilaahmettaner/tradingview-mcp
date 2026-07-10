"""Correctness tests for backtest metrics and walk-forward fold scoring."""
from __future__ import annotations

import json

import pytest

from tradingview_mcp.core.services.backtest_service import (
    _calc_metrics,
    _fold_robustness,
    _max_drawdown_pct,
    _trades_per_year,
)

from ._synthetic import make_candles


def trade(entry_date, exit_date, entry, exit_, return_pct):
    return {
        "entry_date": entry_date, "exit_date": exit_date,
        "entry_price": entry, "exit_price": exit_,
        "return_pct": return_pct, "strategy": "test",
    }


# ─── Walk-forward robustness: the F-02 regression ─────────────────────────────

def metrics(total_return_pct, total_trades=5):
    return {"total_return_pct": total_return_pct, "total_trades": total_trades}


def test_losing_worse_out_of_sample_never_outscores_losing_less():
    """The inversion that scored a 5x-worse strategy as maximally robust.

    Dividing two negative returns yields a positive ratio, so `te/tr` for
    (-10%, -50%) was 5.0, capped to the maximum 2.0 → verdict ROBUST. Meanwhile
    (-10%, -2%), which *improved* out-of-sample, scored 0.2 → OVERFITTED.
    """
    much_worse = _fold_robustness(metrics(-10.0), metrics(-50.0))
    slightly_better = _fold_robustness(metrics(-10.0), metrics(-2.0))

    assert much_worse <= slightly_better
    assert much_worse == 0.0, "a strategy that lost in-sample has no edge to validate"


@pytest.mark.parametrize("train_return", [-50.0, -10.0, -0.01, 0.0])
def test_no_edge_in_sample_scores_zero(train_return):
    assert _fold_robustness(metrics(train_return), metrics(25.0)) == 0.0


def test_a_fold_that_never_traded_is_not_robust():
    """`0/0` is not evidence of consistency.

    Before the donchian fix this was the *only* branch donchian ever hit, and it
    returned 1.0 — a perfect robustness score for a strategy that never traded.
    """
    assert _fold_robustness(metrics(0.0, total_trades=0), metrics(0.0, total_trades=0)) == 0.0
    assert _fold_robustness(metrics(20.0, total_trades=5), metrics(0.0, total_trades=0)) == 0.0


def test_holding_up_out_of_sample_scores_near_one():
    assert _fold_robustness(metrics(20.0), metrics(18.0)) == 0.9


def test_robustness_is_clamped_both_ways():
    assert _fold_robustness(metrics(10.0), metrics(500.0)) == 2.0    # one lucky fold
    assert _fold_robustness(metrics(10.0), metrics(-500.0)) == -1.0  # one blow-up


# ─── profit_factor: the F-05 regression ───────────────────────────────────────

def test_no_losing_trades_yields_json_safe_profit_factor():
    """float("inf") serialises as the bare token `Infinity` — not valid JSON.

    A strict client fails to decode the entire tool response, not just this key.
    """
    winners_only = [
        trade("2024-01-01", "2024-01-05", 100, 110, 10.0),
        trade("2024-02-01", "2024-02-05", 100, 105, 5.0),
    ]
    m = _calc_metrics(winners_only, 10_000, "1d")

    assert m["profit_factor"] is None
    assert m["no_losing_trades"] is True

    encoded = json.dumps(m)
    assert "Infinity" not in encoded
    json.loads(encoded, parse_constant=_reject)  # strict: no Infinity/NaN allowed


def _reject(token):
    raise AssertionError(f"non-JSON constant emitted: {token}")


def test_profit_factor_is_a_ratio_when_there_are_losers():
    trades = [
        trade("2024-01-01", "2024-01-05", 100, 120, 20.0),
        trade("2024-02-01", "2024-02-05", 100, 90, -10.0),
    ]
    m = _calc_metrics(trades, 10_000, "1d")
    assert m["profit_factor"] == 2.0
    assert m["no_losing_trades"] is False


# ─── Sharpe annualisation: the F-03 regression ────────────────────────────────

def test_annualisation_follows_trade_frequency_not_bar_count():
    """Two trades spread over two years is not 252 observations a year."""
    sparse = [
        trade("2024-01-01", "2024-01-10", 100, 110, 10.0),
        trade("2025-06-01", "2025-12-20", 100, 105, 5.0),
    ]
    factor = _trades_per_year(sparse, "1d")
    assert 0.8 < factor < 1.3, f"expected ~1 trade/year, got {factor}"


def test_annualisation_never_exceeds_the_bar_count():
    """A strategy cannot trade more often than the data has bars."""
    burst = [
        trade("2024-01-01", "2024-01-01", 100, 101, 1.0),
        trade("2024-01-02", "2024-01-02", 100, 101, 1.0),
    ]
    assert _trades_per_year(burst, "1d") <= 252


def test_sparse_trading_is_not_awarded_a_dense_trading_sharpe():
    """The old code scaled per-trade returns by sqrt(252) regardless.

    Identical returns spread over two years must not earn the same Sharpe as
    the same returns taken daily.
    """
    returns = [8.0, -3.0, 6.0, -2.0]
    sparse = [
        trade(f"202{i}-01-01", f"202{i}-03-01", 100, 100 + r, r)
        for i, r in enumerate(returns)
    ]
    dense = [
        trade(f"2024-01-{i+1:02d}", f"2024-01-{i+2:02d}", 100, 100 + r, r)
        for i, r in enumerate(returns)
    ]

    sparse_sharpe = _calc_metrics(sparse, 10_000, "1d")["sharpe_ratio"]
    dense_sharpe = _calc_metrics(dense, 10_000, "1d")["sharpe_ratio"]

    assert abs(sparse_sharpe) < abs(dense_sharpe), (
        "annualisation must reward trade frequency, not ignore it"
    )


# ─── Drawdown sampling: the F-04 regression ───────────────────────────────────

def test_intra_trade_drawdown_is_captured_when_candles_are_supplied():
    """Sampling equity only at exits hides the hole in the middle of a trade."""
    closes = [100.0, 90.0, 70.0, 50.0, 80.0, 110.0]
    candles = make_candles(closes)
    one_trade = [trade(candles[0]["date"], candles[-1]["date"], 100.0, 110.0, 10.0)]

    sampled_at_exit = _max_drawdown_pct(one_trade, 10_000, candles=None)
    marked_to_market = _max_drawdown_pct(one_trade, 10_000, candles=candles)

    assert sampled_at_exit == 0.0, "a single winning trade shows no drawdown at exit"
    assert marked_to_market == pytest.approx(50.0, abs=0.5), (
        "equity halved mid-trade; that must surface"
    )


def test_calmar_uses_the_deeper_drawdown():
    """Understating drawdown inflates Calmar, which divides by it."""
    closes = [100.0, 60.0, 110.0]
    candles = make_candles(closes)
    one_trade = [trade(candles[0]["date"], candles[-1]["date"], 100.0, 110.0, 10.0)]

    shallow = _calc_metrics(one_trade, 10_000, "1d")
    deep = _calc_metrics(one_trade, 10_000, "1d", candles=candles)

    assert abs(deep["max_drawdown_pct"]) > abs(shallow["max_drawdown_pct"])
    assert abs(deep["calmar_ratio"]) < abs(shallow["calmar_ratio"] or 1e9)


def test_drawdown_falls_back_cleanly_when_dates_do_not_match_candles():
    """Walk-forward passes trades whose dates may sit outside the window."""
    candles = make_candles([100.0, 105.0, 110.0])
    orphan = [trade("1999-01-01", "1999-06-01", 100.0, 90.0, -10.0)]

    dd = _max_drawdown_pct(orphan, 10_000, candles=candles)
    assert dd == pytest.approx(10.0, abs=0.01), "must still sample at the exit"


# ─── The empty case still holds ───────────────────────────────────────────────

def test_no_trades_returns_the_empty_shape():
    m = _calc_metrics([], 10_000, "1d")
    assert m["total_trades"] == 0
    assert m["final_capital"] == 10_000
    json.dumps(m)  # must remain serialisable
