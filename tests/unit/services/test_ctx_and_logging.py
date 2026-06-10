"""P5 logging tests — two layers.

1. Client-facing MCP Context logging on the async tools. Because this module
   uses ``from __future__ import annotations``, FastMCP can't inject a
   ``ctx: Context`` parameter (the annotation is a string at runtime), so the
   tools fetch the active context via ``mcp.get_context()``. These tests mock
   ``get_context`` and assert the tool awaits ``ctx.debug`` / ``ctx.warning``,
   and that an unavailable context never breaks the tool.

2. Operator-facing stdlib logging in the service layer. The old
   ``print(file=sys.stderr)`` sites are now ``logger.warning`` calls on the
   ``tradingview_mcp`` hierarchy; these assert they emit via ``caplog``.
"""
from __future__ import annotations

import logging
from json import JSONDecodeError
from types import SimpleNamespace
from unittest import mock

import pytest

from tradingview_mcp import server
from tradingview_mcp.core.errors import BatchExecutionError


# ---------------------------------------------------------------------------
# 1. Client-facing ctx logging on async tools
# ---------------------------------------------------------------------------


async def test_async_tool_emits_debug_entry_trace():
    """A converted async tool traces its invocation to the MCP client."""
    mctx = mock.AsyncMock()
    with mock.patch.object(server.mcp, "get_context", return_value=mctx), \
         mock.patch.object(server, "fetch_trending_analysis", return_value=[]):
        await server.top_gainers(exchange="KUCOIN", timeframe="15m", limit=5)
    mctx.debug.assert_awaited_once()
    assert "top_gainers" in mctx.debug.await_args.args[0]


async def test_yahoo_price_emits_debug_trace():
    mctx = mock.AsyncMock()
    with mock.patch.object(server.mcp, "get_context", return_value=mctx), \
         mock.patch.object(server, "get_price_async", new=mock.AsyncMock(return_value={"price": 1.0})):
        await server.yahoo_price("AAPL")
    mctx.debug.assert_awaited_once()


async def test_batch_failure_warns_client_and_returns_envelope():
    """On a total upstream cliff the tool warns the client AND returns the
    structured error envelope (rather than a bare empty list)."""
    mctx = mock.AsyncMock()
    err = BatchExecutionError(batches_attempted=5, batches_failed=5, first_error="JSONDecodeError(...)")
    with mock.patch.object(server.mcp, "get_context", return_value=mctx), \
         mock.patch.object(server, "fetch_trending_analysis", side_effect=err):
        result = await server.top_gainers(exchange="KUCOIN")
    mctx.warning.assert_awaited_once()
    assert "error" in result and result["error"]["code"] == "ALL_BATCHES_FAILED"


async def test_volume_breakout_scanner_warns_on_batch_failure():
    mctx = mock.AsyncMock()
    err = BatchExecutionError(batches_attempted=3, batches_failed=3, first_error="boom")
    with mock.patch.object(server.mcp, "get_context", return_value=mctx), \
         mock.patch.object(server, "volume_breakout_scan", side_effect=err):
        result = await server.volume_breakout_scanner(exchange="KUCOIN")
    mctx.warning.assert_awaited_once()
    assert result["error"]["code"] == "ALL_BATCHES_FAILED"


async def test_tool_survives_unavailable_context():
    """Outside a request ``get_context`` yields a session-less context whose
    log call raises; the tool must still return its result."""
    with mock.patch.object(server.mcp, "get_context", side_effect=RuntimeError("no active request")), \
         mock.patch.object(server, "fetch_trending_analysis", return_value=[]):
        result = await server.top_gainers(exchange="KUCOIN")
    assert result == []


# ---------------------------------------------------------------------------
# 2. Operator-facing service-layer logging (caplog)
# ---------------------------------------------------------------------------


def test_scan_with_retry_logs_transient_warning(monkeypatch, caplog):
    """Transient scanner errors are logged via the ``tradingview_mcp`` logger
    (previously a stderr print)."""
    from tradingview_mcp.core.services import screener_provider as sp

    # One immediate attempt, no backoff sleeps → fast + deterministic.
    monkeypatch.setattr(sp, "_retry_delays", lambda: ())

    class FailingQuery:
        def get_scanner_data(self, cookies=None):
            raise JSONDecodeError("Expecting value", "", 0)

    with caplog.at_level(logging.WARNING, logger="tradingview_mcp"):
        with pytest.raises(JSONDecodeError):
            sp._scan_with_retry(FailingQuery())

    assert any("transient scanner error" in r.message for r in caplog.records)


def test_volume_breakout_scan_logs_batch_warning(caplog):
    from tradingview_mcp.core.services import scanner_service

    def always_fail(*_a, **_k):
        raise JSONDecodeError("Expecting value", "", 0)

    with caplog.at_level(logging.WARNING, logger="tradingview_mcp"):
        with mock.patch.object(scanner_service, "get_multiple_analysis", side_effect=always_fail), \
             mock.patch.object(scanner_service, "load_symbols", return_value=[f"S{i}" for i in range(150)]):
            with pytest.raises(BatchExecutionError):
                scanner_service.volume_breakout_scan(exchange="KUCOIN", timeframe="15m")

    assert any("volume_breakout_scan batch" in r.message for r in caplog.records)


def test_fetch_trending_analysis_logs_batch_warning(caplog):
    from tradingview_mcp.core.services import screener_service

    def always_fail(*_a, **_k):
        raise JSONDecodeError("Expecting value", "", 0)

    with caplog.at_level(logging.WARNING, logger="tradingview_mcp"):
        with mock.patch.object(screener_service, "get_multiple_analysis", side_effect=always_fail), \
             mock.patch.object(screener_service, "load_symbols", return_value=[f"S{i}" for i in range(250)]):
            with pytest.raises(BatchExecutionError):
                screener_service.fetch_trending_analysis(exchange="KUCOIN", timeframe="15m")

    assert any("fetch_trending_analysis batch" in r.message for r in caplog.records)
