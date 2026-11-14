"""TA fetches while TradingView is refusing requests, and coin_analysis's budget.

On the hosted server (week to 2026-11-14) TradingView answered tradingview_ta's
requests with empty bodies in bursts of minutes: 171 fetches failed on the
first attempt and every one failed its two retries too. Each later call then
slept out the 15s failure cooldown and retried three more times, so
coin_analysis took ~20s and still answered from the stale cache, labelled
"real-time"; multi_timeframe_analysis, whose scanner requests never failed,
slept through the same cooldown. These tests pin the replacement:

- while refusing: the stale cache at once, or one attempt, never a sleep;
- the first failure of a burst keeps the normal retry schedule;
- the scanner path only cools down after its own failures;
- coin_analysis has one time budget and says when its numbers are stale.

Network-free: tradingview_ta is replaced by a fake module.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from types import SimpleNamespace
from unittest import mock

import pytest

from tradingview_mcp.core.services import screener_provider as sp
from tradingview_mcp.core.services import screener_service


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    with sp._SCREENER_CACHE_LOCK:
        sp._SCREENER_CACHE.clear()
    with sp._TA_FAILURE_LOCK:
        sp._LAST_TA_FAILURE_TS = 0.0
        sp._LAST_SCAN_FAILURE_TS = 0.0
    monkeypatch.setenv("TRADINGVIEW_MCP_RETRY_DELAYS", "0.01,0.02")
    monkeypatch.setenv("TRADINGVIEW_MCP_RETRY_JITTER", "0")
    monkeypatch.setenv("TRADINGVIEW_MCP_FAILURE_COOLDOWN_S", "15")
    monkeypatch.setenv("TRADINGVIEW_MCP_MIN_INTERVAL_S", "0")
    yield
    with sp._SCREENER_CACHE_LOCK:
        sp._SCREENER_CACHE.clear()
    with sp._TA_FAILURE_LOCK:
        sp._LAST_TA_FAILURE_TS = 0.0
        sp._LAST_SCAN_FAILURE_TS = 0.0


@pytest.fixture
def sleeps(monkeypatch):
    """Record sleeps instead of sleeping."""
    seen: list = []
    monkeypatch.setattr(sp._time, "sleep", lambda s: seen.append(s))
    return seen


def _empty_body() -> json.JSONDecodeError:
    return json.JSONDecodeError("Expecting value", "", 0)


def _refuse():
    """What tradingview_ta raises when TradingView answers with an empty body."""
    raise _empty_body()


def _fake_ta(monkeypatch, behaviour):
    """Install a fake tradingview_ta whose get_multiple_analysis runs ``behaviour``."""
    calls: list = []

    def fake_gma(screener, interval, symbols, **kwargs):
        calls.append(kwargs)
        return behaviour(len(calls), symbols)

    module = mock.MagicMock()
    module.get_multiple_analysis = fake_gma
    monkeypatch.setitem(sys.modules, "tradingview_ta", module)
    return calls


def _expire_fresh(cache_key, by: float = 120.0) -> None:
    """Age a cache entry past the 60s fresh TTL (still inside the stale TTL)."""
    with sp._SCREENER_CACHE_LOCK:
        ts, payload = sp._SCREENER_CACHE[cache_key]
        sp._SCREENER_CACHE[cache_key] = (ts - by, payload)


KEY = ("ta_multi_v2", "egypt", "1D", ("EGX:ASCM",))


# ── Refusal: no sleeping, no retry storm ─────────────────────────────────────

def test_while_refusing_the_stale_cache_answers_without_a_request(monkeypatch, sleeps):
    calls = _fake_ta(monkeypatch, lambda n, s: {"EGX:ASCM": "good"} if n == 1 else _refuse())
    assert sp.resilient_get_multiple_analysis("egypt", "1D", ["EGX:ASCM"]) == {"EGX:ASCM": "good"}
    _expire_fresh(KEY)
    sp._record_ta_failure()  # another fetch just exhausted its attempts

    with sp.ta_call() as call:
        out = sp.resilient_get_multiple_analysis("egypt", "1D", ["EGX:ASCM"])

    assert out == {"EGX:ASCM": "good"}
    assert len(calls) == 1, "no new request while TradingView is refusing"
    assert sleeps == [], "no cooldown sleep"
    assert call["stale_age_s"] == pytest.approx(120.0, abs=5.0)


def test_while_refusing_without_a_stale_copy_one_attempt_fails_fast(monkeypatch, sleeps):
    calls = _fake_ta(monkeypatch, lambda n, s: _refuse())
    sp._record_ta_failure()

    with pytest.raises(RuntimeError) as exc_info:
        sp.resilient_get_multiple_analysis("egypt", "1D", ["EGX:ASCM"])

    assert len(calls) == 1, "one attempt, no retries"
    assert sleeps == []
    msg = str(exc_info.value)
    # The prefix humanize_upstream_error passes through unchanged.
    assert msg.startswith("Upstream TradingView scanner returned transient")
    assert "only attempt" in msg and "did not retry" in msg
    assert "Wait ~60s" in msg


def test_a_success_ends_the_refusal(monkeypatch, sleeps):
    _fake_ta(monkeypatch, lambda n, s: {"EGX:ASCM": "live"})
    sp._record_ta_failure()
    assert sp._ta_refusal_age_s() is not None

    assert sp.resilient_get_multiple_analysis("egypt", "1D", ["EGX:ASCM"]) == {"EGX:ASCM": "live"}
    assert sp._ta_refusal_age_s() is None
    assert sp._LAST_TA_FAILURE_TS == 0.0


def test_the_first_failure_of_a_burst_keeps_the_retry_schedule(monkeypatch, sleeps):
    # No refusal on record: a blip still gets its two retries (an earlier
    # one-retry experiment on the hosted server cost ~5pt of error rate).
    calls = _fake_ta(monkeypatch, lambda n, s: {"EGX:ASCM": "ok"} if n == 3 else _refuse())

    assert sp.resilient_get_multiple_analysis("egypt", "1D", ["EGX:ASCM"]) == {"EGX:ASCM": "ok"}
    assert len(calls) == 3
    assert sleeps == [0.01, 0.02]


def test_retries_stop_once_another_fetch_has_concluded_a_refusal(monkeypatch, sleeps):
    def behaviour(n, symbols):
        sp._record_ta_failure()  # a parallel call used up its attempts meanwhile
        raise _empty_body()

    calls = _fake_ta(monkeypatch, behaviour)
    with pytest.raises(RuntimeError) as exc_info:
        sp.resilient_get_multiple_analysis("egypt", "1D", ["EGX:ASCM"])

    assert len(calls) == 1
    assert sleeps == []
    assert "stopped retrying" in str(exc_info.value)


def test_a_ta_refusal_does_not_slow_the_scanner_path(sleeps):
    sp._record_ta_failure()

    class FakeQuery:
        def get_scanner_data(self, cookies=None):
            return (1, "df")

    assert sp._scan_with_retry(FakeQuery()) == (1, "df")
    assert sleeps == [], "scanner requests kept working through TA refusals"


def test_a_scanner_failure_still_cools_down_the_scanner_path(sleeps):
    class FailingQuery:
        def get_scanner_data(self, cookies=None):
            raise _empty_body()

    with pytest.raises(RuntimeError):
        sp._scan_with_retry(FailingQuery())
    assert sp._ta_refusal_age_s() is None, "a scanner failure is not a TA refusal"
    sleeps.clear()

    sp._wait_for_failure_cooldown()
    assert len(sleeps) == 1 and 0 < sleeps[0] <= 15


# ── Budget ───────────────────────────────────────────────────────────────────

def test_the_budget_cuts_the_attempt_timeout_and_skips_a_retry_it_cannot_cover(monkeypatch, sleeps):
    monkeypatch.setenv("TRADINGVIEW_MCP_RETRY_DELAYS", "5.0")
    calls = _fake_ta(monkeypatch, lambda n, s: _refuse())

    with sp.ta_call(deadline_s=3.0), pytest.raises(RuntimeError) as exc_info:
        sp.resilient_get_multiple_analysis("egypt", "1D", ["EGX:ASCM"])

    assert len(calls) == 1
    assert 2.0 <= calls[0]["timeout"] <= 3.0
    assert sleeps == []
    assert "time budget" in str(exc_info.value)


def test_without_a_ta_call_there_is_no_budget(monkeypatch, sleeps):
    calls = _fake_ta(monkeypatch, lambda n, s: {"EGX:ASCM": "ok"})
    sp.resilient_get_multiple_analysis("egypt", "1D", ["EGX:ASCM"])
    assert calls[0]["timeout"] == sp._socket_timeout_s()


def test_ta_call_time_left_has_a_cap_and_a_floor(monkeypatch):
    assert sp.ta_call_time_left(None, 10.0) == 10.0
    assert sp.ta_call_time_left({"deadline_at": None}, 10.0) == 10.0
    now = sp._time.monotonic()
    assert sp.ta_call_time_left({"deadline_at": now + 100}, 10.0) == 10.0
    assert sp.ta_call_time_left({"deadline_at": now + 5}, 10.0) == pytest.approx(5.0, abs=0.5)
    assert sp.ta_call_time_left({"deadline_at": now - 1}, 10.0) == sp._MIN_ATTEMPT_S


# ── coin_analysis ────────────────────────────────────────────────────────────

def _analysis(**overrides):
    ind = defaultdict(lambda: None)
    ind.update({
        "close": 80_600.0, "open": 80_500.0, "high": 80_800.0, "low": 80_400.0,
        "volume": 1_000.0, "RSI": 55.0, "change": 0.4, "Recommend.All": 0.3,
        "MACD.macd": 5.0, "MACD.signal": 3.0, "EMA20": 80_100.0, "EMA50": 79_000.0,
        "SMA20": 80_300.0, "BB.upper": 81_000.0, "BB.lower": 79_600.0,
    })
    ind.update(overrides)
    return SimpleNamespace(indicators=ind, summary={"RECOMMENDATION": "BUY"},
                           time=None, exchange="BINANCE", symbol="BTCUSDT")


@pytest.fixture
def atr_lookups(monkeypatch):
    seen: list = []

    def fake_atr(ticker, screener, timeframe=None, timeout=10.0):
        seen.append({"ticker": ticker, "timeout": timeout})
        return 720.0

    monkeypatch.setattr(sp, "fetch_atr_for_ticker", fake_atr)
    monkeypatch.setattr(screener_service, "_TA_AVAILABLE", True)
    return seen


def test_coin_analysis_says_when_its_numbers_are_stale(monkeypatch, sleeps, atr_lookups):
    """The 13 Nov case: gold 4h after TradingView refused, an hour-old answer."""
    _fake_ta(monkeypatch, lambda n, s: {"BINANCE:BTCUSDT": _analysis()} if n == 1 else _refuse())
    first = screener_service.analyze_coin("BTCUSDT", "binance", "4h")
    assert first["timestamp"] == "real-time" and "data_note" not in first
    atr_lookups.clear()
    _expire_fresh(("ta_multi_v2", "crypto", "4h", ("BINANCE:BTCUSDT",)), by=3633.0)
    sp._record_ta_failure()

    out = screener_service.analyze_coin("BTCUSDT", "binance", "4h")

    assert out["timestamp"] == "delayed"
    assert out["data_age_seconds"] == pytest.approx(3633, abs=5)
    assert "about 61 min ago" in out["data_note"]
    assert "ATR" in out["data_note"]
    assert atr_lookups == [], "no live ATR next to stale indicators"
    assert out["price_data"]["close"] == 80_600.0
    assert sleeps == []


def test_coin_analysis_live_answer_fits_the_atr_lookup_into_the_budget(monkeypatch, sleeps, atr_lookups):
    monkeypatch.setenv("TRADINGVIEW_MCP_TA_DEADLINE_S", "5")
    _fake_ta(monkeypatch, lambda n, s: {"BINANCE:BTCUSDT": _analysis()})

    out = screener_service.analyze_coin("BTCUSDT", "binance", "4h")

    assert out["timestamp"] == "real-time"
    assert "data_note" not in out and "data_age_seconds" not in out
    assert len(atr_lookups) == 1
    assert 2.0 <= atr_lookups[0]["timeout"] <= 5.0
    assert out["atr"]["value"] == 720.0


def test_coin_analysis_outage_without_a_stale_copy_is_a_fast_retryable_error(monkeypatch, sleeps, atr_lookups):
    _fake_ta(monkeypatch, lambda n, s: _refuse())
    sp._record_ta_failure()

    out = screener_service.analyze_coin("BTCUSDT", "binance", "4h")

    err = out["error"]
    assert err["code"] == "UPSTREAM_ERROR"
    assert err["retryable"] is True and err["retry_after_s"] == 60
    assert "did not retry" in err["message"]
    assert sleeps == []
