"""Unit tests for ``core/utils/cache.py``.

Covers TTLCache primitives (get/set/get_with_age/clear), the ``@cached``
decorator (key derivation, env-tunable TTL, error suppression via
``cache_unless``), and basic thread-safety.
"""
from __future__ import annotations

import threading
import time

import pytest

from tradingview_mcp.core.utils.cache import MISS, TTLCache, cached, env_ttl


# ---------------------------------------------------------------------------
# TTLCache primitives
# ---------------------------------------------------------------------------


def test_ttlcache_returns_miss_for_unknown_key():
    cache = TTLCache()
    assert cache.get("missing", ttl_s=10.0) is MISS


def test_ttlcache_hit_within_ttl():
    cache = TTLCache()
    cache.set("k", {"v": 1})
    assert cache.get("k", ttl_s=10.0) == {"v": 1}


def test_ttlcache_can_cache_none_value():
    """MISS sentinel lets us distinguish miss from a cached None payload."""
    cache = TTLCache()
    cache.set("k", None)
    # Cached value is None — but it's a real hit, not a miss.
    assert cache.get("k", ttl_s=10.0) is None
    assert cache.get("absent", ttl_s=10.0) is MISS


def test_ttlcache_expiry():
    cache = TTLCache()
    cache.set("k", "payload")
    # Stuff the timestamp backward so the entry is now "old".
    with cache._lock:
        ts, payload = cache._store["k"]
        cache._store["k"] = (ts - 100.0, payload)
    assert cache.get("k", ttl_s=10.0) is MISS


def test_ttlcache_zero_ttl_disables_get():
    cache = TTLCache()
    cache.set("k", "v")
    assert cache.get("k", ttl_s=0.0) is MISS
    # But entry remains for get_with_age:
    out = cache.get_with_age("k", max_age_s=10.0)
    assert out is not None
    assert out[1] == "v"


def test_ttlcache_get_with_age_returns_age_and_payload():
    cache = TTLCache()
    cache.set("k", "stale")
    with cache._lock:
        ts, payload = cache._store["k"]
        cache._store["k"] = (ts - 60.0, payload)
    out = cache.get_with_age("k", max_age_s=300.0)
    assert out is not None
    age, value = out
    assert value == "stale"
    assert 50.0 <= age <= 70.0  # ~60s old, with slack for test runtime


def test_ttlcache_get_with_age_evicts_too_old_entries():
    cache = TTLCache()
    cache.set("k", "ancient")
    with cache._lock:
        ts, payload = cache._store["k"]
        cache._store["k"] = (ts - 1000.0, payload)
    assert cache.get_with_age("k", max_age_s=300.0) is None
    # Entry should be evicted so cache doesn't grow unbounded on dead keys.
    assert "k" not in cache._store


def test_ttlcache_invalidate_drops_single_key():
    cache = TTLCache()
    cache.set("a", 1)
    cache.set("b", 2)
    cache.invalidate("a")
    assert cache.get("a", ttl_s=10.0) is MISS
    assert cache.get("b", ttl_s=10.0) == 2


def test_ttlcache_clear_resets_state():
    cache = TTLCache()
    cache.set("a", 1)
    cache.get("a", ttl_s=10.0)
    cache.get("missing", ttl_s=10.0)
    assert cache.hits == 1
    assert cache.misses == 1
    cache.clear()
    assert len(cache) == 0
    assert cache.hits == 0
    assert cache.misses == 0


def test_ttlcache_hits_and_misses_counted():
    cache = TTLCache()
    cache.set("k", 1)
    cache.get("k", ttl_s=10.0)
    cache.get("k", ttl_s=10.0)
    cache.get("absent", ttl_s=10.0)
    assert cache.hits == 2
    assert cache.misses == 1


# ---------------------------------------------------------------------------
# env_ttl
# ---------------------------------------------------------------------------


def test_env_ttl_default_when_unset(monkeypatch):
    monkeypatch.delenv("MY_TTL", raising=False)
    assert env_ttl("MY_TTL", 42.0) == 42.0


def test_env_ttl_reads_int_string(monkeypatch):
    monkeypatch.setenv("MY_TTL", "120")
    assert env_ttl("MY_TTL", 42.0) == 120.0


def test_env_ttl_reads_float_string(monkeypatch):
    monkeypatch.setenv("MY_TTL", "0.5")
    assert env_ttl("MY_TTL", 42.0) == 0.5


def test_env_ttl_falls_back_on_garbage(monkeypatch):
    monkeypatch.setenv("MY_TTL", "not-a-number")
    assert env_ttl("MY_TTL", 42.0) == 42.0


def test_env_ttl_clamps_negative_to_default(monkeypatch):
    monkeypatch.setenv("MY_TTL", "-5")
    assert env_ttl("MY_TTL", 42.0) == 42.0


# ---------------------------------------------------------------------------
# @cached decorator
# ---------------------------------------------------------------------------


def test_cached_returns_same_result_within_ttl(monkeypatch):
    monkeypatch.setenv("TEST_TTL", "60")
    calls = {"n": 0}

    @cached(key_fn=lambda x: x, ttl_env="TEST_TTL", default_ttl=30.0)
    def expensive(x: int) -> int:
        calls["n"] += 1
        return x * 2

    assert expensive(5) == 10
    assert expensive(5) == 10
    assert expensive(5) == 10
    assert calls["n"] == 1


def test_cached_different_keys_call_independently(monkeypatch):
    monkeypatch.setenv("TEST_TTL", "60")
    calls = {"n": 0}

    @cached(key_fn=lambda x: x, ttl_env="TEST_TTL", default_ttl=30.0)
    def f(x: int) -> int:
        calls["n"] += 1
        return x

    f(1); f(2); f(3); f(1); f(2)
    assert calls["n"] == 3


def test_cached_env_zero_disables_cache(monkeypatch):
    monkeypatch.setenv("TEST_TTL", "0")
    calls = {"n": 0}

    @cached(key_fn=lambda x: x, ttl_env="TEST_TTL", default_ttl=30.0)
    def f(x: int) -> int:
        calls["n"] += 1
        return x

    f(1); f(1); f(1)
    assert calls["n"] == 3


def test_cached_env_change_takes_effect_at_runtime(monkeypatch):
    """Re-reading env per call is the contract — monkeypatch flips behavior."""
    calls = {"n": 0}

    @cached(key_fn=lambda x: x, ttl_env="TEST_TTL", default_ttl=60.0)
    def f(x: int) -> int:
        calls["n"] += 1
        return x

    monkeypatch.setenv("TEST_TTL", "60")
    f(1); f(1)
    assert calls["n"] == 1

    # Disable cache at runtime
    monkeypatch.setenv("TEST_TTL", "0")
    f(1); f(1)
    assert calls["n"] == 3


def test_cached_uses_default_when_env_missing(monkeypatch):
    monkeypatch.delenv("TEST_TTL", raising=False)
    calls = {"n": 0}

    @cached(key_fn=lambda x: x, ttl_env="TEST_TTL", default_ttl=60.0)
    def f(x: int) -> int:
        calls["n"] += 1
        return x

    f(1); f(1)
    assert calls["n"] == 1


def test_cached_unless_skips_caching_errors(monkeypatch):
    """cache_unless predicate suppresses storage but still returns the result."""
    monkeypatch.setenv("TEST_TTL", "60")
    calls = {"n": 0}

    @cached(
        key_fn=lambda x: x,
        ttl_env="TEST_TTL",
        default_ttl=30.0,
        cache_unless=lambda r: isinstance(r, dict) and "error" in r,
    )
    def maybe_err(x: int) -> dict:
        calls["n"] += 1
        if x < 0:
            return {"error": "bad input"}
        return {"value": x}

    # Successful calls cache normally
    assert maybe_err(5) == {"value": 5}
    assert maybe_err(5) == {"value": 5}
    assert calls["n"] == 1

    # Error responses are returned but NOT cached
    assert maybe_err(-1) == {"error": "bad input"}
    assert maybe_err(-1) == {"error": "bad input"}
    assert calls["n"] == 3  # both -1 calls hit the underlying fn


def test_cached_isolated_per_decorated_function(monkeypatch):
    """Two decorated callables must not share a cache instance even when
    using identical key_fn and ttl_env."""
    monkeypatch.setenv("TEST_TTL", "60")

    @cached(key_fn=lambda x: x, ttl_env="TEST_TTL", default_ttl=30.0)
    def f1(x: int) -> str:
        return f"f1:{x}"

    @cached(key_fn=lambda x: x, ttl_env="TEST_TTL", default_ttl=30.0)
    def f2(x: int) -> str:
        return f"f2:{x}"

    assert f1(1) == "f1:1"
    assert f2(1) == "f2:1"


def test_cached_exposes_cache_clear(monkeypatch):
    monkeypatch.setenv("TEST_TTL", "60")
    calls = {"n": 0}

    @cached(key_fn=lambda x: x, ttl_env="TEST_TTL", default_ttl=30.0)
    def f(x: int) -> int:
        calls["n"] += 1
        return x

    f(1); f(1)
    assert calls["n"] == 1
    f.cache_clear()
    f(1)
    assert calls["n"] == 2


def test_cached_preserves_function_metadata():
    """functools.wraps must propagate name and docstring."""

    @cached(key_fn=lambda x: x, ttl_env="TEST_TTL", default_ttl=30.0)
    def my_function(x):
        """Docstring lives here."""
        return x

    assert my_function.__name__ == "my_function"
    assert "Docstring lives here." in (my_function.__doc__ or "")


def test_cached_uses_kwargs_in_key(monkeypatch):
    monkeypatch.setenv("TEST_TTL", "60")
    calls = {"n": 0}

    @cached(
        key_fn=lambda symbol, expiry=None: (symbol.upper(), expiry or ""),
        ttl_env="TEST_TTL",
        default_ttl=30.0,
    )
    def f(symbol, expiry=None):
        calls["n"] += 1
        return (symbol, expiry)

    f("aapl")
    f("AAPL")  # same key after upper
    f("aapl", expiry="2026-06-21")
    f("aapl", expiry="2026-06-21")
    assert calls["n"] == 2


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


def test_ttlcache_concurrent_set_and_get():
    cache = TTLCache()
    n_threads = 20
    n_ops = 200
    errors = []

    def worker(thread_id: int):
        try:
            for i in range(n_ops):
                key = (thread_id, i % 10)
                cache.set(key, thread_id * 1000 + i)
                got = cache.get(key, ttl_s=60.0)
                # got may be a later set from same thread; just ensure non-MISS
                assert got is not MISS
        except AssertionError as e:  # pragma: no cover - failure path
            errors.append(e)

    threads = [
        threading.Thread(target=worker, args=(t,)) for t in range(n_threads)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"thread errors: {errors}"


def test_cached_decorator_thread_safe():
    """Concurrent callers must all get the right result without exceptions,
    and a follow-up wave after the first batch settles must be served from
    cache. We don't single-flight concurrent misses — that would be
    over-engineering for read-only data — so the first wave may all miss.
    """

    call_count = {"n": 0}
    count_lock = threading.Lock()

    @cached(
        key_fn=lambda x: x,
        ttl_env="NEVER_SET_THIS_VAR",
        default_ttl=60.0,
    )
    def slow_fn(x: int) -> int:
        with count_lock:
            call_count["n"] += 1
        time.sleep(0.005)
        return x * 2

    # First wave: concurrent misses are allowed to race past .get()
    results: list[int] = []
    res_lock = threading.Lock()

    def worker():
        out = slow_fn(7)
        with res_lock:
            results.append(out)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 20
    assert all(r == 14 for r in results)

    # After the first wave settles, the entry is cached. A second wave must
    # NOT trigger any additional fn calls.
    before = call_count["n"]
    for _ in range(20):
        assert slow_fn(7) == 14
    assert call_count["n"] == before
