"""compare_strategies ranking: strategies that made no trades go last.

A strategy that never trades reports a 0% return. Sorted by return alone,
that 0% outranked every strategy that traded and lost money, so in a falling
market rank 1 and ``winner`` went to a strategy with no trades. Seen live on
APP, 1y daily: ``rsi_pullback`` won with 0 trades while buy-and-hold lost 37%.
"""
from __future__ import annotations

from unittest.mock import patch

from tradingview_mcp.core.services import backtest_service


def _candles(n: int = 300) -> list[dict]:
    # 300 bars clear the SMA200 warmup (220), where the old warning never fired.
    return [
        {"date": f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}",
         "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0}
        for i in range(n)
    ]


def _trade(exit_price: float):
    """One trade over the last 10 bars, entered at 100."""
    def fn(candles, **_):
        return [{"entry_date": candles[-10]["date"], "exit_date": candles[-1]["date"],
                 "entry_price": 100.0, "exit_price": exit_price}]
    return fn


def _no_trades(candles, **_):
    return []


def _run(n: int = 300, **strategies) -> dict:
    """Every strategy stubbed: the ones named trade, the rest never do."""
    stubs = {name: _no_trades for name in backtest_service._STRATEGY_MAP}
    stubs.update(strategies)
    with patch.object(backtest_service, "_fetch_ohlcv", return_value=_candles(n)), \
         patch.dict(backtest_service._STRATEGY_MAP, stubs):
        return backtest_service.compare_strategies(
            "TEST", period="1y", commission_pct=0.0, slippage_pct=0.0,
        )


# Every strategy except rsi_pullback and triple_ema trades once and loses.
LOSERS = {
    "rsi": _trade(95.0),
    "bollinger": _trade(97.0),
    "macd": _trade(90.0),
    "ema_cross": _trade(93.0),
    "supertrend": _trade(92.0),
    "donchian": _trade(91.0),
    "keltner_breakout": _trade(89.0),
}


def test_strategy_without_trades_is_not_the_winner():
    result = _run(**LOSERS)
    assert result["winner"] == "bollinger"  # -3%, the smallest loss
    assert result["ranking"][0]["strategy"] == "bollinger"


def test_strategies_without_trades_rank_last():
    result = _run(**LOSERS)
    names = [r["strategy"] for r in result["ranking"]]
    assert names[-2:] == ["rsi_pullback", "triple_ema"]
    assert [r["rank"] for r in result["ranking"]] == list(range(1, 10))


def test_strategies_that_traded_rank_by_return():
    result = _run(**LOSERS)
    returns = [r["total_return_pct"] for r in result["ranking"][:7]]
    assert returns == [-3.0, -5.0, -7.0, -8.0, -9.0, -10.0, -11.0]


def test_warning_names_the_strategies_without_trades():
    result = _run(**LOSERS)
    assert result["warnings"] == (
        "No trades in this period: rsi_pullback, triple_ema. "
        "Strategies without trades rank last and can't be the winner."
    )


def test_no_winner_when_no_strategy_traded():
    result = _run()
    assert result["winner"] is None
    assert len(result["ranking"]) == 9


def test_profitable_strategy_still_wins():
    result = _run(**{**LOSERS, "macd": _trade(110.0)})
    assert result["winner"] == "macd"


def test_no_warning_when_every_strategy_traded():
    result = _run(**LOSERS, rsi_pullback=_trade(96.0), triple_ema=_trade(94.0))
    assert result["warnings"] is None
    assert result["winner"] == "bollinger"


def test_short_history_keeps_the_sma200_warning():
    result = _run(n=100, **LOSERS)
    assert result["warnings"].startswith("Strategies ['rsi_pullback', 'triple_ema'] need ≥220 bars")
    assert result["warnings"].endswith(
        "No trades in this period: rsi_pullback, triple_ema. "
        "Strategies without trades rank last and can't be the winner."
    )
