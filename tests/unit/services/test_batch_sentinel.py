"""Batch sentinel integration tests.

When 100% of upstream batches fail, batched scanners must raise
``BatchExecutionError`` instead of silently returning ``[]``. The empty list
used to hide rate-limit cliffs as "no matches today"; the sentinel makes the
failure mode explicit so tool wrappers can convert it to a structured error
envelope at the MCP boundary.
"""
from __future__ import annotations

from json import JSONDecodeError
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from tradingview_mcp.core.errors import BatchExecutionError


# --- Helpers ----------------------------------------------------------------

class _FakeAnalysis(SimpleNamespace):
    """Minimal stand-in for ``tradingview_ta`` analysis objects.

    Only exposes the ``indicators`` attribute the scanners read. Values are
    intentionally chosen so the per-symbol filter logic passes/fails as needed.
    """


def _good_indicators() -> dict[str, Any]:
    """Indicators that comfortably clear ``volume_breakout_scan`` defaults
    (volume_multiplier=2.0, price_change_min=3.0)."""
    return {
        "volume": 10_000.0,
        "close": 110.0,
        "open": 100.0,        # +10% bar — well above the 3.0% threshold
        "volume.SMA20": 1_000.0,  # 10x avg — well above the 2x threshold
        "RSI": 55.0,
        "BB.upper": 115.0,
        "BB.lower": 95.0,
    }


def _make_batch_response(symbols: list[str]) -> dict:
    """Map ``EXCHANGE:SYMBOL`` -> fake analysis object."""
    return {s: _FakeAnalysis(indicators=_good_indicators()) for s in symbols}


# --- Tests for volume_breakout_scan -----------------------------------------

class TestVolumeBreakoutScanSentinel:
    def test_all_batches_fail_raises(self, monkeypatch):
        """When every batch raises, the sentinel must fire."""
        from tradingview_mcp.core.services import scanner_service

        # Disable fast-fail for this test so we can verify the sentinel
        # behaviour at the "every batch tried, every batch failed" end of
        # the spectrum. Fast-fail's own behaviour is covered by
        # ``test_fast_fail_aborts_after_consecutive_failures`` below.
        monkeypatch.setenv("TRADINGVIEW_MCP_BATCH_MAX_CONSECUTIVE_FAILS", "999")
        monkeypatch.setenv("TRADINGVIEW_MCP_BATCH_BUDGET_S", "3600")

        def always_fail(*_args, **_kwargs):
            # Mirrors the real upstream "empty body" failure mode.
            raise JSONDecodeError("Expecting value", "", 0)

        with patch.object(scanner_service, "get_multiple_analysis", side_effect=always_fail), \
             patch.object(scanner_service, "load_symbols", return_value=[f"SYM{i}" for i in range(250)]):
            with pytest.raises(BatchExecutionError) as exc_info:
                scanner_service.volume_breakout_scan(
                    exchange="KUCOIN",
                    timeframe="15m",
                )

        # batch_size=100 over 250 symbols => 3 batches attempted (100, 100, 50)
        assert exc_info.value.batches_attempted == 3
        assert exc_info.value.batches_failed == 3
        assert "Expecting value" in exc_info.value.first_error

    def test_fast_fail_aborts_after_consecutive_failures(self, monkeypatch):
        """Fast-fail must bail after N consecutive batch failures so the tool
        returns in bounded time instead of grinding through every batch with
        15s cooldown each."""
        from tradingview_mcp.core.services import scanner_service

        monkeypatch.setenv("TRADINGVIEW_MCP_BATCH_MAX_CONSECUTIVE_FAILS", "2")
        monkeypatch.setenv("TRADINGVIEW_MCP_BATCH_BUDGET_S", "3600")

        call_count = {"n": 0}

        def always_fail(*_args, **_kwargs):
            call_count["n"] += 1
            raise JSONDecodeError("Expecting value", "", 0)

        with patch.object(scanner_service, "get_multiple_analysis", side_effect=always_fail), \
             patch.object(scanner_service, "load_symbols", return_value=[f"SYM{i}" for i in range(500)]):
            # batch_size=100 over 500 symbols would normally be 5 batches,
            # but fast-fail should stop us at 2.
            with pytest.raises(BatchExecutionError) as exc_info:
                scanner_service.volume_breakout_scan(exchange="KUCOIN", timeframe="15m")

        assert call_count["n"] == 2, (
            f"Expected fast-fail to stop at 2 consecutive failures; got "
            f"{call_count['n']} calls to upstream."
        )
        assert exc_info.value.batches_attempted == 2
        assert exc_info.value.batches_failed == 2

    def test_partial_success_does_not_trigger_fast_fail(self, monkeypatch):
        """A successful batch resets the consecutive-failure counter."""
        from tradingview_mcp.core.services import scanner_service

        monkeypatch.setenv("TRADINGVIEW_MCP_BATCH_MAX_CONSECUTIVE_FAILS", "2")
        monkeypatch.setenv("TRADINGVIEW_MCP_BATCH_BUDGET_S", "3600")

        # Pattern: fail, succeed, fail, succeed, fail — never 2 in a row.
        call_log = []

        def alternating(*, screener, interval, symbols):
            call_log.append(len(symbols))
            if len(call_log) % 2 == 1:
                raise JSONDecodeError("Expecting value", "", 0)
            return _make_batch_response(symbols)

        with patch.object(scanner_service, "get_multiple_analysis", side_effect=alternating), \
             patch.object(scanner_service, "load_symbols", return_value=[f"SYM{i}" for i in range(500)]):
            # 500 symbols / 100 = 5 batches. Failures alternate, so no two
            # are consecutive → fast-fail must NOT trip → all 5 attempted.
            result = scanner_service.volume_breakout_scan(exchange="KUCOIN", timeframe="15m")

        assert len(call_log) == 5, (
            f"Expected all 5 batches attempted (alternating failures); got "
            f"{len(call_log)}."
        )
        # 3 failed, 2 succeeded → not all-fail → returns list (not raise).
        assert isinstance(result, list)

    def test_all_succeed_returns_list_no_raise(self):
        """Happy path: every batch returns data, no sentinel."""
        from tradingview_mcp.core.services import scanner_service

        def all_good(*, screener, interval, symbols):
            return _make_batch_response(symbols)

        with patch.object(scanner_service, "get_multiple_analysis", side_effect=all_good), \
             patch.object(scanner_service, "load_symbols", return_value=[f"SYM{i}" for i in range(150)]):
            result = scanner_service.volume_breakout_scan(
                exchange="KUCOIN",
                timeframe="15m",
                limit=10,
            )

        assert isinstance(result, list)
        assert len(result) <= 10
        assert len(result) > 0  # Our fake indicators trip the filter
        for row in result:
            assert "symbol" in row
            assert "breakout_type" in row

    def test_partial_failure_no_raise(self):
        """If at least one batch succeeds, return whatever we got — no sentinel."""
        from tradingview_mcp.core.services import scanner_service

        call_count = {"n": 0}

        def first_fails_rest_ok(*, screener, interval, symbols):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise JSONDecodeError("Expecting value", "", 0)
            return _make_batch_response(symbols)

        with patch.object(scanner_service, "get_multiple_analysis", side_effect=first_fails_rest_ok), \
             patch.object(scanner_service, "load_symbols", return_value=[f"SYM{i}" for i in range(250)]):
            # Must NOT raise — partial success is success.
            result = scanner_service.volume_breakout_scan(
                exchange="KUCOIN",
                timeframe="15m",
                limit=200,
            )

        assert isinstance(result, list)
        # Batches 2 and 3 succeeded (100 + 50 symbols).
        assert len(result) > 0

    def test_empty_symbol_list_returns_empty_no_raise(self):
        """No symbols loaded => no batches attempted => no sentinel (early return)."""
        from tradingview_mcp.core.services import scanner_service

        with patch.object(scanner_service, "load_symbols", return_value=[]):
            result = scanner_service.volume_breakout_scan(exchange="UNKNOWN")

        assert result == []


# --- Tests for fetch_trending_analysis --------------------------------------

class TestFetchTrendingAnalysisSentinel:
    def test_all_batches_fail_raises(self):
        from tradingview_mcp.core.services import screener_service

        def always_fail(*_args, **_kwargs):
            raise JSONDecodeError("Expecting value", "", 0)

        # batch_size=200, so 250 symbols => 2 batches attempted.
        with patch.object(screener_service, "get_multiple_analysis", side_effect=always_fail), \
             patch.object(screener_service, "load_symbols", return_value=[f"S{i}" for i in range(250)]):
            with pytest.raises(BatchExecutionError) as exc_info:
                screener_service.fetch_trending_analysis(exchange="KUCOIN", timeframe="15m")

        assert exc_info.value.batches_attempted == 2
        assert exc_info.value.batches_failed == 2

    def test_partial_failure_no_raise(self):
        from tradingview_mcp.core.services import screener_service

        call_count = {"n": 0}

        def second_fails(*, screener, interval, symbols):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise JSONDecodeError("Expecting value", "", 0)
            # First batch returns rich enough data for compute_metrics to pass.
            return {
                f"KUCOIN:{s}": _FakeAnalysis(
                    indicators={
                        "open": 100.0,
                        "close": 110.0,
                        "high": 112.0,
                        "low": 99.0,
                        "BB.upper": 115.0,
                        "BB.lower": 95.0,
                        "SMA20": 105.0,
                        "EMA50": 100.0,
                        "RSI": 55.0,
                        "volume": 1_000_000.0,
                        "Recommend.All": 0.2,
                    }
                )
                for s in symbols
            }

        with patch.object(screener_service, "get_multiple_analysis", side_effect=second_fails), \
             patch.object(screener_service, "load_symbols", return_value=[f"S{i}" for i in range(250)]):
            result = screener_service.fetch_trending_analysis(exchange="KUCOIN", timeframe="15m", limit=300)

        assert isinstance(result, list)
        # First batch (200 symbols) survived; second batch failure was swallowed
        # because at least one batch succeeded.
        assert len(result) > 0
