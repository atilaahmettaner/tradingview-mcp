"""Issue #76 batch 1: screener/scanner tools return envelopes on EVERY failure.

Before this batch the four screener/scanner tools only translated
``BatchExecutionError``; service entry guards (missing dependency, empty
symbol list) and unexpected exceptions still escaped as raw strings /
tracebacks — exactly the half-migrated state issue #76 calls out. And the
two futures tools referenced ``ErrorCode.SERVICE_ERROR``, an enum member
that never existed, so their error handlers themselves crashed with
``AttributeError`` instead of returning anything.

These tests pin the uniform contract: every failure mode → structured
envelope with a stable ``code`` and an explicit ``retryable`` flag.
All network-free (service functions are monkeypatched at the server
module boundary, matching test_async_handlers.py's pattern).
"""
import asyncio

import pytest

from tradingview_mcp import server
from tradingview_mcp.core.errors import (
    BatchExecutionError,
    ErrorCode,
    ScreenerServiceError,
    exception_to_envelope,
    is_error,
)


def _boom_batch(*args, **kwargs):
    raise BatchExecutionError(batches_attempted=4, batches_failed=4, first_error="JSONDecodeError")


def _boom_no_symbols(*args, **kwargs):
    raise ScreenerServiceError(
        ErrorCode.NO_DATA, "No symbols found for exchange: egx",
        exchange="egx", retryable=False,
    )


def _boom_unexpected(*args, **kwargs):
    raise ValueError("someone divided by a dataframe")


# ── translator unit behavior ───────────────────────────────────────────────────

def test_screener_service_error_is_a_runtime_error():
    # Backward-compat pin: pre-envelope guards raised bare RuntimeError, so
    # external callers with `except RuntimeError` must keep working.
    assert issubclass(ScreenerServiceError, RuntimeError)


def test_translator_maps_batch_error_with_retryable_true():
    exc = BatchExecutionError(batches_attempted=4, batches_failed=4, first_error="x")
    env = exception_to_envelope(exc)
    assert is_error(env)
    assert env["error"]["code"] == "ALL_BATCHES_FAILED"
    assert env["error"]["retryable"] is True
    assert env["error"]["batches_attempted"] == 4


def test_translator_maps_unexpected_to_internal_error_with_context():
    env = exception_to_envelope(ValueError("boom"), context="top_losers")
    assert env["error"]["code"] == "INTERNAL_ERROR"
    assert env["error"]["retryable"] is False
    assert "top_losers" in env["error"]["message"]


# ── tool boundaries: every failure mode returns an envelope ────────────────────

@pytest.mark.parametrize("raiser,expected_code", [
    (_boom_batch, "ALL_BATCHES_FAILED"),
    (_boom_no_symbols, "NO_DATA"),
    (_boom_unexpected, "INTERNAL_ERROR"),
])
def test_top_losers_never_leaks_raw_exceptions(monkeypatch, raiser, expected_code):
    monkeypatch.setattr(server, "fetch_trending_analysis", raiser)
    result = server.top_losers(exchange="KUCOIN")
    assert is_error(result)
    assert result["error"]["code"] == expected_code
    assert "retryable" in result["error"]


@pytest.mark.parametrize("raiser,expected_code", [
    (_boom_no_symbols, "NO_DATA"),
    (_boom_unexpected, "INTERNAL_ERROR"),
])
def test_rating_filter_never_leaks_raw_exceptions(monkeypatch, raiser, expected_code):
    monkeypatch.setattr(server, "fetch_trending_analysis", raiser)
    result = server.rating_filter(exchange="KUCOIN", rating=2)
    assert is_error(result)
    assert result["error"]["code"] == expected_code


def test_bollinger_scan_gains_error_handling(monkeypatch):
    # bollinger_scan previously had NO try/except at all — an upstream blip
    # propagated a raw RuntimeError to the MCP layer.
    def upstream_down(*args, **kwargs):
        raise ScreenerServiceError(
            ErrorCode.UPSTREAM_ERROR,
            "Analysis failed: TradingView data is temporarily unavailable — please retry in a moment.",
            retryable=True,
        )
    monkeypatch.setattr(server, "fetch_bollinger_analysis", upstream_down)
    result = server.bollinger_scan(exchange="KUCOIN")
    assert is_error(result)
    assert result["error"]["code"] == "UPSTREAM_ERROR"
    assert result["error"]["retryable"] is True


def test_smart_volume_scanner_wraps_unexpected(monkeypatch):
    monkeypatch.setattr(server, "smart_volume_scan", _boom_unexpected)
    result = server.smart_volume_scanner(exchange="KUCOIN")
    assert is_error(result)
    assert result["error"]["code"] == "INTERNAL_ERROR"


def test_top_gainers_still_translates_and_marks_retryable(monkeypatch):
    monkeypatch.setattr(server, "fetch_trending_analysis", _boom_batch)
    result = asyncio.run(server.top_gainers(exchange="KUCOIN"))
    assert is_error(result)
    assert result["error"]["code"] == "ALL_BATCHES_FAILED"
    assert result["error"]["retryable"] is True


# ── futures SERVICE_ERROR regression ───────────────────────────────────────────

def test_futures_overview_error_path_returns_envelope_not_attributeerror(monkeypatch):
    # Regression: handler referenced ErrorCode.SERVICE_ERROR (nonexistent),
    # so the except-branch itself raised AttributeError.
    monkeypatch.setattr(server, "get_futures_overview", _boom_unexpected)
    result = server.futures_market_overview()
    assert is_error(result)
    assert result["error"]["code"] == "UPSTREAM_ERROR"
    assert result["error"]["retryable"] is True


def test_futures_movers_error_path_returns_envelope_not_attributeerror(monkeypatch):
    monkeypatch.setattr(server, "get_futures_movers", _boom_unexpected)
    result = server.futures_top_movers(direction="gainers")
    assert is_error(result)
    assert result["error"]["code"] == "UPSTREAM_ERROR"


# ── service entry guards raise typed errors ────────────────────────────────────

def test_fetch_trending_empty_symbol_list_is_typed(monkeypatch):
    from tradingview_mcp.core.services import screener_service
    monkeypatch.setattr(screener_service, "load_symbols", lambda ex: [])
    with pytest.raises(ScreenerServiceError) as exc_info:
        screener_service.fetch_trending_analysis("egx")
    assert exc_info.value.code == ErrorCode.NO_DATA
    assert exc_info.value.extra["exchange"] == "egx"


def test_fetch_bollinger_missing_dependency_is_typed(monkeypatch):
    from tradingview_mcp.core.services import screener_service
    monkeypatch.setattr(screener_service, "_SCREENER_AVAILABLE", False)
    with pytest.raises(ScreenerServiceError) as exc_info:
        screener_service.fetch_bollinger_analysis("kucoin")
    assert exc_info.value.code == ErrorCode.DEPENDENCY_MISSING
    assert exc_info.value.to_envelope()["error"]["retryable"] is False
