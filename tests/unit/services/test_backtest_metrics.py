"""Regression tests for backtest metric correctness.

- Open positions at data end were silently discarded (a strategy underwater
  in an open trade reported only its closed winners) → now force-closed at
  the final bar, flagged forced_exit.
- Drawdown/equity were computed only at trade exits, so a trade that rode a
  deep dip before exiting green showed near-zero drawdown → now mark-to-market
  per bar.
- Buy-and-hold benchmark was cost-free while the strategy paid
  commission+slippage → now charged one round trip of the same costs.
"""
from __future__ import annotations

from tradingview_mcp.core.services import backtest_service


def _candle(date: str, price: float) -> dict:
    return {"date": date, "open": price, "high": price * 1.01,
            "low": price * 0.99, "close": price, "volume": 100}


class TestForcedExit:
    def test_open_position_is_closed_at_final_bar(self):
        # RSI dives below 40 (entry) and never recovers above 60 (no exit).
        prices = [100.0] * 15 + [90.0, 80.0, 70.0, 65.0, 60.0]
        candles = [_candle(f"2024-01-{i+1:02d}", p) for i, p in enumerate(prices)]
        trades = backtest_service._run_rsi(candles)
        assert len(trades) == 1
        assert trades[0]["forced_exit"] is True
        assert trades[0]["exit_date"] == candles[-1]["date"]
        assert trades[0]["exit_price"] == 60.0  # the loss is realized, not hidden


class TestMarkToMarketDrawdown:
    def test_intra_trade_dip_counts_toward_drawdown(self):
        # One trade: enter day 1 at 100, dip to 60 mid-trade, exit day 5 at 102.
        candles = [
            _candle("2024-01-01", 100.0),
            _candle("2024-01-02", 80.0),
            _candle("2024-01-03", 60.0),
            _candle("2024-01-04", 90.0),
            _candle("2024-01-05", 102.0),
        ]
        trades = [{
            "entry_date": "2024-01-01", "entry_price": 100.0,
            "exit_date": "2024-01-05", "exit_price": 102.0,
            "return_pct": 2.0, "strategy": "x",
        }]

        m = backtest_service._calc_metrics(trades, 10_000, "1d", candles=candles)
        # Equity dips to 6,000 at the trough → ~40% drawdown. The old
        # exit-only path reported 0% for this winning trade.
        assert m["max_drawdown_pct"] <= -39.0
        assert m["total_return_pct"] == 2.0

    def test_without_candles_falls_back_to_trade_based(self):
        trades = [{
            "entry_date": "a", "entry_price": 100.0,
            "exit_date": "b", "exit_price": 102.0,
            "return_pct": 2.0, "strategy": "x",
        }]
        m = backtest_service._calc_metrics(trades, 10_000, "1d")
        assert m["total_return_pct"] == 2.0
        assert m["max_drawdown_pct"] == 0


class TestFairBuyAndHold:
    def test_benchmark_pays_the_same_round_trip_costs(self):
        candles = [_candle("2024-01-01", 100.0), _candle("2024-01-02", 110.0)]
        assert backtest_service._buy_and_hold_return(candles) == 10.0
        assert backtest_service._buy_and_hold_return(candles, 0.1, 0.05) == 9.7
