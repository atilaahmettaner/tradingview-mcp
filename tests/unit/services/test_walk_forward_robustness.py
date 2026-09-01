"""Regression tests for walk-forward robustness scoring.

Two shipped defects:

1. In the both-negative branch, ``fold_rob = min(te/tr, 2.0)`` REWARDED losing
   more out-of-sample: train -1% / test -2% scored a capped 2.0 ("maximally
   robust"). The fix scores ``tr/te`` so losing LESS out-of-sample is what
   scores above 1.

2. Test slices shorter than the strategy's indicator warmup can never trade,
   so ``te=0`` forced ``fold_rob=0.0`` and a false "OVERFITTED" verdict. Such
   folds are now flagged ``insufficient_data`` and excluded from the average.
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


def _trade(entry: float, exit_: float) -> dict:
    return {"entry_date": "2024-01-01", "exit_date": "2024-01-02",
            "entry_price": entry, "exit_price": exit_}


def _fake_strategy(train_exit: float, test_exit: float):
    """Return one trade whose P&L depends on window size.

    Walk-forward slices each fold into train (70%) and test (30%), so the
    train window is always the longer one. n=200, n_splits=2 → fold=100,
    train=70, test=30.
    """
    def fn(candles, **_):
        exit_ = train_exit if len(candles) > 50 else test_exit
        return [_trade(100.0, exit_)]
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


class TestWarmupInsufficientData:
    def test_short_test_windows_do_not_read_as_overfitted(self):
        """ema_cross needs ~50 warmup bars; a 30-bar test slice can't trade.
        That must surface as insufficient data, not OVERFITTED."""
        def no_trades(candles, **_):
            # Realistic: too few bars for the slow EMA → zero signals in
            # test; the train window (70 bars) manages one winning trade.
            if len(candles) > 50:
                return [_trade(100.0, 102.0)]
            return []

        result = _run(no_trades, strategy="ema_cross")
        # 30-bar test slices < 50-bar warmup for every fold → explicit error,
        # never a fold_rob=0.0 "fails out-of-sample" verdict.
        assert "error" in result
        assert "warmup" in result["error"]
        assert all(f["insufficient_data"] for f in result["folds"])

    def test_adequate_windows_are_scored_normally(self):
        """rsi warmup is 14; 30-bar test slices are adequate → scored."""
        result = _run(_fake_strategy(train_exit=102.0, test_exit=102.0))
        assert "error" not in result
        assert result["insufficient_data_folds"] == 0
        assert result["scored_folds"] == len(result["folds"])
