"""Multi-timeframe analysis: one scanner request, honest failures, right scores.

* Score misattribution regression: ``alignment_scores`` was appended only for
  timeframes that succeeded, but ``scores_by_tf`` zipped it against the FULL
  timeframe list, so when 1W errored, 1D's score was reported under "1W" and
  every later timeframe shifted by one. Scores are recorded as (tf, score) pairs.
* One request: the tool used to send ten scanner requests per call (TA and ATR
  per timeframe), which tripped TradingView's empty-body throttling on the
  hosted server. All timeframes, ATR included, now come from one request.
* Honest failures: when no timeframe had data the tool still answered
  "MIXED/RANGING - HOLD/NO TRADE". It now raises UPSTREAM_ERROR / NO_DATA.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from tradingview_mcp.core.errors import ScreenerServiceError
from tradingview_mcp.core.services import screener_provider, screener_service

TIMEFRAMES = ["1W", "1D", "4h", "1h", "15m"]


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
    analyses = {tf: SimpleNamespace(indicators=_bullish_indicators()) for tf in TIMEFRAMES}
    analyses["1W"] = None  # no weekly data

    with patch.object(screener_service, "resilient_multi_timeframe_analysis",
                      return_value=analyses):
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


def test_upstream_failure_is_an_error_not_a_mixed_market(monkeypatch):
    monkeypatch.setattr(screener_service, "_TA_AVAILABLE", True)
    boom = RuntimeError(
        "Upstream TradingView scanner returned transient errors on all 3 attempts "
        "spanning 5s (JSONDecodeError('Expecting value')). Wait ~60s before retrying."
    )
    with patch.object(screener_service, "resilient_multi_timeframe_analysis", side_effect=boom):
        with pytest.raises(ScreenerServiceError) as caught:
            screener_service.run_multi_timeframe_analysis("KUCOIN:BTCUSDT", "kucoin")
    envelope = caught.value.to_envelope()
    assert envelope["error"]["code"] == "UPSTREAM_ERROR"
    assert envelope["error"]["retryable"] is True
    assert "Upstream TradingView scanner" in envelope["error"]["message"]


def test_no_data_on_any_timeframe_is_no_data(monkeypatch):
    monkeypatch.setattr(screener_service, "_TA_AVAILABLE", True)
    with patch.object(screener_service, "resilient_multi_timeframe_analysis",
                      return_value={tf: None for tf in TIMEFRAMES}):
        with pytest.raises(ScreenerServiceError) as caught:
            screener_service.run_multi_timeframe_analysis("KUCOIN:NOPEUSDT", "kucoin")
    assert caught.value.to_envelope()["error"]["code"] == "NO_DATA"


def test_all_timeframes_come_from_one_scanner_request(monkeypatch):
    """One request carries every timeframe's columns (ATR included), and each
    value lands in its own timeframe's indicators."""
    pytest.importorskip("tradingview_ta")
    from tradingview_ta.main import TradingView

    keys = TradingView.indicators.copy() + list(screener_provider.TA_EXTRA_COLUMNS) + ["ATR"]
    suffix = {"1W": "|1W", "1D": "", "4h": "|240", "1h": "|60", "15m": "|15"}
    rsi_by_tf = {"1W": 61.0, "1D": 52.0, "4h": 47.0, "1h": 58.0, "15m": 66.0}
    atr_by_tf = {"1W": 5800.0, "1D": 2050.0, "4h": 790.0, "1h": 470.0, "15m": 320.0}

    def values_for(tf):
        row = []
        for k in keys:
            if k in ("Recommend.Other", "Recommend.All", "Recommend.MA"):
                row.append(0.3)
            elif k == "RSI":
                row.append(rsi_by_tf[tf])
            elif k == "ATR":
                row.append(atr_by_tf[tf])
            else:
                row.append(1.0)
        return row

    queries = []

    def fake_scan(q, cookies=None, cache_key=None, raw=False, throttle=False):
        queries.append(q)
        assert raw and throttle
        return {"totalCount": 1, "data": [
            {"s": "KUCOIN:BTCUSDT", "d": [v for tf in TIMEFRAMES for v in values_for(tf)]},
        ]}

    monkeypatch.setattr(screener_provider, "_scan_with_retry", fake_scan)
    monkeypatch.setattr(screener_provider, "_cache_get", lambda key: None)
    out = screener_provider.resilient_multi_timeframe_analysis("crypto", "KUCOIN:BTCUSDT", TIMEFRAMES)

    assert len(queries) == 1
    columns = queries[0].query["columns"]
    assert len(columns) == len(keys) * len(TIMEFRAMES)
    for tf in TIMEFRAMES:
        assert "RSI" + suffix[tf] in columns
        assert "ATR" + suffix[tf] in columns
        analysis = out[tf]
        assert analysis is not None, tf
        assert analysis.indicators["RSI"] == rsi_by_tf[tf]
        assert analysis.indicators["ATR"] == atr_by_tf[tf]


def test_unknown_symbol_gives_no_analysis(monkeypatch):
    pytest.importorskip("tradingview_ta")
    monkeypatch.setattr(screener_provider, "_scan_with_retry",
                        lambda *a, **k: {"totalCount": 0, "data": []})
    monkeypatch.setattr(screener_provider, "_cache_get", lambda key: None)
    out = screener_provider.resilient_multi_timeframe_analysis("crypto", "KUCOIN:NOPEUSDT", TIMEFRAMES)
    assert out == {tf: None for tf in TIMEFRAMES}
