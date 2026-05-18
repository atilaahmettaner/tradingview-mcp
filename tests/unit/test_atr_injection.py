"""Regression tests for the ATR null bug in coin_analysis.

The tradingview_ta library does not expose an "ATR" key in its indicators
payload, which caused atr.value (and every downstream stop/sizing calc) to
collapse to None on every coin_analysis call. fetch_atr_for_ticker patches
the gap by hitting the public scanner endpoint directly.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tradingview_mcp.core.services.screener_provider import fetch_atr_for_ticker


def _mock_response(payload):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = payload
    return resp


class TestFetchAtrForTicker:
    def test_returns_float_when_payload_present(self):
        payload = {"totalCount": 1, "data": [{"s": "BINANCE:BTCUSDT", "d": [2036.4]}]}
        with patch("requests.post", return_value=_mock_response(payload)) as mocked:
            atr = fetch_atr_for_ticker("BINANCE:BTCUSDT", "crypto", "4h")
        assert atr == pytest.approx(2036.4)
        # Confirm we hit the right URL and asked for the timeframe-suffixed column
        args, kwargs = mocked.call_args
        assert args[0].endswith("/crypto/scan")
        assert kwargs["json"]["columns"] == ["ATR|240"]
        assert kwargs["json"]["symbols"]["tickers"] == ["BINANCE:BTCUSDT"]

    def test_omits_suffix_when_no_timeframe(self):
        payload = {"totalCount": 1, "data": [{"s": "NASDAQ:AAPL", "d": [6.24]}]}
        with patch("requests.post", return_value=_mock_response(payload)) as mocked:
            atr = fetch_atr_for_ticker("NASDAQ:AAPL", "america")
        assert atr == pytest.approx(6.24)
        assert mocked.call_args.kwargs["json"]["columns"] == ["ATR"]

    def test_returns_none_on_empty_data(self):
        with patch("requests.post", return_value=_mock_response({"data": []})):
            assert fetch_atr_for_ticker("BINANCE:BTCUSDT", "crypto", "4h") is None

    def test_returns_none_on_missing_value(self):
        payload = {"data": [{"s": "BINANCE:BTCUSDT", "d": [None]}]}
        with patch("requests.post", return_value=_mock_response(payload)):
            assert fetch_atr_for_ticker("BINANCE:BTCUSDT", "crypto", "4h") is None

    def test_returns_none_on_http_error(self):
        bad = MagicMock()
        bad.raise_for_status.side_effect = RuntimeError("boom")
        with patch("requests.post", return_value=bad):
            assert fetch_atr_for_ticker("BINANCE:BTCUSDT", "crypto", "4h") is None

    def test_returns_none_on_blank_inputs(self):
        assert fetch_atr_for_ticker("", "crypto", "4h") is None
        assert fetch_atr_for_ticker("BINANCE:BTCUSDT", "", "4h") is None

    def test_handles_unknown_timeframe(self):
        payload = {"data": [{"d": [1.23]}]}
        with patch("requests.post", return_value=_mock_response(payload)) as mocked:
            atr = fetch_atr_for_ticker("BINANCE:BTCUSDT", "crypto", "7m")
        assert atr == pytest.approx(1.23)
        # Unknown timeframe → no suffix
        assert mocked.call_args.kwargs["json"]["columns"] == ["ATR"]
