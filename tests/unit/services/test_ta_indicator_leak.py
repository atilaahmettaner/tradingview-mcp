"""Each tradingview_ta Analysis keeps its own indicators.

tradingview_ta's calculate() wrote every indicator into a dict declared on the
Analysis class, which every Analysis shares, and then copied that dict onto the
instance. A column one request asked for and the next didn't stayed behind.
multi_timeframe_analysis is the only request that includes ATR, so after one
call coin_analysis reported that symbol's ATR for every other symbol (BTC 4h
read 0.0003, DOGE's 15m ATR) and skipped its own ATR lookup, and stock trade
setups built on that ATR disappeared. screener_provider now gives each
Analysis its own dict.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from tradingview_mcp.core.services import screener_provider, screener_service

TIMEFRAMES = ["1W", "1D", "4h", "1h", "15m"]


def _row(keys, **values):
    """Scanner values for ``keys``: the given ones, neutral recommendations,
    1.0 everywhere else."""
    row = []
    for k in keys:
        if k in values:
            row.append(values[k])
        elif k in ("Recommend.Other", "Recommend.All", "Recommend.MA"):
            row.append(0.3)
        else:
            row.append(1.0)
    return row


def test_a_column_from_one_analysis_does_not_reach_the_next():
    pytest.importorskip("tradingview_ta")
    from tradingview_ta.main import TradingView, calculate

    keys = TradingView.indicators.copy()
    doge = calculate(
        indicators=dict(zip(keys + ["ATR"], _row(keys + ["ATR"], ATR=0.0003))),
        indicators_key=keys + ["ATR"],
        screener="crypto", symbol="DOGEUSDT", exchange="BINANCE", interval="15m",
    )
    btc = calculate(
        indicators=dict(zip(keys, _row(keys, close=80_600.0))),
        indicators_key=keys,
        screener="crypto", symbol="BTCUSDT", exchange="BINANCE", interval="4h",
    )

    assert doge.indicators["ATR"] == 0.0003
    assert "ATR" not in btc.indicators
    assert btc.indicators["close"] == 80_600.0


def test_coin_analysis_looks_up_its_own_atr_after_a_multi_timeframe_call(monkeypatch):
    """The reported case: coin_analysis of BTC 4h after a multi-timeframe
    analysis of DOGE."""
    pytest.importorskip("tradingview_ta")
    from tradingview_ta.main import TradingView

    monkeypatch.setattr(screener_provider, "_cache_get", lambda key: None)
    monkeypatch.setattr(screener_provider, "_cache_set", lambda key, payload: None)
    monkeypatch.setenv("TRADINGVIEW_MCP_MIN_INTERVAL_S", "0")

    # multi_timeframe_analysis of DOGE: the one request that includes ATR.
    mtf_keys = TradingView.indicators.copy() + list(screener_provider.TA_EXTRA_COLUMNS) + ["ATR"]
    doge_row = [v for _ in TIMEFRAMES for v in _row(mtf_keys, ATR=0.0003)]
    monkeypatch.setattr(screener_provider, "_scan_with_retry", lambda *a, **k: {
        "totalCount": 1, "data": [{"s": "BINANCE:DOGEUSDT", "d": doge_row}],
    })
    screener_provider.resilient_multi_timeframe_analysis("crypto", "BINANCE:DOGEUSDT", TIMEFRAMES)

    # coin_analysis of BTC 4h: tradingview_ta's own request, without ATR.
    ta_keys = TradingView.indicators.copy() + list(screener_provider.TA_EXTRA_COLUMNS)
    btc_row = _row(ta_keys, open=80_500.0, high=80_800.0, low=80_400.0, close=80_600.0,
                   SMA20=80_300.0, **{"BB.upper": 81_000.0, "BB.lower": 79_600.0})

    def fake_post(url, **kwargs):
        assert url.endswith("/crypto/scan")
        return SimpleNamespace(text=json.dumps({"data": [{"s": "BINANCE:BTCUSDT", "d": btc_row}]}))

    monkeypatch.setattr("tradingview_ta.main.requests.post", fake_post)

    lookups = []

    def fake_atr(ticker, screener, timeframe=None, timeout=10.0):
        lookups.append((ticker, screener, timeframe))
        return 720.0

    monkeypatch.setattr(screener_provider, "fetch_atr_for_ticker", fake_atr)
    monkeypatch.setattr(screener_service, "_TA_AVAILABLE", True)

    result = screener_service.analyze_coin("BTCUSDT", "binance", "4h")

    assert lookups == [("BINANCE:BTCUSDT", "crypto", "4h")]
    assert result["atr"]["value"] == 720.0
    assert result["atr"]["percent_of_price"] == pytest.approx(0.89, abs=0.01)
