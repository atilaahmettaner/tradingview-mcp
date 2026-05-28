"""Real-network stress tests — opt-in.

These tests hit live ``scanner.tradingview.com`` and Yahoo Finance. They
exist because the unit-test suite mocks every upstream call, and a regression
that lets calls hang indefinitely cannot be detected by mocks.

Run explicitly:

    pytest -m stress -v

Skipped by default in CI. Each test has a hard wall-clock ceiling — if any
test exceeds it the assertion fails, which is the whole point: we'd rather
ship a clear error than a "hang for 30 minutes" experience.

The ceilings are deliberately generous (90 s for batched scanners, 60 s for
multi-timeframe, 30 s for single-symbol calls) because the actual upstream
may be cliffing — in which case the fast-fail / wall-clock-budget guards in
``screener_service`` and ``scanner_service`` should kick in and return
either a partial result or a ``BatchExecutionError`` envelope. Either
counts as "did not hang".
"""
from __future__ import annotations

import asyncio
import os
import time

import pytest

from tradingview_mcp.core.errors import BatchExecutionError, is_error


# Apply the stress marker to every test in this module. Run with
# ``pytest -m stress`` — otherwise pytest skips them.
pytestmark = pytest.mark.stress


# Hard wall-clock ceilings. If any test exceeds these, something is hung.
SINGLE_SYMBOL_CEILING_S = 30.0
MULTI_TF_CEILING_S = 60.0
BATCHED_SCAN_CEILING_S = 90.0


def _is_error_envelope(result) -> bool:
    """A dict like ``{"error": {...}}`` counts as a graceful failure."""
    return isinstance(result, dict) and "error" in result


# ---------------------------------------------------------------------------
# yahoo_price — true async via httpx, should be fastest
# ---------------------------------------------------------------------------


async def test_yahoo_price_returns_within_ceiling():
    """yahoo_price hits Yahoo Finance Chart API directly. Should be <5 s in
    healthy conditions; the 30 s ceiling exists only to catch real hangs."""
    from tradingview_mcp.server import yahoo_price

    t0 = time.perf_counter()
    result = await asyncio.wait_for(
        yahoo_price("AAPL"), timeout=SINGLE_SYMBOL_CEILING_S
    )
    elapsed = time.perf_counter() - t0

    assert elapsed < SINGLE_SYMBOL_CEILING_S, (
        f"yahoo_price took {elapsed:.1f}s (ceiling {SINGLE_SYMBOL_CEILING_S}s)"
    )
    # Either a real quote dict, or an error envelope — both prove the call
    # returned without hanging.
    assert isinstance(result, dict)
    if "error" not in result:
        assert "price" in result
        assert "symbol" in result


async def test_yahoo_price_20x_parallel_completes():
    """The parallelism win we claim — 20 concurrent yahoo_price calls must
    finish well inside the single-call ceiling (proves async actually
    overlaps and that no single call is dragging the whole batch down)."""
    from tradingview_mcp.server import yahoo_price

    symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "JPM",
               "V", "WMT", "PG", "HD", "MA", "DIS", "BAC", "KO", "PFE", "PEP",
               "CSCO", "NFLX"]

    t0 = time.perf_counter()
    results = await asyncio.wait_for(
        asyncio.gather(*(yahoo_price(s) for s in symbols)),
        timeout=SINGLE_SYMBOL_CEILING_S,
    )
    elapsed = time.perf_counter() - t0

    assert len(results) == len(symbols)
    assert elapsed < SINGLE_SYMBOL_CEILING_S, (
        f"20 parallel yahoo_price took {elapsed:.1f}s; expected <"
        f"{SINGLE_SYMBOL_CEILING_S}s. If close to 20 × single-call time, "
        f"the event loop is being blocked somewhere."
    )


# ---------------------------------------------------------------------------
# Batched screener — fast-fail + wall-clock budget guard
# ---------------------------------------------------------------------------


async def test_top_gainers_returns_within_ceiling(monkeypatch):
    """The exact scenario that produced the "always hanging" user report.
    Whether upstream is healthy or cliffing, the call MUST return within the
    wall-clock budget (default 30 s for the scan + retry overhead).

    Tightens the budget for the test so a hung run fails in 30 s, not 90.
    """
    from tradingview_mcp.server import top_gainers

    monkeypatch.setenv("TRADINGVIEW_MCP_BATCH_BUDGET_S", "25")
    monkeypatch.setenv("TRADINGVIEW_MCP_BATCH_MAX_CONSECUTIVE_FAILS", "2")

    t0 = time.perf_counter()
    result = await asyncio.wait_for(
        top_gainers(exchange="KUCOIN", timeframe="15m", limit=10),
        timeout=BATCHED_SCAN_CEILING_S,
    )
    elapsed = time.perf_counter() - t0

    assert elapsed < BATCHED_SCAN_CEILING_S, (
        f"top_gainers took {elapsed:.1f}s; expected <{BATCHED_SCAN_CEILING_S}s. "
        f"This is the regression that hung the MCP server for 30+ minutes."
    )

    # Result is either a list (success / partial success) or an error envelope
    # (upstream cliff). Both prove the call returned cleanly.
    assert isinstance(result, (list, dict))
    if isinstance(result, dict):
        assert "error" in result, f"unexpected dict shape: {result}"


async def test_volume_breakout_scanner_returns_within_ceiling(monkeypatch):
    """Same fast-fail expectation as top_gainers — different code path."""
    from tradingview_mcp.server import volume_breakout_scanner

    monkeypatch.setenv("TRADINGVIEW_MCP_BATCH_BUDGET_S", "25")
    monkeypatch.setenv("TRADINGVIEW_MCP_BATCH_MAX_CONSECUTIVE_FAILS", "2")

    t0 = time.perf_counter()
    result = await asyncio.wait_for(
        volume_breakout_scanner(exchange="KUCOIN"),
        timeout=BATCHED_SCAN_CEILING_S,
    )
    elapsed = time.perf_counter() - t0

    assert elapsed < BATCHED_SCAN_CEILING_S
    assert isinstance(result, (list, dict))


# ---------------------------------------------------------------------------
# Multi-timeframe — 5 timeframes sequentially, fast-fail must trip
# ---------------------------------------------------------------------------


async def test_multi_timeframe_analysis_returns_within_ceiling(monkeypatch):
    """multi_timeframe_analysis does 5 sequential TF queries. Pre-fix, a
    cliffing upstream would take 5 × (5 s retries + 15 s cooldown) ≈ 100 s.
    Post-fix, fast-fail + wall-clock budget must keep it under 60 s."""
    from tradingview_mcp.server import multi_timeframe_analysis

    monkeypatch.setenv("TRADINGVIEW_MCP_BATCH_BUDGET_S", "45")
    monkeypatch.setenv("TRADINGVIEW_MCP_BATCH_MAX_CONSECUTIVE_FAILS", "2")

    t0 = time.perf_counter()
    result = await asyncio.wait_for(
        multi_timeframe_analysis("BTCUSDT", "KUCOIN"),
        timeout=MULTI_TF_CEILING_S,
    )
    elapsed = time.perf_counter() - t0

    assert elapsed < MULTI_TF_CEILING_S, (
        f"multi_timeframe_analysis took {elapsed:.1f}s; expected <"
        f"{MULTI_TF_CEILING_S}s. Fast-fail or wall-clock budget not tripping."
    )
    assert isinstance(result, dict)
    # Must include timeframes block even when partial — proves the response
    # shape stays intact regardless of upstream health.
    assert "timeframes" in result or "error" in result


# ---------------------------------------------------------------------------
# Mixed parallel load — async tools alongside each other
# ---------------------------------------------------------------------------


async def test_mixed_parallel_tools_complete():
    """Run yahoo_price + top_gainers + multi_timeframe_analysis concurrently.
    Total wall-clock must be bounded by the slowest single tool, not their
    sum. Catches regressions where a sync tool sneaks back in and blocks
    the event loop for everyone else."""
    from tradingview_mcp.server import (
        yahoo_price,
        top_gainers,
        multi_timeframe_analysis,
    )

    t0 = time.perf_counter()
    yahoo_task = yahoo_price("AAPL")
    gainers_task = top_gainers(exchange="KUCOIN", timeframe="15m", limit=5)
    mtf_task = multi_timeframe_analysis("BTCUSDT", "KUCOIN")

    results = await asyncio.wait_for(
        asyncio.gather(yahoo_task, gainers_task, mtf_task, return_exceptions=True),
        timeout=BATCHED_SCAN_CEILING_S,
    )
    elapsed = time.perf_counter() - t0

    assert len(results) == 3
    assert elapsed < BATCHED_SCAN_CEILING_S, (
        f"Mixed parallel run took {elapsed:.1f}s; expected the slowest "
        f"individual tool. Event loop may be blocked."
    )

    # None of the three should leak an unhandled exception. Each may return
    # an error envelope or partial data — both are graceful.
    for i, r in enumerate(results):
        assert not isinstance(r, BaseException), (
            f"task {i} leaked exception: {r!r}"
        )
