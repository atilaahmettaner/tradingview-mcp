"""Regression tests for walk-forward robustness scoring.

Three shipped defects:

1. In the both-negative branch, ``fold_rob = min(te/tr, 2.0)`` REWARDED losing
   more out-of-sample: train -1% / test -2% scored a capped 2.0 ("maximally
   robust"). The fix scores ``tr/te`` so losing LESS out-of-sample is what
   scores above 1.

2. Test slices that can't trade used to force ``fold_rob=0.0`` and a false
   "OVERFITTED" verdict. Such folds are flagged ``insufficient_data`` and
   excluded from the average.

3. Every slice was simulated cold, on its own bars only. ema_cross (50-bar
   warmup) never traded in the ~50-bar test windows of the default 2y /
   3-split run, so the tool failed with its own defaults, and every slice lost
   its first warmup bars. Slices now run with the history just before them,
   and only trades opened inside the slice count.
"""
from __future__ import annotations

from unittest.mock import patch

from tradingview_mcp.core.services import backtest_service


def _candles(n: int = 200) -> list[dict]:
    return [
        {"date": f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}",
         "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0}
        for i in range(n)
    ]


CANDLES = _candles()
# n=200, n_splits=2 → fold=100, train=70, test=30: test slices end on the
# fold boundaries, train slices at bars 69 and 169.
TEST_ENDS = {CANDLES[99]["date"], CANDLES[199]["date"]}


def _trade_near_end(candles: list[dict], exit_price: float) -> dict:
    """A trade opened 3 bars before the end of what the strategy was given."""
    return {"entry_date": candles[-3]["date"], "exit_date": candles[-1]["date"],
            "entry_price": 100.0, "exit_price": exit_price}


def _fake_strategy(train_exit: float, test_exit: float):
    """One trade whose P&L depends on which slice the run belongs to.

    Slices run with warmup history in front of them, so the length of what
    the strategy receives doesn't tell train from test; where it ends does.
    """
    def fn(candles, **_):
        exit_ = test_exit if candles[-1]["date"] in TEST_ENDS else train_exit
        return [_trade_near_end(candles, exit_)]
    return fn


def _needs_bars(bars: int, exit_price: float = 102.0):
    """A strategy that emits nothing until its slow indicator has `bars` bars."""
    def fn(candles, **_):
        return [_trade_near_end(candles, exit_price)] if len(candles) >= bars else []
    return fn


def _run(strategy_fn, strategy: str = "rsi") -> dict:
    with patch.object(backtest_service, "_fetch_ohlcv", return_value=_candles()), \
         patch.dict(backtest_service._STRATEGY_MAP, {strategy: strategy_fn}):
        return backtest_service.walk_forward_backtest(
            "TEST", strategy, period="2y",
            commission_pct=0.0, slippage_pct=0.0, n_splits=2,
        )


class TestBothNegativeBranch:
    def test_losing_more_out_of_sample_is_not_robust(self):
        """train -1%, test -2% used to score a capped 2.0 → ROBUST."""
        result = _run(_fake_strategy(train_exit=99.0, test_exit=98.0))
        assert "error" not in result
        scores = [f["fold_robustness_score"] for f in result["folds"]]
        assert all(s == 0.5 for s in scores)
        assert not result["verdict"].startswith("ROBUST")

    def test_losing_less_out_of_sample_scores_high(self):
        """train -2%, test -1%: the test window held up better → robust."""
        result = _run(_fake_strategy(train_exit=98.0, test_exit=99.0))
        scores = [f["fold_robustness_score"] for f in result["folds"]]
        assert all(s == 2.0 for s in scores)
        assert result["verdict"].startswith("ROBUST")


class TestPositiveBranchUnchanged:
    def test_test_return_half_of_train(self):
        result = _run(_fake_strategy(train_exit=102.0, test_exit=101.0))
        scores = [f["fold_robustness_score"] for f in result["folds"]]
        assert all(s == 0.5 for s in scores)


class TestWarmup:
    def test_short_test_windows_trade_once_warm(self):
        """ema_cross needs ~50 bars and the test slices here are 30. Run cold
        they never traded and the tool returned an error; warmed on the
        history before them they trade and are scored."""
        result = _run(_needs_bars(55), strategy="ema_cross")
        assert "error" not in result
        assert result["insufficient_data_folds"] == 0
        assert all(f["test_trades"] == 1 for f in result["folds"])

    def test_trades_opened_in_the_warmup_history_do_not_count(self):
        """The history in front of a slice only warms the indicators: a trade
        opened there belongs to the slice before."""
        def opens_at_first_bar(candles, **_):
            return [{"entry_date": candles[0]["date"], "exit_date": candles[-1]["date"],
                     "entry_price": 100.0, "exit_price": 110.0}]

        result = _run(opens_at_first_bar, strategy="ema_cross")
        assert all(f["test_trades"] == 0 for f in result["folds"])
        # The first train slice starts at bar 0, so there is no history in
        # front of it and its trade is its own.
        assert result["folds"][0]["train_trades"] == 1

    def test_not_enough_history_is_insufficient_data(self):
        """When no test slice has warmup-length history before it, the tool
        says so and names options that exist (2y is the longest period)."""
        with patch.dict(backtest_service._STRATEGY_WARMUP_BARS, {"ema_cross": 500}):
            result = _run(_needs_bars(55), strategy="ema_cross")
        assert "error" in result
        assert "warm up" in result["error"] and "period='2y'" in result["error"]
        assert all(f["insufficient_data"] for f in result["folds"])

    def test_adequate_windows_are_scored_normally(self):
        """rsi warmup is 14; every test slice has the history it needs."""
        result = _run(_fake_strategy(train_exit=102.0, test_exit=102.0))
        assert "error" not in result
        assert result["insufficient_data_folds"] == 0
        assert result["scored_folds"] == len(result["folds"])
