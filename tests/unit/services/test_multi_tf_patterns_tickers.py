"""Regression test: fetch_multi_timeframe_patterns must query the CALLER'S
symbols, not the first N arbitrary rows of a whole-exchange scan.

The old code did ``set_markets(...).limit(len(symbols))`` — the ``symbols``
argument was silently ignored while the resilience cache was keyed on it, so
different symbol lists collided onto the same wrong rows.
"""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from tradingview_mcp.core.services import screener_service


def test_query_targets_the_requested_symbols():
    captured = {}

    def fake_scan(q, cache_key=None, **_):
        captured["query"] = q.query
        return 0, pd.DataFrame()

    with patch.object(screener_service, "_scan_with_retry", side_effect=fake_scan):
        screener_service.fetch_multi_timeframe_patterns(
            "kucoin", ["KUCOIN:AUSDT", "BUSDT"], "15m", 3, 10.0,
        )

    tickers = captured["query"]["symbols"]["tickers"]
    # Prefixed symbols pass through; bare ones get the exchange prefix.
    assert tickers == ["KUCOIN:AUSDT", "KUCOIN:BUSDT"]
