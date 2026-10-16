"""The tradingview_ta-based tools see a real volume baseline.

TradingView has no volume-SMA column, so the "volume.SMA20" these divided by was
never there. That hit coin_analysis and multi_timeframe_analysis (volume ratio
null, signal always "Normal", no volume line in the timeframe context), the
stock score and trade quality (volume and liquidity points always 0), and the
EGX tools (sector flow always "Inflow", no liquidity filter, no Fibonacci
volume ratio). The TA fetch now asks for TradingView's relative and average
volume.
"""
from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tradingview_mcp.core.services import egx_service, indicators
from tradingview_mcp.core.services import screener_provider as sp


@pytest.fixture(autouse=True)
def _reset_cache():
    with sp._SCREENER_CACHE_LOCK:
        sp._SCREENER_CACHE.clear()
    yield
    with sp._SCREENER_CACHE_LOCK:
        sp._SCREENER_CACHE.clear()


def _ind(**overrides) -> dict:
    """A +3% bar with enough fields for compute_metrics and the score helpers."""
    ind = {
        "open": 100.0, "close": 103.0, "high": 104.0, "low": 99.0, "volume": 5_000.0,
        "SMA20": 100.0, "BB.upper": 110.0, "BB.lower": 90.0,
        "EMA20": 101.0, "EMA50": 98.0, "EMA200": 95.0, "RSI": 55.0,
    }
    ind.update(overrides)
    return ind


# ── the fetch ───────────────────────────────────────────────────────────────

def test_ta_fetch_requests_the_volume_columns(monkeypatch):
    seen = {}

    def fake_gma(screener, interval, symbols, additional_indicators=(), timeout=None, **kwargs):
        seen["additional"] = list(additional_indicators)
        return {symbols[0]: SimpleNamespace(indicators={})}

    fake_module = types.ModuleType("tradingview_ta")
    fake_module.get_multiple_analysis = fake_gma
    monkeypatch.setitem(sys.modules, "tradingview_ta", fake_module)
    monkeypatch.setenv("TRADINGVIEW_MCP_MIN_INTERVAL_S", "0")

    sp.resilient_get_multiple_analysis("america", "1D", ["NASDAQ:AAPL"])

    assert seen["additional"] == ["relative_volume_10d_calc", "average_volume_10d_calc"]


# ── shared indicator helpers (coin_analysis, multi_timeframe_analysis) ─────

def test_volume_analysis_reads_relative_volume():
    vol = indicators.extract_extended_indicators(
        _ind(relative_volume_10d_calc=2.5, average_volume_10d_calc=2_000.0)
    )["volume"]
    assert vol["ratio"] == 2.5
    assert vol["signal"] == "High"
    assert vol["average_10"] == 2000
    assert vol["average_20"] is None  # key kept for clients; no 20-bar average exists


def test_volume_analysis_without_baseline_stays_normal():
    vol = indicators.extract_extended_indicators(_ind())["volume"]
    assert vol["ratio"] is None
    assert vol["signal"] == "Normal"


def test_timeframe_context_mentions_volume():
    daily = indicators.analyze_timeframe_context(_ind(relative_volume_10d_calc=1.8), "1D")
    hourly = indicators.analyze_timeframe_context(_ind(relative_volume_10d_calc=2.5), "1h")
    quiet = indicators.analyze_timeframe_context(_ind(relative_volume_10d_calc=0.9), "1D")
    assert any("Volume 1.8x above average" in r for r in daily["bias_reasons"])
    assert any("Volume spike: 2.5x" in r for r in hourly["bias_reasons"])
    assert not any("Volume" in r for r in quiet["bias_reasons"])


def test_stock_score_awards_volume_points():
    strong = indicators.compute_stock_score(_ind(relative_volume_10d_calc=1.6))
    missing = indicators.compute_stock_score(_ind())
    assert strong["breakdown"]["volume_confirmation"] == 10
    assert missing["breakdown"]["volume_confirmation"] == 0


def test_trade_quality_volume_and_liquidity_points():
    setup = {"resistances": [], "stop_distance_pct": 3.0, "risk_reward": {}}
    quality = indicators.compute_trade_quality(
        _ind(relative_volume_10d_calc=1.6, average_volume_10d_calc=600_000.0), setup
    )
    assert quality["breakdown"]["volume_confirmation"] == 20
    assert quality["breakdown"]["liquidity"] == 10


# ── EGX tools ───────────────────────────────────────────────────────────────

def _analysis(symbols, **overrides) -> dict:
    return {s: SimpleNamespace(indicators=_ind(**overrides)) for s in symbols}


@pytest.mark.parametrize("relative_volume, expected", [(0.5, "Outflow"), (2.0, "Inflow")])
def test_egx_sector_flow_follows_relative_volume(relative_volume, expected):
    """Every sector used to read "Inflow": the flow was raw volume minus 0."""
    def fake(screener, interval, symbols):
        return _analysis(symbols, relative_volume_10d_calc=relative_volume)

    with patch.object(egx_service, "get_multiple_analysis", side_effect=fake):
        out = egx_service.run_egx_sector_scanner()

    signals = {row["volume_flow"]["signal"] for row in out["sector_heatmap"]}
    assert signals - {"N/A"} == {expected}


def test_egx_screener_liquidity_uses_average_volume():
    def fake(screener, interval, symbols):
        return {
            "EGX:THIN": SimpleNamespace(indicators=_ind(average_volume_10d_calc=5_000.0)),
            "EGX:DEEP": SimpleNamespace(indicators=_ind(average_volume_10d_calc=50_000.0)),
        }

    with patch.object(egx_service, "get_multiple_analysis", side_effect=fake), \
         patch.object(egx_service, "load_symbols", return_value=["EGX:THIN", "EGX:DEEP"]):
        out = egx_service.screen_egx_stocks(min_score=0, limit=10)

    status = {s["symbol"]: s["liquidity_status"] for s in out["qualified_trades"] + out["watchlist"]}
    assert status == {"EGX:THIN": "Fail — Very Low", "EGX:DEEP": "Pass"}


def test_egx_fibonacci_reports_relative_volume(monkeypatch):
    monkeypatch.setattr(egx_service, "_SCREENER_AVAILABLE", False)  # use the pivot fallback
    ind = _ind(relative_volume_10d_calc=1.7, ATR=2.0, **{
        "Pivot.M.Fibonacci.R3": 130.0, "Pivot.M.Fibonacci.S3": 80.0,
    })
    with patch.object(egx_service, "get_multiple_analysis",
                      return_value={"EGX:COMI": SimpleNamespace(indicators=ind)}):
        out = egx_service.analyze_egx_fibonacci("COMI")

    assert out["context"]["volume_ratio"] == 1.7
