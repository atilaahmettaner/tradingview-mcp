"""Regression tests for the ATR null bug in coin_analysis / egx_service.

The tradingview_ta library does not expose an "ATR" key in its indicators
payload, which caused atr.value (and every downstream stop/sizing calc) to
collapse to None on every coin_analysis / EGX call. The two helpers below
patch the gap by hitting the public scanner endpoint directly — once per
ticker for the single helper, once per batch for the plural helper that
``analyze_egx_index`` uses on 200-symbol passes.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tradingview_mcp.core.services.screener_provider import (
    fetch_atr_for_ticker,
    fetch_atr_for_tickers,
)


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
        payload = {"data": [{"s": "BINANCE:BTCUSDT", "d": [1.23]}]}
        with patch("requests.post", return_value=_mock_response(payload)) as mocked:
            atr = fetch_atr_for_ticker("BINANCE:BTCUSDT", "crypto", "7m")
        assert atr == pytest.approx(1.23)
        assert mocked.call_args.kwargs["json"]["columns"] == ["ATR"]

    def test_daily_uses_bare_atr_column(self):
        # Scanner exposes daily ATR as bare "ATR" — asking for "ATR|1D" returns null.
        # Verified live against crypto/scan and egypt/scan during dev test.
        payload = {"data": [{"s": "BINANCE:BTCUSDT", "d": [2106.30]}]}
        with patch("requests.post", return_value=_mock_response(payload)) as mocked:
            atr = fetch_atr_for_ticker("BINANCE:BTCUSDT", "crypto", "1D")
        assert atr == pytest.approx(2106.30)
        assert mocked.call_args.kwargs["json"]["columns"] == ["ATR"]

    def test_weekly_keeps_its_suffix(self):
        # Regression — weekly ATR DOES use a suffix ("ATR|1W").
        payload = {"data": [{"s": "BINANCE:BTCUSDT", "d": [7017.78]}]}
        with patch("requests.post", return_value=_mock_response(payload)) as mocked:
            atr = fetch_atr_for_ticker("BINANCE:BTCUSDT", "crypto", "1W")
        assert atr == pytest.approx(7017.78)
        assert mocked.call_args.kwargs["json"]["columns"] == ["ATR|1W"]


class TestFetchAtrForTickers:
    """Plural helper — same scanner endpoint, one POST for many tickers."""

    def test_maps_results_by_symbol(self):
        payload = {
            "totalCount": 3,
            "data": [
                {"s": "EGX:COMI", "d": [1.45]},
                {"s": "EGX:HRHO", "d": [0.82]},
                {"s": "EGX:EAST", "d": [3.10]},
            ],
        }
        tickers = ["EGX:COMI", "EGX:HRHO", "EGX:EAST"]
        # Use 4h so the suffix is preserved (1D drops the suffix — covered in
        # test_daily_uses_bare_atr_column).
        with patch("requests.post", return_value=_mock_response(payload)) as mocked:
            atr = fetch_atr_for_tickers(tickers, "egypt", "4h")

        assert atr == {
            "EGX:COMI": pytest.approx(1.45),
            "EGX:HRHO": pytest.approx(0.82),
            "EGX:EAST": pytest.approx(3.10),
        }
        # All tickers go in a single POST
        kwargs = mocked.call_args.kwargs
        assert kwargs["json"]["symbols"]["tickers"] == tickers
        assert kwargs["json"]["columns"] == ["ATR|240"]
        assert mocked.call_count == 1

    def test_missing_tickers_in_response_get_none(self):
        # Scanner returned only 2 of the 3 requested tickers
        payload = {
            "data": [
                {"s": "EGX:COMI", "d": [1.45]},
                {"s": "EGX:EAST", "d": [3.10]},
            ]
        }
        with patch("requests.post", return_value=_mock_response(payload)):
            atr = fetch_atr_for_tickers(["EGX:COMI", "EGX:HRHO", "EGX:EAST"], "egypt", "1D")
        assert atr["EGX:COMI"] == pytest.approx(1.45)
        assert atr["EGX:HRHO"] is None
        assert atr["EGX:EAST"] == pytest.approx(3.10)

    def test_returns_all_none_on_empty_input(self):
        with patch("requests.post") as mocked:
            assert fetch_atr_for_tickers([], "egypt", "1D") == {}
            assert mocked.call_count == 0  # No request fired

    def test_returns_all_none_on_http_error(self):
        bad = MagicMock()
        bad.raise_for_status.side_effect = RuntimeError("boom")
        with patch("requests.post", return_value=bad):
            atr = fetch_atr_for_tickers(["EGX:COMI", "EGX:HRHO"], "egypt", "1D")
        assert atr == {"EGX:COMI": None, "EGX:HRHO": None}

    def test_returns_all_none_on_blank_screener(self):
        with patch("requests.post") as mocked:
            atr = fetch_atr_for_tickers(["EGX:COMI", "EGX:HRHO"], "", "1D")
        assert atr == {"EGX:COMI": None, "EGX:HRHO": None}
        assert mocked.call_count == 0

    def test_handles_invalid_value_per_row(self):
        # One row has a non-numeric value — only that ticker degrades to None
        payload = {
            "data": [
                {"s": "EGX:COMI", "d": [1.45]},
                {"s": "EGX:HRHO", "d": ["NaN"]},
            ]
        }
        with patch("requests.post", return_value=_mock_response(payload)):
            atr = fetch_atr_for_tickers(["EGX:COMI", "EGX:HRHO"], "egypt", "1D")
        assert atr["EGX:COMI"] == pytest.approx(1.45)
        assert atr["EGX:HRHO"] is None
