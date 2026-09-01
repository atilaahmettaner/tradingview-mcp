"""Regression tests for the top_losers sort-before-truncate bug.

``fetch_trending_analysis`` used to sort descending and truncate to ``limit``
unconditionally; ``top_losers`` then re-sorted that slice ascending — so with
limit=25 it returned the 25 biggest GAINERS presented smallest-first, and the
market's actual losers never left the service layer. The fix threads a
``sort`` parameter through so ordering happens before truncation.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from tradingview_mcp import server
from tradingview_mcp.core.services import screener_service


def _indicators(open_price: float, close: float) -> dict[str, Any]:
    """Indicators that pass compute_metrics with change = close vs open."""
    return {
        "open": open_price,
        "close": close,
        "SMA20": 100.0,
        "BB.upper": 110.0,
        "BB.lower": 90.0,
        "EMA50": 100.0,
        "RSI": 50.0,
        "volume": 1_000.0,
    }


def _analysis_response() -> dict:
    """Five symbols spanning -20%..+20% so order is unambiguous."""
    changes = {"UP20": 120.0, "UP10": 110.0, "FLAT": 100.0, "DN10": 90.0, "DN20": 80.0}
    return {
        sym: SimpleNamespace(indicators=_indicators(100.0, close))
        for sym, close in changes.items()
    }


def _patched(sort: str, limit: int):
    with patch.object(screener_service, "get_multiple_analysis",
                      return_value=_analysis_response()), \
         patch.object(screener_service, "load_symbols",
                      return_value=["UP20", "UP10", "FLAT", "DN10", "DN20"]):
        return screener_service.fetch_trending_analysis(
            "KUCOIN", timeframe="15m", limit=limit, sort=sort,
        )


class TestFetchTrendingAnalysisSort:
    def test_desc_returns_biggest_gainers(self):
        rows = _patched(sort="desc", limit=2)
        assert [r["symbol"] for r in rows] == ["UP20", "UP10"]

    def test_asc_returns_biggest_losers_not_smallest_gainers(self):
        """The bug: asc-after-truncate would yield ['FLAT', 'UP10'] here."""
        rows = _patched(sort="asc", limit=2)
        assert [r["symbol"] for r in rows] == ["DN20", "DN10"]
        assert all(r["changePercent"] < 0 for r in rows)


class TestTopLosersTool:
    def test_tool_requests_ascending_sort(self, monkeypatch):
        captured: dict[str, Any] = {}

        def fake_fetch(exchange, timeframe="5m", filter_type="",
                       rating_filter=None, limit=50, sort="desc"):
            captured["sort"] = sort
            captured["limit"] = limit
            return [
                {"symbol": "DN20", "changePercent": -20.0, "indicators": {}},
                {"symbol": "DN10", "changePercent": -10.0, "indicators": {}},
            ]

        monkeypatch.setattr(server, "fetch_trending_analysis", fake_fetch)
        rows = server.top_losers(exchange="KUCOIN", timeframe="15m", limit=2)

        assert captured["sort"] == "asc"
        assert captured["limit"] == 2
        # Service order (losers-first) must be preserved, not re-sorted.
        assert [r["symbol"] for r in rows] == ["DN20", "DN10"]
