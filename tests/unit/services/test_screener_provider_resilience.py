"""Unit tests for screener_provider resilience layer.

Locks in 2026-05-20 hardening:
- Extended retry budget with jitter
- Stale-while-error cache fallback
- Actionable terminal error on persistent failure
"""
from __future__ import annotations

import json
import os
import time
from unittest import mock

import pytest

from tradingview_mcp.core.services import screener_provider as sp


@pytest.fixture(autouse=True)
def _reset_state():
    """Clear cache + last-failure timestamp between tests."""
    with sp._SCREENER_CACHE_LOCK:
        sp._SCREENER_CACHE.clear()
    with sp._TA_FAILURE_LOCK:
        sp._LAST_TA_FAILURE_TS = 0.0
    yield


@pytest.fixture
def fast_retry(monkeypatch):
    """Shrink retry delays to keep tests fast."""
    monkeypatch.setenv("TRADINGVIEW_MCP_RETRY_DELAYS", "0.01,0.02,0.03")
    monkeypatch.setenv("TRADINGVIEW_MCP_RETRY_JITTER", "0")
    monkeypatch.setenv("TRADINGVIEW_MCP_FAILURE_COOLDOWN_S", "0")


def _empty_body_error() -> json.JSONDecodeError:
    """Same shape the empty-body cliff raises."""
    return json.JSONDecodeError("Expecting value", "", 0)


def test_is_transient_screener_error_catches_empty_body():
    assert sp._is_transient_screener_error(_empty_body_error()) is True
    assert sp._is_transient_screener_error(RuntimeError("Connection reset by peer")) is True
    assert sp._is_transient_screener_error(ValueError("totally unrelated")) is False


def test_is_transient_screener_error_catches_socket_timeouts():
    """Socket timeouts MUST be classified transient so retry layer fires
    (was causing 8-minute hangs before 2026-05-20 hardening)."""
    import socket as _socket
    assert sp._is_transient_screener_error(_socket.timeout()) is True
    assert sp._is_transient_screener_error(TimeoutError("call timed out")) is True
    assert sp._is_transient_screener_error(RuntimeError("Read timed out")) is True
    assert sp._is_transient_screener_error(RuntimeError("Max retries exceeded")) is True
    assert sp._is_transient_screener_error(RuntimeError("RemoteDisconnected")) is True


def test_socket_default_timeout_applied_on_import():
    """Module import must call socket.setdefaulttimeout() so urllib calls
    inside tradingview_ta/screener never hang indefinitely."""
    import socket as _socket
    t = _socket.getdefaulttimeout()
    assert t is not None
    assert t > 0
    assert t <= 60.0  # sanity: well below the 8-minute hang threshold


def test_retry_then_succeed(fast_retry):
    """Scanner that fails twice then succeeds should return final result."""
    calls = {"n": 0}

    class FakeQuery:
        def get_scanner_data(self, cookies=None):
            calls["n"] += 1
            if calls["n"] < 3:
                raise _empty_body_error()
            return (1, "ok_df")

    total, df = sp._scan_with_retry(FakeQuery())
    assert (total, df) == (1, "ok_df")
    assert calls["n"] == 3


def test_persistent_failure_raises_runtime_error(fast_retry):
    """All retries fail and no cache → RuntimeError with actionable message."""
    class FakeQuery:
        def get_scanner_data(self, cookies=None):
            raise _empty_body_error()

    with pytest.raises(RuntimeError) as exc_info:
        sp._scan_with_retry(FakeQuery())

    msg = str(exc_info.value)
    assert "transient errors on all" in msg
    assert "scanner.tradingview.com" in msg
    assert "Wait" in msg


def test_stale_while_error_returns_cached_payload(fast_retry):
    """When upstream is dead, stale cached data should serve as fallback."""
    cache_key = ("indicators_v1", "EGX", ("EGX:ASCM",), "1D", None)
    sp._cache_set(cache_key, (1, "stale_df"))

    # Force the freshness window to be already expired so _cache_get misses,
    # but stale lookup still hits.
    with sp._SCREENER_CACHE_LOCK:
        ts, payload = sp._SCREENER_CACHE[cache_key]
        sp._SCREENER_CACHE[cache_key] = (ts - 120.0, payload)  # 2 min old

    class FakeQuery:
        def get_scanner_data(self, cookies=None):
            raise _empty_body_error()

    total, df = sp._scan_with_retry(FakeQuery(), cache_key=cache_key)
    assert (total, df) == (1, "stale_df")


def test_non_transient_error_propagates_immediately(fast_retry):
    """Non-transient errors must NOT be silenced by the retry layer."""
    class FakeQuery:
        def get_scanner_data(self, cookies=None):
            raise ValueError("schema mismatch")

    with pytest.raises(ValueError):
        sp._scan_with_retry(FakeQuery())


def test_jitter_within_band(monkeypatch):
    """_jittered must keep delays within ±jitter of the base value."""
    monkeypatch.setenv("TRADINGVIEW_MCP_RETRY_JITTER", "0.2")
    for _ in range(50):
        d = sp._jittered(10.0)
        assert 8.0 <= d <= 12.0


def test_resilient_ta_uses_fresh_cache_first(fast_retry, monkeypatch):
    """Fresh cache hit must skip upstream entirely."""
    call_count = {"n": 0}

    def fake_gma(screener, interval, symbols, **kwargs):
        call_count["n"] += 1
        return {"EGX:ASCM": object()}

    fake_module = mock.MagicMock()
    fake_module.get_multiple_analysis = fake_gma
    monkeypatch.setitem(__import__("sys").modules, "tradingview_ta", fake_module)

    # First call hits upstream
    sp.resilient_get_multiple_analysis("egypt", "1D", ["EGX:ASCM"])
    # Second call within TTL must hit cache
    sp.resilient_get_multiple_analysis("egypt", "1D", ["EGX:ASCM"])
    assert call_count["n"] == 1


def test_resilient_ta_passes_timeout_explicitly(fast_retry, monkeypatch):
    """tradingview_ta.get_multiple_analysis defaults timeout=None which would
    hang requests.post FOREVER on stalled upstream (this was the actual
    8-minute hang root cause). Resilient wrapper MUST pass timeout=20."""
    captured = {}

    def fake_gma(screener, interval, symbols, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        return {"EGX:ASCM": "ok"}

    fake_module = mock.MagicMock()
    fake_module.get_multiple_analysis = fake_gma
    monkeypatch.setitem(__import__("sys").modules, "tradingview_ta", fake_module)

    sp.resilient_get_multiple_analysis("egypt", "1D", ["EGX:ASCM"])

    assert captured["timeout"] is not None, "timeout must be passed explicitly"
    assert 1.0 <= captured["timeout"] <= 60.0, f"timeout should be a sane value, got {captured['timeout']}"


def test_resilient_ta_returns_stale_on_persistent_failure(fast_retry, monkeypatch):
    """When all retries fail, stale-while-error must serve old result."""
    call_count = {"n": 0}

    def fake_gma(screener, interval, symbols, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return {"EGX:ASCM": "good_payload"}
        raise _empty_body_error()

    fake_module = mock.MagicMock()
    fake_module.get_multiple_analysis = fake_gma
    monkeypatch.setitem(__import__("sys").modules, "tradingview_ta", fake_module)

    # Prime the cache with one successful call
    first = sp.resilient_get_multiple_analysis("egypt", "1D", ["EGX:ASCM"])
    assert first == {"EGX:ASCM": "good_payload"}

    # Manually expire the FRESH window so the next call must re-fetch,
    # but stale window still holds.
    cache_key = ("ta_multi_v1", "egypt", "1D", ("EGX:ASCM",))
    with sp._SCREENER_CACHE_LOCK:
        ts, payload = sp._SCREENER_CACHE[cache_key]
        sp._SCREENER_CACHE[cache_key] = (ts - 120.0, payload)

    # Upstream now broken; stale fallback should kick in
    result = sp.resilient_get_multiple_analysis("egypt", "1D", ["EGX:ASCM"])
    assert result == {"EGX:ASCM": "good_payload"}
