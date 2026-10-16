"""The volume tools read a real volume baseline, in one scanner request.

``volume_breakout_scan`` (volume_breakout_scanner, smart_volume_scanner) and
``volume_confirmation_analyze`` (volume_confirmation_analysis) computed the
volume ratio from a ``volume.SMA20`` column that was never fetched:
tradingview_ta doesn't request it and TradingView's scanner has no volume-SMA
field. So the scans skipped every symbol and always returned an empty list, and
volume_confirmation always reported a 1.0x ratio. The scans also ran in
100-symbol batches capped at the first 500 symbols.

They now read TradingView's ``relative_volume_10d_calc`` (the bar's volume over
the mean of the previous 10 bars at the timeframe) and fetch the whole list in
one request.
"""
from __future__ import annotations

from unittest.mock import patch

from tradingview_mcp.core.errors import is_error
from tradingview_mcp.core.services import scanner_service


def _row(open_price: float, close: float, volume: float, relative_volume) -> dict:
    return {
        "open": open_price, "close": close, "high": max(open_price, close) * 1.01,
        "low": min(open_price, close) * 0.99, "volume": volume,
        "relative_volume_10d_calc": relative_volume, "RSI": 55.0,
        "BB.upper": close * 1.05, "BB.lower": close * 0.95,
    }


def test_baseline_column_is_one_the_scanner_has():
    for columns in (scanner_service._BREAKOUT_COLUMNS, scanner_service._CONFIRMATION_COLUMNS):
        assert "relative_volume_10d_calc" in columns
        assert "volume.SMA20" not in columns


def test_breakout_scan_is_one_request_over_the_whole_list():
    """A breakout past the old 500-symbol cap must be found."""
    nasdaq = [f"NASDAQ:T{i}" for i in range(4997)]
    calls: list = []

    def fake_scan(screener, interval, symbols, columns):
        calls.append({"screener": screener, "interval": interval,
                      "symbols": list(symbols), "columns": list(columns)})
        rows = {s: _row(100.0, 100.5, 1_000.0, 1.0) for s in symbols}  # quiet
        rows["NASDAQ:T4000"] = _row(100.0, 108.0, 5_000.0, 5.0)       # +8%, 5x
        return rows

    with patch.object(scanner_service, "resilient_scan_columns", side_effect=fake_scan), \
         patch.object(scanner_service, "load_symbols", return_value=nasdaq):
        rows = scanner_service.volume_breakout_scan("nasdaq", "1D")

    assert len(calls) == 1
    assert calls[0]["screener"] == "america"
    assert calls[0]["interval"] == "1D"
    assert calls[0]["symbols"] == nasdaq
    assert calls[0]["columns"] == scanner_service._BREAKOUT_COLUMNS
    assert [r["symbol"] for r in rows] == ["NASDAQ:T4000"]
    assert rows[0]["volume_ratio"] == 5.0
    assert rows[0]["breakout_type"] == "bullish"


def test_smart_volume_scan_returns_the_breakouts():
    symbols = ["BINANCE:UPUSDT", "BINANCE:DNUSDT", "BINANCE:FLATUSDT"]

    def fake_scan(screener, interval, symbols, columns):
        return {
            "BINANCE:UPUSDT": _row(1.00, 1.05, 30_000.0, 3.0),    # +5%, 3x
            "BINANCE:DNUSDT": _row(1.00, 0.96, 25_000.0, 2.5),    # -4%, 2.5x
            "BINANCE:FLATUSDT": _row(1.00, 1.001, 50_000.0, 5.0),  # no price move
        }

    with patch.object(scanner_service, "resilient_scan_columns", side_effect=fake_scan), \
         patch.object(scanner_service, "load_symbols", return_value=symbols):
        rows = scanner_service.smart_volume_scan("binance", 2.0, 2.0, "any", 10)

    assert [r["symbol"] for r in rows] == ["BINANCE:UPUSDT", "BINANCE:DNUSDT"]
    assert rows[0]["trading_recommendation"] == "🚀 STRONG BUY"
    assert rows[1]["trading_recommendation"] == "📉 STRONG SELL"


def test_volume_confirmation_uses_the_real_baseline():
    """3x relative volume on a +5% bar used to read as 1.0x / NORMAL."""
    seen = {}

    def fake_scan(screener, interval, symbols, columns):
        seen["columns"] = list(columns)
        return {symbols[0]: _row(100.0, 105.0, 3_000.0, 3.0)}

    with patch.object(scanner_service, "resilient_scan_columns", side_effect=fake_scan):
        out = scanner_service.volume_confirmation_analyze("BTCUSDT", "BINANCE", "15m")

    assert not is_error(out), out
    assert seen["columns"] == scanner_service._CONFIRMATION_COLUMNS
    assert out["volume_analysis"]["volume_ratio"] == 3.0
    assert out["volume_analysis"]["volume_strength"] == "VERY STRONG"
    assert out["volume_analysis"]["average_volume"] == 1_000.0
    assert any("STRONG BREAKOUT" in s for s in out["signals"])


def test_volume_confirmation_without_baseline_stays_neutral():
    def fake_scan(screener, interval, symbols, columns):
        return {symbols[0]: _row(100.0, 101.0, 3_000.0, None)}

    with patch.object(scanner_service, "resilient_scan_columns", side_effect=fake_scan):
        out = scanner_service.volume_confirmation_analyze("BTCUSDT", "BINANCE", "15m")

    assert not is_error(out), out
    assert out["volume_analysis"]["volume_ratio"] == 1
    assert out["volume_analysis"]["volume_strength"] == "NORMAL"
