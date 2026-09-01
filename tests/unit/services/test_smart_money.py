"""Unit tests for the smart-money / banker-fund proxy service.

Synthetic-candle fixtures with unambiguous accumulation vs distribution
character, plus tool-boundary envelope checks. No network.
"""
from __future__ import annotations

from unittest.mock import patch

from tradingview_mcp.core.services import smart_money_service as sm


def _candle(date, o, h, l, c, v):
    return {"date": date, "open": o, "high": h, "low": l, "close": c, "volume": v}


def _accumulation_candles(n=120):
    """Steady uptrend: closes near the top of each bar on rising volume."""
    out = []
    price = 100.0
    for i in range(n):
        o = price
        c = price * 1.01
        h = c * 1.002        # close lands near the high
        lo = o * 0.995
        out.append(_candle(f"d{i}", o, h, lo, c, 1_000 + i * 50))
        price = c
    return out


def _distribution_candles(n=120):
    """Steady downtrend: closes near the low of each bar on rising volume."""
    out = []
    price = 100.0
    for i in range(n):
        o = price
        c = price * 0.99
        lo = c * 0.998       # close lands near the low
        h = o * 1.005
        out.append(_candle(f"d{i}", o, h, lo, c, 1_000 + i * 50))
        price = c
    return out


class TestComputations:
    def test_composite_separates_accumulation_from_distribution(self):
        acc = sm.compute_smart_money_composite(_accumulation_candles())
        dist = sm.compute_smart_money_composite(_distribution_candles())
        assert acc["score"] >= 70 and acc["verdict"] == "STRONG_ACCUMULATION"
        assert dist["score"] <= 30 and dist["verdict"] == "STRONG_DISTRIBUTION"

    def test_mcdx_banker_high_in_persistent_uptrend(self):
        mcdx = sm.compute_mcdx(_accumulation_candles())
        assert mcdx["banker"] is not None and mcdx["banker"] > 10
        # A monotonic melt-up pins every horizon → must not read as fresh
        # banker-only accumulation.
        assert mcdx["signal"] in ("CROWDED", "BANKER_ACCUMULATING")

    def test_mcdx_banker_floors_at_zero_in_downtrend(self):
        mcdx = sm.compute_mcdx(_distribution_candles())
        assert mcdx["banker"] == 0.0

    def test_oscillator_high_in_uptrend_low_in_downtrend(self):
        up = sm.compute_banker_fund_oscillator(_accumulation_candles())
        down = sm.compute_banker_fund_oscillator(_distribution_candles())
        assert up["oscillator"] > 70
        assert down["oscillator"] < 30
        assert up["state"] in ("TREND", "OVERHEATED")
        assert down["state"] in ("OVERSOLD", "COOLING")


class TestYahooSymbolMapping:
    def test_egx_maps_to_ca_suffix(self):
        assert sm.yahoo_symbol_for("COMI", "EGX") == "COMI.CA"
        assert sm.yahoo_symbol_for("comi", "egx") == "COMI.CA"

    def test_existing_suffixes_and_special_forms_pass_through(self):
        assert sm.yahoo_symbol_for("THYAO.IS", "BIST") == "THYAO.IS"
        assert sm.yahoo_symbol_for("BTC-USD", "EGX") == "BTC-USD"
        assert sm.yahoo_symbol_for("^GSPC", "EGX") == "^GSPC"

    def test_non_mapped_exchange_passes_through(self):
        assert sm.yahoo_symbol_for("AAPL", "NASDAQ") == "AAPL"


class TestAnalyzeSmartMoney:
    def test_invalid_period_returns_envelope(self):
        r = sm.analyze_smart_money("COMI", "EGX", period="5y")
        assert r["error"]["code"] == "INVALID_PARAMETER"
        assert "6mo" in r["error"]["valid_periods"]

    def test_fetch_failure_returns_upstream_envelope(self):
        with patch.object(sm, "_fetch_ohlcv", side_effect=RuntimeError("404")):
            r = sm.analyze_smart_money("COMI", "EGX")
        assert r["error"]["code"] == "UPSTREAM_ERROR"
        assert r["error"]["yahoo_symbol"] == "COMI.CA"

    def test_too_few_bars_returns_no_data(self):
        with patch.object(sm, "_fetch_ohlcv", return_value=_accumulation_candles(10)):
            r = sm.analyze_smart_money("COMI", "EGX")
        assert r["error"]["code"] == "NO_DATA"

    def test_full_payload_shape_and_consensus(self):
        with patch.object(sm, "_fetch_ohlcv", return_value=_accumulation_candles()):
            r = sm.analyze_smart_money("COMI", "EGX", period="6mo")
        assert r["yahoo_symbol"] == "COMI.CA"
        assert r["consensus"]["read"] in ("SMART_MONEY_IN", "NEUTRAL", "MIXED")
        assert "methodology_note" in r  # honesty note must always ship
        for key in ("mcdx_style", "banker_fund_oscillator", "volume_flow_composite"):
            assert key in r


class TestEgxScanner:
    def test_unknown_index_errors_with_valid_list(self):
        r = sm.scan_egx_smart_money(index="EGX999")
        assert r["error"]["code"] == "INVALID_PARAMETER"
        assert "EGX30" in r["error"]["valid_indices"]

    def test_scan_ranks_and_reports_skips(self):
        def fake_analyze(symbol, exchange, period, interval):
            if symbol == "BAD":
                return {"error": {"code": "NO_DATA", "message": "no bars"}}
            score = {"AAA": 80.0, "BBB": 60.0, "CCC": 20.0}[symbol]
            return {
                "last_close": 10.0, "as_of": "d1",
                "volume_flow_composite": {"score": score, "verdict": "X"},
                "mcdx_style": {"banker": 5.0, "signal": "NEUTRAL"},
                "banker_fund_oscillator": {"oscillator": 50.0, "state": "TREND"},
                "consensus": {"read": "NEUTRAL"},
            }

        fake_index = {"EGX30": {"get_symbols": lambda: ["EGX:AAA", "EGX:BBB", "EGX:CCC", "EGX:BAD"]}}
        with patch.object(sm, "analyze_smart_money", side_effect=fake_analyze), \
             patch("tradingview_mcp.core.data.egx_indices.EGX_INDICES", fake_index):
            r = sm.scan_egx_smart_money(index="EGX30", limit=2, min_score=30.0)

        assert [row["symbol"] for row in r["rows"]] == ["AAA", "BBB"]  # ranked, min_score drops CCC
        assert r["skipped"] == [{"symbol": "BAD", "reason": "no bars"}]
        assert r["constituents_scanned"] == 4
