"""Whole-exchange scans make ONE lean scanner request.

``fetch_trending_analysis`` (top_gainers, top_losers, rating_filter) and
``fetch_bollinger_analysis`` (bollinger_scan) used to call
``get_multiple_analysis`` in 200-symbol batches, each asking for ~90 indicator
columns. NASDAQ (~5,000 tickers) took 25 requests: the scan ran out of its 30s
budget (PARTIAL_DATA) or tripped TradingView's empty-body throttling
(ALL_BATCHES_FAILED) on most US-stock calls. They now fetch only the columns
they read, for the whole list, in a single request.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from tradingview_screener import query as tv_query

from tradingview_mcp.core.services import screener_provider as sp
from tradingview_mcp.core.services import screener_service


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    """Isolate the shared cache / cooldown and make retries instant."""
    with sp._SCREENER_CACHE_LOCK:
        sp._SCREENER_CACHE.clear()
    with sp._TA_FAILURE_LOCK:
        sp._LAST_TA_FAILURE_TS = 0.0
    monkeypatch.setenv("TRADINGVIEW_MCP_RETRY_DELAYS", "0.01,0.02")
    monkeypatch.setenv("TRADINGVIEW_MCP_RETRY_JITTER", "0")
    monkeypatch.setenv("TRADINGVIEW_MCP_FAILURE_COOLDOWN_S", "0")
    monkeypatch.setenv("TRADINGVIEW_MCP_MIN_INTERVAL_S", "0")
    yield
    with sp._SCREENER_CACHE_LOCK:
        sp._SCREENER_CACHE.clear()


class _FakeScanner:
    """Stands in for ``Query.get_scanner_data_raw``; records every request."""

    def __init__(self, responder):
        self.requests: list[dict] = []
        self._responder = responder

    def __call__(self, query_self, **kwargs):
        sent = {"url": query_self.url, **json.loads(json.dumps(query_self.query))}
        self.requests.append(sent)
        return self._responder(sent)


def _echo_rows(sent: dict) -> dict:
    """One row per requested ticker; every column value is 1.0."""
    tickers = sent["symbols"]["tickers"]
    width = len(sent["columns"])
    return {"totalCount": len(tickers),
            "data": [{"s": t, "d": [1.0] * width} for t in tickers]}


def _install(monkeypatch, responder=_echo_rows) -> _FakeScanner:
    fake = _FakeScanner(responder)

    # A plain function (not the callable instance) so it binds as a method
    # and receives the Query being sent.
    def get_scanner_data_raw(query_self, **kwargs):
        return fake(query_self, **kwargs)

    monkeypatch.setattr(tv_query.Query, "get_scanner_data_raw", get_scanner_data_raw)
    return fake


# ── resilient_scan_columns ──────────────────────────────────────────────────

def test_one_request_for_every_ticker_with_interval_suffix(monkeypatch):
    fake = _install(monkeypatch)
    tickers = [f"NASDAQ:T{i}" for i in range(4997)]

    out = sp.resilient_scan_columns("america", "1h", tickers, ["open", "close"])

    assert len(fake.requests) == 1
    sent = fake.requests[0]
    assert sent["url"] == "https://scanner.tradingview.com/america/scan"
    assert sent["markets"] == ["america"]
    assert sent["symbols"]["tickers"] == tickers
    assert sent["columns"] == ["open|60", "close|60"]
    assert sent["range"] == [0, 4997]
    assert "sort" not in sent  # callers rank on their own metric
    # Keys are the bare column names, like Analysis.indicators.
    assert out["NASDAQ:T0"] == {"open": 1.0, "close": 1.0}
    assert len(out) == 4997


@pytest.mark.parametrize("interval, suffix", [
    ("5m", "|5"), ("15m", "|15"), ("1h", "|60"), ("4h", "|240"),
    ("1D", ""), ("1W", "|1W"), ("1M", "|1M"),
])
def test_column_suffix_matches_tradingview_ta(monkeypatch, interval, suffix):
    """Daily is the bare column: the scanner answers "close|1D" with null."""
    fake = _install(monkeypatch)
    sp.resilient_scan_columns("crypto", interval, ["BINANCE:BTCUSDT"], ["close", "SMA20"])
    assert fake.requests[0]["columns"] == [f"close{suffix}", f"SMA20{suffix}"]


def test_null_values_stay_none_and_malformed_rows_are_skipped(monkeypatch):
    """None must survive (compute_metrics drops the row on TypeError); a NaN
    would slip through its checks and break the sort."""
    def responder(sent):
        return {"totalCount": 3, "data": [
            {"s": "NYSE:IBM", "d": [10.0, None]},
            {"s": "NYSE:BAD", "d": [1.0]},          # wrong width
            {"d": [1.0, 2.0]},                       # no symbol
        ]}

    _install(monkeypatch, responder)
    out = sp.resilient_scan_columns("america", "1D", ["NYSE:IBM", "NYSE:BAD"], ["open", "close"])
    assert out == {"NYSE:IBM": {"open": 10.0, "close": None}}


def test_fresh_cache_answers_repeat_scans(monkeypatch):
    fake = _install(monkeypatch)
    args = ("america", "1D", ["NASDAQ:AAPL", "NASDAQ:NVDA"], ["close"])

    first = sp.resilient_scan_columns(*args)
    second = sp.resilient_scan_columns(*args)

    assert first == second
    assert len(fake.requests) == 1


def test_transient_failure_is_retried(monkeypatch):
    calls = {"n": 0}

    def responder(sent):
        calls["n"] += 1
        if calls["n"] == 1:
            raise json.JSONDecodeError("Expecting value", "", 0)  # empty-body cliff
        return _echo_rows(sent)

    _install(monkeypatch, responder)
    out = sp.resilient_scan_columns("america", "1D", ["NASDAQ:AAPL"], ["close"])
    assert out == {"NASDAQ:AAPL": {"close": 1.0}}
    assert calls["n"] == 2


def test_outage_serves_the_stale_scan(monkeypatch):
    fake = _install(monkeypatch)
    args = ("america", "1D", ["NASDAQ:AAPL"], ["close"])
    sp.resilient_scan_columns(*args)

    # Age the entry past the fresh TTL, then take upstream down.
    with sp._SCREENER_CACHE_LOCK:
        for key, (ts, payload) in list(sp._SCREENER_CACHE.items()):
            sp._SCREENER_CACHE[key] = (ts - 600.0, payload)

    def down(sent):
        raise json.JSONDecodeError("Expecting value", "", 0)

    fake._responder = down
    assert sp.resilient_scan_columns(*args) == {"NASDAQ:AAPL": {"close": 1.0}}


def test_persistent_outage_raises_clean_transient_error(monkeypatch):
    def down(sent):
        raise json.JSONDecodeError("Expecting value", "", 0)

    _install(monkeypatch, down)
    with pytest.raises(RuntimeError, match="transient errors on all 3 attempts"):
        sp.resilient_scan_columns("america", "1D", ["NASDAQ:AAPL"], ["close"])


def test_empty_symbol_list_makes_no_request(monkeypatch):
    fake = _install(monkeypatch)
    assert sp.resilient_scan_columns("america", "1D", [], ["close"]) == {}
    assert fake.requests == []


# ── the scans themselves ────────────────────────────────────────────────────

def _indicators(open_price: float, close: float) -> dict:
    return {
        "open": open_price, "close": close, "SMA20": 100.0,
        "BB.upper": 110.0, "BB.lower": 90.0,
        "EMA50": 100.0, "RSI": 50.0, "volume": 1_000.0,
    }


def _scan_spy(calls: list):
    def fake_scan(screener, interval, symbols, columns):
        calls.append({"screener": screener, "interval": interval,
                      "symbols": list(symbols), "columns": list(columns)})
        # Change rises with the symbol index so the ranking is unambiguous.
        return {s: _indicators(100.0, 100.0 + i / 100) for i, s in enumerate(symbols)}
    return fake_scan


def test_nasdaq_top_gainers_is_one_request():
    nasdaq = [f"NASDAQ:T{i}" for i in range(4997)]
    calls: list = []
    with patch.object(screener_service, "resilient_scan_columns", side_effect=_scan_spy(calls)), \
         patch.object(screener_service, "load_symbols", return_value=nasdaq):
        rows = screener_service.fetch_trending_analysis("nasdaq", timeframe="1D", limit=50)

    assert len(calls) == 1
    assert calls[0]["screener"] == "america"
    assert calls[0]["symbols"] == nasdaq
    assert calls[0]["columns"] == screener_service._SCAN_COLUMNS
    assert len(rows) == 50
    assert rows[0]["symbol"] == "NASDAQ:T4996"  # biggest gainer of the whole list


def test_nasdaq_top_losers_ranks_the_whole_list():
    nasdaq = [f"NASDAQ:T{i}" for i in range(4997)]
    calls: list = []
    with patch.object(screener_service, "resilient_scan_columns", side_effect=_scan_spy(calls)), \
         patch.object(screener_service, "load_symbols", return_value=nasdaq):
        rows = screener_service.fetch_trending_analysis("nasdaq", timeframe="1D", limit=5, sort="asc")

    assert len(calls) == 1
    assert [r["symbol"] for r in rows] == [f"NASDAQ:T{i}" for i in range(5)]


def test_bollinger_scan_is_one_request():
    nasdaq = [f"NASDAQ:T{i}" for i in range(4997)]
    calls: list = []
    with patch.object(screener_service, "resilient_scan_columns", side_effect=_scan_spy(calls)), \
         patch.object(screener_service, "load_symbols", return_value=nasdaq):
        rows = screener_service.fetch_bollinger_analysis("nasdaq", timeframe="1D", bbw_filter=0.5, limit=10)

    assert len(calls) == 1
    assert calls[0]["symbols"] == nasdaq
    assert len(rows) == 10
    assert rows[0]["indicators"]["EMA50"] == 100.0


def test_every_shipped_coinlist_fits_in_one_request():
    """A coinlist that outgrows the chunk silently doubles the request count;
    raise _SCAN_CHUNK (or split the list) when this fails."""
    import os
    from tradingview_mcp.core.services.coinlist import COINLIST_DIR

    sizes = {}
    for name in os.listdir(COINLIST_DIR):
        if name.endswith(".txt"):
            with open(os.path.join(COINLIST_DIR, name), encoding="utf-8") as f:
                sizes[name] = sum(1 for line in f if line.strip())
    too_big = {n: c for n, c in sizes.items() if c > screener_service._SCAN_CHUNK}
    assert not too_big
