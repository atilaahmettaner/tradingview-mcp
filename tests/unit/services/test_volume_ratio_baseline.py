"""Regression tests for the volume-ratio baseline fallback bug.

When a symbol had no volume baseline column, ``volume_breakout_scan`` used
``volume / (volume / 2)`` as its ratio — mathematically always exactly 2.0.
With the default ``volume_multiplier=2.0`` gate that meant every baseline-less
symbol "passed" on price change alone, flooding the scan with breakouts that
carried no volume signal. Symbols without a baseline must be skipped instead.

The ratio is ``relative_volume_10d_calc`` (volume over the mean of the
previous 10 bars). The old ``volume.SMA20`` column was never fetched, so every
symbol was skipped.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

from tradingview_mcp.core.services import scanner_service


def _indicators(relative_volume: Any) -> dict[str, Any]:
    """A +10% bar (clears price_change_min=3.0) with a configurable baseline."""
    return {
        "volume": 10_000.0,
        "close": 110.0,
        "open": 100.0,
        "relative_volume_10d_calc": relative_volume,
        "RSI": 55.0,
        "BB.upper": 115.0,
        "BB.lower": 95.0,
    }


def _scan(analysis: dict) -> list[dict]:
    with patch.object(scanner_service, "resilient_scan_columns",
                      return_value=analysis), \
         patch.object(scanner_service, "load_symbols",
                      return_value=list(analysis)):
        return scanner_service.volume_breakout_scan("KUCOIN", "15m")


def test_symbol_without_volume_baseline_is_skipped():
    """No volume baseline → no volume signal → must not appear as a breakout."""
    analysis = {
        "NOBASE": _indicators(relative_volume=None),
        "ZEROBASE": _indicators(relative_volume=0.0),
    }
    assert _scan(analysis) == []


def test_symbol_with_real_volume_spike_still_detected():
    analysis = {
        "REAL": _indicators(relative_volume=10.0),
        "QUIET": _indicators(relative_volume=1.1),
    }
    rows = _scan(analysis)
    assert [r["symbol"] for r in rows] == ["REAL"]
    assert rows[0]["volume_ratio"] == 10.0
