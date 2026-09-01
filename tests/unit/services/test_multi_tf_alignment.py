"""Regression test for multi-timeframe alignment score misattribution.

``alignment_scores`` was appended only for timeframes that succeeded, but
``scores_by_tf`` zipped it against the FULL timeframe list — so when 1W
errored, 1D's score was reported under the "1W" key and every later
timeframe shifted by one. Scores are now recorded as (tf, score) pairs.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from tradingview_mcp.core.services import screener_service


def _bullish_indicators() -> dict[str, Any]:
    return {
        "open": 100.0, "close": 110.0, "high": 111.0, "low": 99.0,
        "SMA20": 105.0, "BB.upper": 115.0, "BB.lower": 95.0,
        "EMA20": 105.0, "EMA50": 104.0, "EMA100": 103.0, "EMA200": 100.0,
        "RSI": 55.0, "MACD.macd": 1.0, "MACD.signal": 0.5, "ADX": 30.0,
        "volume": 1_000.0, "volume.SMA20": 800.0, "VWAP": 105.0, "ATR": 2.0,
    }


def test_failed_timeframe_does_not_shift_scores(monkeypatch):
    monkeypatch.setattr(screener_service, "_TA_AVAILABLE", True)

    def fake_analysis(screener, interval, symbols):
        if interval == "1W":
            raise RuntimeError("upstream 500 for weekly")
        return {symbols[0]: SimpleNamespace(indicators=_bullish_indicators())}

    with patch.object(screener_service, "get_multiple_analysis",
                      side_effect=fake_analysis):
        result = screener_service.run_multi_timeframe_analysis(
            "KUCOIN:BTCUSDT", "kucoin",
        )

    scores = result["alignment"]["scores_by_tf"]

    # The failed timeframe must be absent — before the fix it received the
    # next timeframe's score and every subsequent key shifted by one.
    assert "1W" not in scores
    assert set(scores) == {"1D", "4h", "1h", "15m"}
    assert "error" in result["timeframes"]["1W"]

    # Every reported score must agree with that SAME timeframe's bias.
    bias_to_score = {"Bullish": 1, "Bearish": -1, "Neutral": 0}
    for tf, score in scores.items():
        assert score == bias_to_score[result["timeframes"][tf]["bias"]], tf
