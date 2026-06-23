"""Generic TTL cache + ``@cached`` decorator for read-only services.

Extracted from ``screener_provider.py`` so the same primitives can be reused
across services that hit external HTTP APIs (Yahoo, RSS feeds, Reddit, Yahoo
Options). All caches are in-memory, thread-safe, and TTL-tunable via env
vars at call time (so tests can monkeypatch env without instance churn).

Design:

- ``TTLCache`` is TTL-agnostic — the caller supplies the freshness window on
  every ``.get()`` call. This makes it cheap to read env vars at call time
  and lets one instance serve multiple semantics (fresh window + stale
  window, as ``screener_provider`` uses for stale-while-error).
- ``MISS`` sentinel distinguishes a cache miss from a cached ``None`` value.
- ``@cached`` decorator wraps a function so a key is computed via ``key_fn``,
  fresh TTL is read from ``ttl_env``, and an optional ``cache_unless``
  predicate suppresses caching of error responses.
"""
from __future__ import annotations

import functools
import os
import time
from threading import RLock
from typing import Any, Callable, Dict, Hashable, Optional, Tuple


__all__ = ["TTLCache", "MISS", "cached", "env_ttl"]


class _Miss:
    """Singleton sentinel used to distinguish miss from a cached ``None``."""

    _instance: Optional["_Miss"] = None

    def __new__(cls) -> "_Miss":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return "<cache.MISS>"

    def __bool__(self) -> bool:  # pragma: no cover - cosmetic
        return False


MISS: _Miss = _Miss()


class TTLCache:
    """Thread-safe key→payload cache with caller-supplied TTLs.

    The instance does not store its own TTL — every read passes the TTL it
    cares about. This lets the same store serve both a short fresh window
    and a long stale-while-error window from one set of entries.
    """

    def __init__(self) -> None:
        self._store: Dict[Hashable, Tuple[float, Any]] = {}
        self._lock = RLock()
        self.hits = 0
        self.misses = 0

    # -- core ops -----------------------------------------------------------

    def get(self, key: Hashable, ttl_s: float) -> Any:
        """Return cached payload if its age ≤ ``ttl_s``, else ``MISS``.

        ``ttl_s`` ≤ 0 disables the cache (always returns ``MISS``) but does
        NOT evict the entry — a subsequent ``get_with_age`` call can still
        retrieve it within a longer window.
        """
        if ttl_s <= 0:
            return MISS
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                self.misses += 1
                return MISS
            ts, payload = entry
            if time.time() - ts > ttl_s:
                self.misses += 1
                return MISS
            self.hits += 1
            return payload

    def get_with_age(
        self, key: Hashable, max_age_s: float
    ) -> Optional[Tuple[float, Any]]:
        """Return ``(age_seconds, payload)`` if entry exists within ``max_age_s``.

        Used for stale-while-error fallback. Returns ``None`` if no entry or
        the entry exceeds ``max_age_s`` — in which case the stale entry is
        also evicted so the cache doesn't grow unbounded on dead keys.
        """
        if max_age_s <= 0:
            return None
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            ts, payload = entry
            age = time.time() - ts
            if age > max_age_s:
                self._store.pop(key, None)
                return None
            return (age, payload)

    def set(self, key: Hashable, payload: Any) -> None:
        with self._lock:
            self._store[key] = (time.time(), payload)

    def invalidate(self, key: Hashable) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self.hits = 0
            self.misses = 0

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)


# ---------------------------------------------------------------------------
# Env helpers + decorator
# ---------------------------------------------------------------------------


def env_ttl(env_var: str, default_s: float) -> float:
    """Read a non-negative TTL (seconds) from environment, with a default.

    Re-read on every call so monkeypatched env in tests applies immediately.
    """
    raw = os.environ.get(env_var)
    if raw is None:
        return default_s
    try:
        v = float(raw)
    except ValueError:
        return default_s
    return v if v >= 0 else default_s


def cached(
    *,
    key_fn: Callable[..., Hashable],
    ttl_env: str,
    default_ttl: float,
    cache_unless: Optional[Callable[[Any], bool]] = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorate ``fn`` so its result is cached by ``key_fn(*args, **kwargs)``.

    Args:
        key_fn: Builds a hashable cache key from the call's args. Returned
            value is wrapped under the function's qualname so different
            decorated callables can never collide.
        ttl_env: Env var name read on every call. Setting it to ``0``
            disables caching at runtime.
        default_ttl: Fallback TTL in seconds when env var is unset/invalid.
        cache_unless: Optional predicate ``(result) -> bool``. If it returns
            True for a result, the result is returned to the caller but
            NOT stored — used to skip caching error responses like
            ``{"error": "..."}``.

    Wrapped function gains two attributes:
        - ``cache_clear()``: drop all entries
        - ``cache``: the underlying ``TTLCache`` for inspection/tests
    """
    cache = TTLCache()

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        namespace = getattr(fn, "__qualname__", fn.__name__)

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            ttl = env_ttl(ttl_env, default_ttl)
            key = (namespace, key_fn(*args, **kwargs))
            hit = cache.get(key, ttl)
            if hit is not MISS:
                return hit
            result = fn(*args, **kwargs)
            if cache_unless is None or not cache_unless(result):
                cache.set(key, result)
            return result

        wrapper.cache_clear = cache.clear  # type: ignore[attr-defined]
        wrapper.cache = cache  # type: ignore[attr-defined]
        return wrapper

    return decorator
