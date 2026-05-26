"""Tests for the P4 async tool conversion.

Verifies:
- The 7 converted tool handlers are ``async def`` (so FastMCP awaits them
  cooperatively instead of blocking the event loop).
- ``asyncio.gather`` over many parallel handler calls actually overlaps —
  total time is bounded by the slowest single call, not their sum.
- ``combined_analysis`` fans its 3 sub-calls out in parallel.
- True-async (``yahoo_price`` / ``stock_extended_hours``) and
  threadpool-async (``top_gainers``/``multi_timeframe_analysis``/
  ``volume_breakout_scanner``/``financial_news``/``combined_analysis``)
  both unblock the event loop.
- Errors propagate cleanly without leaving the event loop in a bad state.

The tests stub every upstream call so they neither hit network nor depend
on ``tradingview_ta`` / ``tradingview-screener`` being functional in CI.
"""
from __future__ import annotations

import asyncio
import inspect
import time
from unittest import mock

import pytest

from tradingview_mcp import server


# Tools converted as part of P4. Any regression that flips one back to a
# bare ``def`` should fail this immediately.
ASYNC_HANDLERS = [
    "top_gainers",
    "volume_breakout_scanner",
    "multi_timeframe_analysis",
    "financial_news",
    "combined_analysis",
    "yahoo_price",
    "stock_extended_hours",
]


# ---------------------------------------------------------------------------
# Signatures
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ASYNC_HANDLERS)
def test_handler_is_async(name: str) -> None:
    fn = getattr(server, name)
    assert inspect.iscoroutinefunction(fn), (
        f"{name} must be `async def` so FastMCP awaits it cooperatively; "
        f"reverting to sync def would block the event loop for the full "
        f"call duration and stall every concurrent tool call."
    )


# ---------------------------------------------------------------------------
# yahoo_price — true async via httpx
# ---------------------------------------------------------------------------


async def test_yahoo_price_returns_formatted_quote(monkeypatch):
    """End-to-end shape check using a stubbed httpx response."""
    async def fake_get_price(symbol: str) -> dict:
        return {
            "symbol": symbol,
            "price": 100.0,
            "previous_close": 95.0,
            "change": 5.0,
            "change_pct": 5.26,
            "currency": "USD",
            "exchange": "NMS",
            "market_state": "REGULAR",
            "52w_high": 120.0,
            "52w_low": 80.0,
            "source": "Yahoo Finance",
            "timestamp": "2026-05-27T00:00:00Z",
        }

    monkeypatch.setattr(server, "get_price_async", fake_get_price)

    result = await server.yahoo_price("AAPL")
    assert result["symbol"] == "AAPL"
    assert result["price"] == 100.0
    assert result["source"] == "Yahoo Finance"


async def test_yahoo_price_propagates_errors_as_envelope(monkeypatch):
    async def fake_get_price(symbol: str) -> dict:
        return {"symbol": symbol, "error": "boom", "source": "Yahoo Finance"}

    monkeypatch.setattr(server, "get_price_async", fake_get_price)

    result = await server.yahoo_price("AAPL")
    assert result["error"] == "boom"


# ---------------------------------------------------------------------------
# Parallelism — the actual win we're shipping
# ---------------------------------------------------------------------------


async def test_yahoo_price_runs_in_parallel(monkeypatch):
    """20 concurrent yahoo_price calls should finish in roughly the time of
    one call, not 20x. This proves the event loop isn't being blocked.

    Uses a stubbed ``get_price_async`` that sleeps 100ms per call. If the
    handler were sync (or if we wrapped a sync call without to_thread), the
    total wall-clock would be ~2s. Async gives ~100-200ms.
    """
    async def slow_price(symbol: str) -> dict:
        await asyncio.sleep(0.1)
        return {"symbol": symbol, "price": 1.0}

    monkeypatch.setattr(server, "get_price_async", slow_price)

    start = time.perf_counter()
    results = await asyncio.gather(*(server.yahoo_price(f"S{i}") for i in range(20)))
    elapsed = time.perf_counter() - start

    assert len(results) == 20
    # Generous bound — 1 second is still 20x faster than serialized 2s,
    # and gives CI loaded machines plenty of slack.
    assert elapsed < 1.0, (
        f"20 parallel yahoo_price calls took {elapsed:.2f}s; expected ~0.1s "
        f"if the event loop is truly free. Either the handler is no longer "
        f"async or the underlying call is blocking."
    )


async def test_top_gainers_offloads_to_thread(monkeypatch):
    """Sync screener call must run in a worker thread so the event loop
    can interleave other tool calls."""
    # Sleep inside the sync call simulates network I/O. If the handler
    # called this directly (without to_thread) it would block the loop.
    call_threads = []

    def slow_screener(exchange, timeframe, limit):
        import threading
        call_threads.append(threading.get_ident())
        time.sleep(0.05)
        return [{"symbol": "X", "changePercent": 1.0, "indicators": {}}]

    monkeypatch.setattr(server, "fetch_trending_analysis", slow_screener)

    # While top_gainers is in flight, this sleep should also run
    # concurrently → both finish in ~50ms, not 100ms.
    start = time.perf_counter()

    async def parallel_marker():
        await asyncio.sleep(0.05)

    gainers_task = asyncio.create_task(
        server.top_gainers(exchange="KUCOIN", timeframe="15m", limit=5)
    )
    marker_task = asyncio.create_task(parallel_marker())
    rows, _ = await asyncio.gather(gainers_task, marker_task)
    elapsed = time.perf_counter() - start

    assert isinstance(rows, list)
    assert len(rows) == 1
    # The worker thread must NOT be the main event loop thread.
    import threading
    assert call_threads[0] != threading.main_thread().ident
    assert elapsed < 0.1, (
        f"top_gainers + marker took {elapsed:.2f}s; expected ~0.05s if "
        f"running concurrently. The handler may be blocking the event loop."
    )


async def test_combined_analysis_fans_subcalls_in_parallel(monkeypatch):
    """combined_analysis used to do 3 sequential sync calls. Async fan-out
    should make total wall-clock equal to the slowest single call, not
    the sum of all three.
    """
    def slow_tech(symbol, exchange, timeframe):
        time.sleep(0.1)
        return {"market_sentiment": {"momentum": "Bullish", "buy_sell_signal": "BUY"}}

    def slow_sentiment(symbol, category):
        time.sleep(0.1)
        return {
            "sentiment_score": 0.3,
            "sentiment_label": "Bullish",
            "posts_analyzed": 12,
        }

    def slow_news(symbol, category, limit):
        time.sleep(0.1)
        return {"count": 3, "items": [{"title": "x"}, {"title": "y"}, {"title": "z"}]}

    monkeypatch.setattr(server, "analyze_coin", slow_tech)
    monkeypatch.setattr(server, "analyze_sentiment", slow_sentiment)
    monkeypatch.setattr(server, "fetch_news_summary", slow_news)

    start = time.perf_counter()
    result = await server.combined_analysis("AAPL", exchange="NASDAQ", timeframe="1D")
    elapsed = time.perf_counter() - start

    # Sequential = ~300ms; parallel = ~100ms. Bound at 200ms to absorb
    # CI jitter while still failing if someone removes the asyncio.gather.
    assert elapsed < 0.2, (
        f"combined_analysis took {elapsed:.2f}s; expected ~0.1s with the "
        f"3-way parallel fan-out. Did asyncio.gather get unwound?"
    )

    # Confluence math should still work — proves the result wiring survived.
    assert result["symbol"] == "AAPL"
    assert result["confluence"]["signals_agree"] is True
    assert result["confluence"]["confidence"] == "HIGH"
    assert result["technical"]["market_sentiment"]["buy_sell_signal"] == "BUY"
    assert result["sentiment"]["posts_analyzed"] == 12
    assert result["news"]["count"] == 3


# ---------------------------------------------------------------------------
# Error propagation — async handlers must not eat exceptions silently
# ---------------------------------------------------------------------------


async def test_volume_breakout_scanner_translates_batch_failure(monkeypatch):
    """BatchExecutionError raised inside the threadpool must surface as
    the standard error envelope (not propagate as an exception)."""
    from tradingview_mcp.core.errors import BatchExecutionError

    def boom(*args, **kwargs):
        raise BatchExecutionError(
            batches_attempted=5,
            batches_failed=5,
            first_error="JSONDecodeError",
        )

    monkeypatch.setattr(server, "volume_breakout_scan", boom)

    result = await server.volume_breakout_scanner(exchange="KUCOIN")
    assert isinstance(result, dict)
    assert "error" in result
    assert result["error"]["code"] == "ALL_BATCHES_FAILED"
    assert result["error"]["batches_attempted"] == 5
    assert result["error"]["batches_failed"] == 5


async def test_top_gainers_translates_batch_failure(monkeypatch):
    from tradingview_mcp.core.errors import BatchExecutionError

    def boom(*args, **kwargs):
        raise BatchExecutionError(
            batches_attempted=3,
            batches_failed=3,
            first_error="JSONDecodeError",
        )

    monkeypatch.setattr(server, "fetch_trending_analysis", boom)

    result = await server.top_gainers(exchange="KUCOIN", timeframe="15m", limit=10)
    assert isinstance(result, dict)
    assert result["error"]["code"] == "ALL_BATCHES_FAILED"


async def test_financial_news_offloads_feedparser(monkeypatch):
    """feedparser.parse() is sync. The handler must offload it so the loop
    stays free."""
    calls = {"n": 0}

    def fake_summary(symbol, category, limit):
        time.sleep(0.05)
        calls["n"] += 1
        return {"symbol": symbol, "category": category, "count": 0,
                "feedparser_available": True, "items": [], "timestamp": "x"}

    monkeypatch.setattr(server, "fetch_news_summary", fake_summary)

    start = time.perf_counter()
    results = await asyncio.gather(
        server.financial_news(symbol="AAPL", category="stocks", limit=10),
        server.financial_news(symbol="MSFT", category="stocks", limit=10),
        server.financial_news(symbol="GOOG", category="stocks", limit=10),
    )
    elapsed = time.perf_counter() - start

    assert len(results) == 3
    assert calls["n"] == 3
    # 3 parallel × 50ms sleep should finish near 50ms, not 150ms.
    assert elapsed < 0.12, (
        f"3 parallel financial_news calls took {elapsed:.2f}s; expected ~0.05s. "
        f"feedparser must be offloaded via asyncio.to_thread."
    )


async def test_multi_timeframe_analysis_offloads(monkeypatch):
    def slow_run(full_symbol, exchange):
        time.sleep(0.05)
        return {"symbol": full_symbol, "exchange": exchange, "ok": True}

    monkeypatch.setattr(server, "run_multi_timeframe_analysis", slow_run)

    start = time.perf_counter()
    a, b = await asyncio.gather(
        server.multi_timeframe_analysis("BTCUSDT", "KUCOIN"),
        server.multi_timeframe_analysis("ETHUSDT", "KUCOIN"),
    )
    elapsed = time.perf_counter() - start
    assert a["ok"] is True and b["ok"] is True
    assert elapsed < 0.1


# ---------------------------------------------------------------------------
# yahoo_finance_service unit tests
# ---------------------------------------------------------------------------


async def test_get_price_async_uses_format_helper(monkeypatch):
    """The async fetch path must produce the same dict shape as the sync
    path — same _format_quote helper feeds both."""
    from tradingview_mcp.core.services import yahoo_finance_service as yf

    sample_chart = {
        "meta": {
            "regularMarketPrice": 200.0,
            "previousClose": 195.0,
            "currency": "USD",
            "exchangeName": "NMS",
            "marketState": "REGULAR",
            "fiftyTwoWeekHigh": 250.0,
            "fiftyTwoWeekLow": 100.0,
        },
        "indicators": {"quote": [{"close": [195.0, 200.0]}]},
    }

    class _FakeResp:
        def raise_for_status(self):  # pragma: no cover - trivial
            return None

        def json(self):
            return {"chart": {"result": [sample_chart]}}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url):
            return _FakeResp()

    monkeypatch.setattr(yf.httpx, "AsyncClient", _FakeClient)

    result = await yf.get_price_async("aapl")
    assert result["symbol"] == "AAPL"
    assert result["price"] == 200.0
    assert result["previous_close"] == 195.0
    assert result["change_pct"] == pytest.approx(2.56, rel=0.01)
    assert "timestamp" in result


async def test_get_extended_hours_price_async(monkeypatch):
    from tradingview_mcp.core.services import extended_hours_service as eh

    sample_data = {
        "chart": {
            "result": [{
                "meta": {
                    "regularMarketPrice": 150.0,
                    "previousClose": 148.0,
                    "currency": "USD",
                    "exchangeName": "NMS",
                    "marketState": "POST",
                    "currentTradingPeriod": {
                        "regular": {"start": 1716800000, "end": 1716823400},
                    },
                    "regularMarketTime": 1716823400,
                },
                "timestamp": [1716780000, 1716810000, 1716830000],
                "indicators": {"quote": [{"close": [149.0, 150.0, 151.5]}]},
            }]
        }
    }

    class _FakeResp:
        def raise_for_status(self):  # pragma: no cover - trivial
            return None

        def json(self):
            return sample_data

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url):
            return _FakeResp()

    monkeypatch.setattr(eh.httpx, "AsyncClient", _FakeClient)

    result = await eh.get_extended_hours_price_async("AAPL")
    assert result["symbol"] == "AAPL"
    assert result["pre_market"] is not None
    assert result["post_market"] is not None
    assert result["regular"]["price"] == 150.0
