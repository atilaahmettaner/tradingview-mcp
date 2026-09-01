"""Partial scans must surface PARTIAL_DATA instead of a plain truncated list.

When the wall-clock budget or the consecutive-failure bail aborted a batched
scan that had already collected rows, the tool returned those rows with no
indication of partiality (the abort reason went only to stderr). Callers could
not distinguish "scanned everything" from "scanned 2 of 8 batches". Services
now raise PartialDataError, which the tool boundary converts to a PARTIAL_DATA
envelope that still carries the rows.
"""
from __future__ import annotations

import asyncio
from json import JSONDecodeError
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tradingview_mcp import server
from tradingview_mcp.core.errors import PartialDataError, exception_to_envelope
from tradingview_mcp.core.services import screener_service


def _good_analysis(symbols):
    ind = {
        "open": 100.0, "close": 110.0, "SMA20": 105.0,
        "BB.upper": 115.0, "BB.lower": 95.0,
        "EMA50": 104.0, "RSI": 55.0, "volume": 1_000.0,
    }
    return {s: SimpleNamespace(indicators=ind) for s in symbols}


def test_consecutive_failure_abort_raises_partial_with_rows(monkeypatch):
    """Batch 1 succeeds, batches 2-4 cliff → PartialDataError carrying batch 1."""
    monkeypatch.setenv("TRADINGVIEW_MCP_BATCH_MAX_CONSECUTIVE_FAILS", "3")
    monkeypatch.setenv("TRADINGVIEW_MCP_BATCH_BUDGET_S", "3600")

    calls = {"n": 0}

    def flaky(screener, interval, symbols):
        calls["n"] += 1
        if calls["n"] == 1:
            return _good_analysis(symbols)
        raise JSONDecodeError("Expecting value", "", 0)

    symbols = [f"SYM{i}" for i in range(1000)]  # 5 batches of 200
    with patch.object(screener_service, "get_multiple_analysis", side_effect=flaky), \
         patch.object(screener_service, "load_symbols", return_value=symbols):
        with pytest.raises(PartialDataError) as exc_info:
            screener_service.fetch_trending_analysis("KUCOIN", timeframe="15m", limit=500)

    err = exc_info.value
    assert len(err.rows) == 200          # batch 1's rows survive
    assert err.batches_attempted == 4    # 1 success + 3 consecutive failures
    assert err.total_batches == 5
    assert "consecutive" in err.aborted_reason


def test_envelope_carries_rows_and_partial_code():
    exc = PartialDataError(
        rows=[{"symbol": "X"}], batches_attempted=2, total_batches=8,
        aborted_reason="wall-clock budget (30s) exhausted",
    )
    env = exception_to_envelope(exc, context="top_gainers")
    assert env["error"]["code"] == "PARTIAL_DATA"
    assert env["error"]["retryable"] is True
    assert env["rows"] == [{"symbol": "X"}]


def test_tool_boundary_returns_partial_envelope(monkeypatch):
    def partial(*args, **kwargs):
        raise PartialDataError(
            rows=[{"symbol": "X", "changePercent": 1.0, "indicators": {}}],
            batches_attempted=2, total_batches=8, aborted_reason="budget",
        )

    monkeypatch.setattr(server, "fetch_trending_analysis", partial)
    result = asyncio.run(server.top_gainers(exchange="KUCOIN"))
    assert result["error"]["code"] == "PARTIAL_DATA"
    assert result["rows"][0]["symbol"] == "X"
