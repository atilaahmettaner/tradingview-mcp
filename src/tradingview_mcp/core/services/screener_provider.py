from __future__ import annotations
from typing import List, Dict, Any, Optional, Tuple
from ..utils.validators import get_market_type
import json as _json
import os as _os
import random as _random
import socket as _socket
import sys as _sys
import time as _time
from threading import RLock as _RLock, Semaphore as _Semaphore, Lock as _Lock


# --- Socket-level timeout (added 2026-05-20) ------------------------------
# Critical: tradingview_ta and tradingview-screener use urllib without an
# explicit timeout, so when scanner.tradingview.com opens a connection then
# stops sending bytes, calls hang INDEFINITELY. The retry layer can't fire
# because no exception is ever raised. Set socket default timeout so any
# stalled HTTP call fails with socket.timeout within a bounded window — the
# retry layer then catches it (TimeoutError is now treated as transient).
#
# Tunable: TRADINGVIEW_MCP_SOCKET_TIMEOUT (default 20 seconds).
def _socket_timeout_s() -> float:
    try:
        return max(1.0, float(_os.environ.get('TRADINGVIEW_MCP_SOCKET_TIMEOUT', '20')))
    except Exception:
        return 20.0


_SOCKET_TIMEOUT_APPLIED = False


def _ensure_socket_timeout() -> None:
    """Apply socket.setdefaulttimeout once per process. Idempotent."""
    global _SOCKET_TIMEOUT_APPLIED
    if _SOCKET_TIMEOUT_APPLIED:
        return
    t = _socket_timeout_s()
    try:
        _socket.setdefaulttimeout(t)
        _SOCKET_TIMEOUT_APPLIED = True
        try:
            print(
                f"[tradingview_mcp] socket default timeout set to {t:.1f}s",
                file=_sys.stderr,
            )
        except Exception:
            pass
    except Exception:
        pass


# Apply at module import time so all TV HTTP calls inherit the timeout.
_ensure_socket_timeout()


# --- Resilience layer (added 2026-05-13, hardened 2026-05-20) --------------
# TradingView's scanner.tradingview.com endpoint occasionally returns an empty
# body on transient hiccups, causing tradingview-screener to raise
# json.JSONDecodeError("Expecting value: line 1 column 1 (char 0)").
# We retry with exponential backoff (+ jitter) and cache successful results
# (with a stale-while-error fallback) so transient outages don't surface to
# skill callers.
#
# 2026-05-20 hardening:
# - Added ±20% jitter so parallel callers don't form synchronized retry
#   storms (the 5-stock parallel batch failure mode).
# - Added stale-while-error cache: on full retry exhaustion, return the most
#   recent successful result (up to TRADINGVIEW_MCP_STALE_TTL=6h old).
#   This is the primary defense against deep outages — for repeat queries
#   we always serve from cache rather than burn long retries.
# - Final terminal error now includes attempt count, total wait, and an
#   explicit "wait N seconds before retry" suggestion (no more bare
#   JSONDecodeError surfacing to skill callers).
# - Routed the 3 remaining direct ``q.get_scanner_data()`` callsites
#   (egx_fibonacci, screener_service.multi_changes, screener_service.scan)
#   through ``_scan_with_retry`` so they share the resilience layer.
#
# Retry budget design: kept moderate (~5s of backoff) so interactive tools fail
# clearly rather than feeling "stuck". For sustained outages we rely on
# the 6h stale cache to serve previously-seen symbols.
#
# Tunables (env vars):
#   TRADINGVIEW_MCP_CACHE_TTL    default 60   (seconds — fresh cache)
#   TRADINGVIEW_MCP_STALE_TTL    default 21600 (6 hours — fallback cache)
#   TRADINGVIEW_MCP_RETRY_DELAYS default "1.0,4.0"
#   TRADINGVIEW_MCP_RETRY_JITTER default 0.2  (±20% jitter on each delay)
#   TRADINGVIEW_MCP_FAILURE_COOLDOWN_S default 15 (seconds)

def _cache_ttl_s() -> float:
    try:
        return float(_os.environ.get('TRADINGVIEW_MCP_CACHE_TTL', '60'))
    except Exception:
        return 60.0


def _stale_ttl_s() -> float:
    try:
        return max(0.0, float(_os.environ.get('TRADINGVIEW_MCP_STALE_TTL', '21600')))
    except Exception:
        return 21600.0


def _retry_delays() -> tuple:
    # Tighter default 2026-05-20 hardening: with socket timeout now bounding
    # each attempt to ~20s, we only need 2-3 retries before stale fallback
    # or terminal error. Previous 4-retry budget made interactive callers
    # feel "stuck" when upstream was truly dead.
    raw = _os.environ.get('TRADINGVIEW_MCP_RETRY_DELAYS', '1.0,4.0')
    try:
        return tuple(float(x) for x in raw.split(',') if x.strip())
    except Exception:
        return (1.0, 4.0)


def _retry_jitter() -> float:
    try:
        return max(0.0, min(1.0, float(_os.environ.get('TRADINGVIEW_MCP_RETRY_JITTER', '0.2'))))
    except Exception:
        return 0.2


def _jittered(delay: float) -> float:
    """Apply ±jitter to a delay so parallel callers don't synchronize retries."""
    j = _retry_jitter()
    if j <= 0 or delay <= 0:
        return delay
    return max(0.0, delay * (1.0 + _random.uniform(-j, j)))


# --- Shared failure cooldown (added 2026-05-19) ---------------------------
# When a call exhausts all retries (sustained upstream outage), the next
# call shouldn't immediately re-hammer with another full retry round —
# that just compounds load on a struggling upstream. After a full-retry
# failure, subsequent calls wait up to TRADINGVIEW_MCP_FAILURE_COOLDOWN_S
# seconds before starting their own retry sequence, giving upstream room
# to recover. The cooldown decays as time passes since last failure.
def _failure_cooldown_s() -> float:
    # Tightened 2026-05-20: 15s is enough to absorb a brief upstream blip
    # without compounding wait time across multiple skill calls.
    try:
        return max(0.0, float(_os.environ.get('TRADINGVIEW_MCP_FAILURE_COOLDOWN_S', '15')))
    except Exception:
        return 15.0


_LAST_TA_FAILURE_TS: float = 0.0
_TA_FAILURE_LOCK = _Lock()


def _record_ta_failure() -> None:
    global _LAST_TA_FAILURE_TS
    with _TA_FAILURE_LOCK:
        _LAST_TA_FAILURE_TS = _time.time()


def _wait_for_failure_cooldown() -> None:
    """If a previous call recently exhausted all retries, sleep until the
    cooldown elapses before starting a new retry sequence."""
    cooldown = _failure_cooldown_s()
    if cooldown <= 0:
        return
    with _TA_FAILURE_LOCK:
        ts = _LAST_TA_FAILURE_TS
    if ts == 0.0:
        return
    elapsed = _time.time() - ts
    if elapsed < cooldown:
        wait = cooldown - elapsed
        try:
            print(
                f"[tradingview_mcp] failure cooldown active, sleeping {wait:.1f}s",
                file=_sys.stderr,
            )
        except Exception:
            pass
        _time.sleep(wait)


# --- Auth + proxy + circuit breaker (added 2026-06-03) ---------------------
# Root cause of the recurring daily empty-body outage: anonymous, single-IP,
# bot-UA scraping of scanner.tradingview.com gets rate-limited (TradingView
# returns an empty 200/429 body -> JSONDecodeError "Expecting value"). Three
# mitigations, applied here:
#   1. PROXY    — route requests through the (already-built) Webshare rotating
#                 proxy so traffic isn't all from one IP.
#   2. COOKIE   — authenticate the screener path with a logged-in TradingView
#                 session cookie; authenticated requests get far higher limits
#                 than anonymous scraping. (Path A / tradingview_ta can't take a
#                 cookie, so it relies on the proxy; Path B / get_scanner_data
#                 gets both.)
#   3. CIRCUIT  — a fail-fast breaker that stops re-hammering a blocked
#                 endpoint for a cooldown window instead of every call
#                 re-walking the retry ladder and deepening the block.
#                 (Distinct from TRADINGVIEW_MCP_FAILURE_COOLDOWN_S above,
#                 which sleeps before retrying; the circuit raises instead.)
#
# Secrets live in the gitignored repo-root .env (NOT .mcp.json, which is
# version-controlled). See .env.example:
#   TRADINGVIEW_COOKIE   raw cookie header, e.g. "sessionid=abc; sessionid_sign=def"
#   PROXY_USERNAME_PREFIX / PROXY_PASSWORD / PROXY_HOST  (Webshare)
#   TRADINGVIEW_MCP_CIRCUIT_COOLDOWN_S  seconds to hold the circuit open (0=off)

# Best-effort .env load so TRADINGVIEW_COOKIE is available regardless of import
# order (proxy_manager loads the same .env at import time).
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(
        dotenv_path=_os.path.join(_os.path.dirname(__file__), "../../../../.env"),
        override=False,
    )
except Exception:
    pass


def _tv_cookies():
    """Parse TRADINGVIEW_COOKIE ('k=v; k2=v2') into a dict for requests, or None.
    Logged-in requests dodge the anonymous-scraper rate limit that causes the
    daily empty-body outage."""
    raw = _os.environ.get('TRADINGVIEW_COOKIE', '').strip()
    if not raw:
        return None
    jar: Dict[str, str] = {}
    for part in raw.split(';'):
        part = part.strip()
        if not part or '=' not in part:
            continue
        k, v = part.split('=', 1)
        jar[k.strip()] = v.strip()
    return jar or None


def _tv_proxies():
    """requests-style proxies dict from the Webshare proxy manager, or None if
    not configured. Rotating IPs sidestep per-IP rate limiting."""
    try:
        from .proxy_manager import get_proxy
        return get_proxy()
    except Exception:
        return None


_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)


class _AuthRequestsShim:
    """Proxies the real ``requests`` module but injects the TradingView session
    cookie + a browser User-Agent into ``.post()`` calls. tradingview_ta (Path A,
    get_multiple_analysis / TA_Handler) hits the SAME scanner.tradingview.com
    endpoint as the screener but exposes no cookie parameter and ships a bot UA
    (``tradingview_ta/x.y.z``), so it gets anonymous-rate-limited. Replacing the
    module-level ``requests`` reference inside tradingview_ta.main with this shim
    makes Path A authenticated like Path B — without forking the vendored lib or
    changing its rich Analysis output. Only tradingview_ta is affected; every
    other module keeps its own untouched ``requests``."""

    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        return getattr(self._real, name)

    def post(self, url, **kwargs):
        cookies = _tv_cookies()
        if cookies and not kwargs.get("cookies"):
            kwargs["cookies"] = cookies
        headers = dict(kwargs.get("headers") or {})
        headers["User-Agent"] = _BROWSER_UA  # replace the self-identifying bot UA
        kwargs["headers"] = headers
        return self._real.post(url, **kwargs)


def _patch_tradingview_ta_auth() -> None:
    """Authenticate tradingview_ta's requests (cookie + browser UA) so Path A
    stops being anonymous — the same root-cause fix already applied to the
    screener (Path B). Idempotent; no-op if tradingview_ta isn't importable."""
    try:
        from tradingview_ta import main as _ta_main
    except Exception:
        return
    if getattr(_ta_main, "_tvmcp_auth_patched", False):
        return
    try:
        _ta_main.requests = _AuthRequestsShim(_ta_main.requests)
        _ta_main._tvmcp_auth_patched = True
    except Exception:
        pass


def _circuit_cooldown_s() -> float:
    try:
        return max(0.0, float(_os.environ.get('TRADINGVIEW_MCP_CIRCUIT_COOLDOWN_S', '0')))
    except Exception:
        return 0.0


_CIRCUIT_LOCK = _Lock()
_CIRCUIT_OPEN_UNTIL: float = 0.0


class ScreenerCircuitOpen(RuntimeError):
    """Raised when the scanner circuit breaker is open (endpoint recently
    failing). Surfaced fast to callers so a scan degrades instead of grinding."""


def _circuit_check() -> None:
    """Raise immediately if the circuit is open, instead of hammering a
    known-blocked endpoint and deepening the block. No-op when cooldown=0."""
    if _circuit_cooldown_s() <= 0:
        return
    with _CIRCUIT_LOCK:
        remaining = _CIRCUIT_OPEN_UNTIL - _time.time()
    if remaining > 0:
        raise ScreenerCircuitOpen(
            f"scanner circuit open ~{remaining:.0f}s (endpoint rate-limited); failing fast"
        )


def _circuit_record(success: bool) -> None:
    if _circuit_cooldown_s() <= 0:
        return
    global _CIRCUIT_OPEN_UNTIL
    with _CIRCUIT_LOCK:
        _CIRCUIT_OPEN_UNTIL = 0.0 if success else (_time.time() + _circuit_cooldown_s())


_SCREENER_CACHE: Dict[Tuple, Tuple[float, Any]] = {}
_SCREENER_CACHE_LOCK = _RLock()


def _cache_get(key: Tuple):
    """Return cached payload if fresh (within TRADINGVIEW_MCP_CACHE_TTL)."""
    ttl = _cache_ttl_s()
    if ttl <= 0:
        return None
    with _SCREENER_CACHE_LOCK:
        entry = _SCREENER_CACHE.get(key)
        if not entry:
            return None
        ts, payload = entry
        if _time.time() - ts > ttl:
            # Don't pop here — stale lookup below may still want it.
            return None
        return payload


def _cache_get_stale(key: Tuple) -> Optional[Tuple[float, Any]]:
    """Return (age_seconds, payload) if a stale-but-usable entry exists
    (older than fresh TTL, younger than stale TTL). Used as last-resort
    fallback when fresh upstream fetch fails persistently."""
    stale_ttl = _stale_ttl_s()
    if stale_ttl <= 0:
        return None
    with _SCREENER_CACHE_LOCK:
        entry = _SCREENER_CACHE.get(key)
        if not entry:
            return None
        ts, payload = entry
        age = _time.time() - ts
        if age > stale_ttl:
            _SCREENER_CACHE.pop(key, None)
            return None
        return (age, payload)


def _cache_set(key: Tuple, payload: Any) -> None:
    """Store payload. We always store (even if fresh TTL is 0) so the
    stale-while-error fallback can serve it later within STALE_TTL."""
    stale_ttl = _stale_ttl_s()
    fresh_ttl = _cache_ttl_s()
    if stale_ttl <= 0 and fresh_ttl <= 0:
        return
    with _SCREENER_CACHE_LOCK:
        _SCREENER_CACHE[key] = (_time.time(), payload)


# --- Throttle for tradingview_ta calls (added 2026-05-15) -----------------
# Caps in-flight TA calls and enforces minimum interval between call starts
# to prevent parallel skill batches from all hitting the empty-body
# rate-limit cliff at the same time. Retry alone (above) recovers from a hit
# but doesn't prevent it; this layer keeps us under the cliff.
#
# Tunables (env vars):
#   TRADINGVIEW_MCP_MAX_INFLIGHT    default 2 (max concurrent TA calls)
#   TRADINGVIEW_MCP_MIN_INTERVAL_S  default 0.5 (min seconds between starts)


def _max_inflight() -> int:
    try:
        return max(1, int(_os.environ.get('TRADINGVIEW_MCP_MAX_INFLIGHT', '2')))
    except Exception:
        return 2


def _min_interval_s() -> float:
    # Tightened 2026-05-20: now that each call is bounded by socket timeout,
    # we don't need a 1.5s gate between starts. 0.5s is enough to avoid
    # synchronized request bursts without serializing parallel batches.
    try:
        return max(0.0, float(_os.environ.get('TRADINGVIEW_MCP_MIN_INTERVAL_S', '0.5')))
    except Exception:
        return 0.5


_TA_SEMAPHORE = _Semaphore(_max_inflight())
_TA_INTERVAL_LOCK = _Lock()
_TA_LAST_CALL_TS: float = 0.0


def _ta_throttle_acquire() -> None:
    """Block until a slot is free AND min-interval since last call elapsed.
    Caller MUST pair with _ta_throttle_release() in a finally block."""
    global _TA_LAST_CALL_TS
    _TA_SEMAPHORE.acquire()
    try:
        with _TA_INTERVAL_LOCK:
            now = _time.time()
            wait = _min_interval_s() - (now - _TA_LAST_CALL_TS)
            if wait > 0:
                _time.sleep(wait)
                now = _time.time()
            _TA_LAST_CALL_TS = now
    except BaseException:
        _TA_SEMAPHORE.release()
        raise


def _ta_throttle_release() -> None:
    _TA_SEMAPHORE.release()


def _is_transient_screener_error(e: BaseException) -> bool:
    """True if the error looks like an upstream transient (empty body,
    JSON parse failure, connection reset, rate limit, or socket timeout)."""
    if isinstance(e, _json.JSONDecodeError):
        return True
    # socket.timeout, urllib's ReadTimeoutError, requests.exceptions.Timeout, etc.
    if isinstance(e, (TimeoutError, _socket.timeout)):
        return True
    msg = str(e)
    return any(s in msg for s in (
        'Expecting value',
        'Connection reset',
        'Connection aborted',
        'Read timed out',
        'timed out',
        'Temporary failure',
        'Max retries exceeded',
        'RemoteDisconnected',
    ))


def _format_transient_error(last_exc: BaseException, attempts: int, total_wait: float) -> str:
    """Build an actionable terminal error message for callers."""
    base = repr(last_exc)
    return (
        f"Upstream TradingView scanner returned transient errors on all "
        f"{attempts} attempts spanning {total_wait:.0f}s ({base}). "
        f"This is typically a 30-90s empty-body outage at scanner.tradingview.com. "
        f"Wait ~60s before retrying."
    )


def _scan_with_retry(q, cookies=None, proxies=None, cache_key: Optional[Tuple] = None):
    """Wrap Query.get_scanner_data with retries on transient TV outages.
    Self-configures the TradingView session cookie + Webshare proxy from env
    when not explicitly supplied, and honors the fail-fast circuit breaker.
    Returns (total, df). Re-raises on non-transient errors or on final failure.

    If ``cache_key`` is provided and all retries fail, attempts to return a
    stale-but-usable cached payload before raising — callers that pass a key
    get stale-while-error behavior automatically."""
    if cookies is None:
        cookies = _tv_cookies()
    if proxies is None:
        proxies = _tv_proxies()
    try:
        _circuit_check()  # fail fast if the endpoint is in a cooldown window
    except ScreenerCircuitOpen:
        # Degrade to stale data instead of raising when we can.
        if cache_key is not None:
            stale = _cache_get_stale(cache_key)
            if stale is not None:
                return stale[1]
        raise
    _wait_for_failure_cooldown()
    delays = (0.0,) + _retry_delays()  # immediate try, then back off
    last_exc: Optional[BaseException] = None
    total_wait = 0.0
    for i, delay in enumerate(delays):
        wait = _jittered(delay) if delay > 0 else 0.0
        if wait > 0:
            _time.sleep(wait)
            total_wait += wait
        try:
            result = q.get_scanner_data(cookies=cookies, proxies=proxies)
            _circuit_record(True)
            return result
        except Exception as e:  # noqa: BLE001 - intentionally broad, narrowed below
            if not _is_transient_screener_error(e):
                raise
            last_exc = e
            try:
                print(
                    f"[tradingview_mcp] transient scanner error (attempt {i+1}/{len(delays)}, "
                    f"slept {wait:.1f}s): {e!r}",
                    file=_sys.stderr,
                )
            except Exception:
                pass
            continue
    # All attempts exhausted — record failure so subsequent calls back off,
    # and open the circuit so we stop hammering a blocked endpoint.
    _record_ta_failure()
    _circuit_record(False)
    # Last-resort: stale-while-error fallback if we have a cache key
    if cache_key is not None:
        stale = _cache_get_stale(cache_key)
        if stale is not None:
            age, payload = stale
            try:
                print(
                    f"[tradingview_mcp] returning stale cache (age {age:.0f}s) after "
                    f"{len(delays)} failed scanner attempts",
                    file=_sys.stderr,
                )
            except Exception:
                pass
            return payload
    assert last_exc is not None
    raise RuntimeError(_format_transient_error(last_exc, len(delays), total_wait)) from last_exc


def resilient_get_multiple_analysis(screener, interval, symbols):
    """Drop-in replacement for tradingview_ta.get_multiple_analysis with the
    same resilience layer used by the screener calls (retry + cache + stale
    fallback). Required because coin_analysis / combined_analysis /
    multi_timeframe_analysis use tradingview_ta directly and hit the same
    transient JSON errors when TradingView's scanner endpoint returns an
    empty body."""
    try:
        from tradingview_ta import get_multiple_analysis as _gma  # type: ignore
    except Exception as e:
        raise ImportError("tradingview_ta is not installed") from e
    _patch_tradingview_ta_auth()  # Path A: authenticate via cookie + browser UA

    sym_key = tuple(sorted(symbols)) if symbols else ()
    cache_key = ('ta_multi_v1', screener, interval, sym_key)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        _circuit_check()  # fail fast if the endpoint is in a cooldown window
    except ScreenerCircuitOpen:
        # Degrade to stale data instead of raising when we can.
        stale = _cache_get_stale(cache_key)
        if stale is not None:
            return stale[1]
        raise
    _wait_for_failure_cooldown()
    proxies = _tv_proxies()  # tradingview_ta has no cookie param; proxy-protect it
    delays = (0.0,) + _retry_delays()
    last_exc: Optional[BaseException] = None
    total_wait = 0.0
    for i, delay in enumerate(delays):
        wait = _jittered(delay) if delay > 0 else 0.0
        if wait > 0:
            _time.sleep(wait)
            total_wait += wait
        try:
            _ta_throttle_acquire()
            try:
                # CRITICAL: tradingview_ta defaults timeout=None, which means
                # requests.post hangs FOREVER on stalled upstream. socket.setdefaulttimeout
                # does NOT apply to requests/urllib3. Pass timeout explicitly.
                result = _gma(
                    screener=screener,
                    interval=interval,
                    symbols=symbols,
                    timeout=_socket_timeout_s(),
                    proxies=proxies,
                )
            finally:
                _ta_throttle_release()
            _cache_set(cache_key, result)
            _circuit_record(True)
            return result
        except Exception as e:  # noqa: BLE001
            if not _is_transient_screener_error(e):
                raise
            last_exc = e
            try:
                print(
                    f"[tradingview_mcp] transient TA error (attempt {i+1}/{len(delays)}, "
                    f"slept {wait:.1f}s): {e!r}",
                    file=_sys.stderr,
                )
            except Exception:
                pass
            continue
    # All attempts exhausted — record failure so subsequent calls back off,
    # and open the circuit so we stop hammering a blocked endpoint.
    _record_ta_failure()
    _circuit_record(False)
    # Last-resort: stale-while-error fallback (up to TRADINGVIEW_MCP_STALE_TTL)
    stale = _cache_get_stale(cache_key)
    if stale is not None:
        age, payload = stale
        try:
            print(
                f"[tradingview_mcp] returning stale TA cache (age {age:.0f}s, symbols={symbols}) "
                f"after {len(delays)} failed attempts",
                file=_sys.stderr,
            )
        except Exception:
            pass
        return payload
    assert last_exc is not None
    raise RuntimeError(_format_transient_error(last_exc, len(delays), total_wait)) from last_exc


def _tf_to_tv_resolution(tf: Optional[str]) -> Optional[str]:
    """Map our timeframe to TradingView resolution suffix used in columns.
    Returns None if no mapping (means: no suffix).
    """
    if not tf:
        return None
    m = {
        '5m': '5',
        '15m': '15',
        '1h': '60',
        '4h': '240',
        '1D': '1D',
        '1W': '1W',
        '1M': '1M',
    }
    return m.get(tf)


def fetch_atr_for_tickers(
    tickers: List[str],
    screener_market: str,
    timeframe: Optional[str] = None,
    timeout: float = 10.0,
) -> Dict[str, Optional[float]]:
    """Batch-fetch ATR(14) for many tickers in a single scanner POST.

    Same workaround as :func:`fetch_atr_for_ticker` but issues one HTTP request
    for all tickers — important for callers like ``analyze_egx_index`` which
    process 200-symbol batches and cannot afford a fan-out of N requests.

    Args:
        tickers:          Fully-qualified TradingView symbols
                          (e.g. ``["EGX:COMI", "EGX:HRHO"]``). Empty list → ``{}``.
        screener_market:  Scanner market path segment (``"crypto"``, ``"egypt"``,
                          ``"america"``, …) — the same value passed as
                          ``screener`` to ``tradingview_ta``.
        timeframe:        Optional timeframe (``5m``, ``15m``, ``1h``, ``4h``,
                          ``1D``, ``1W``, ``1M``). When omitted the daily ATR is
                          returned.

    Returns a dict keyed by ticker. Every input ticker is present in the
    output; missing/failed values are ``None``. Any whole-call failure (network,
    parse, missing requests) returns ``{ticker: None for ticker in tickers}``
    so callers can iterate without special-casing.
    """
    if not tickers or not screener_market:
        return {t: None for t in tickers}
    try:
        import requests  # type: ignore
    except ImportError:
        return {t: None for t in tickers}

    suffix = _tf_to_tv_resolution(timeframe)
    # The scanner exposes daily ATR as the bare "ATR" column. Asking for
    # "ATR|1D" returns null on every market we tested (crypto, egypt, …).
    # Weekly and monthly DO require their suffix (ATR|1W, ATR|1M).
    if suffix == "1D":
        suffix = None
    col = f"ATR|{suffix}" if suffix else "ATR"
    url = f"https://scanner.tradingview.com/{screener_market}/scan"
    payload = {
        "symbols": {"tickers": list(tickers), "query": {"types": []}},
        "columns": [col],
    }
    try:
        resp = requests.post(
            url, json=payload, timeout=timeout,
            proxies=_tv_proxies(), cookies=_tv_cookies(),
        )
        resp.raise_for_status()
        body = resp.json()
    except Exception:  # noqa: BLE001 — graceful degrade
        return {t: None for t in tickers}

    rows = body.get("data") if isinstance(body, dict) else None
    out: Dict[str, Optional[float]] = {t: None for t in tickers}
    if not isinstance(rows, list):
        return out

    for row in rows:
        if not isinstance(row, dict):
            continue
        sym = row.get("s")
        values = row.get("d") or []
        if not sym or not values:
            continue
        raw = values[0]
        if raw is None:
            out[sym] = None
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            out[sym] = None
            continue
        # NaN survives float() but is toxic downstream (stop_loss = close - 1.5*nan
        # propagates silently). Treat as missing.
        out[sym] = val if val == val else None  # NaN != NaN by IEEE-754
    return out


def fetch_atr_for_ticker(
    ticker: str,
    screener_market: str,
    timeframe: Optional[str] = None,
    timeout: float = 10.0,
) -> Optional[float]:
    """Fetch ATR(14) for a single ticker via TradingView's scanner endpoint.

    Thin wrapper around :func:`fetch_atr_for_tickers` kept for the single-symbol
    call sites that don't need batching (``analyze_coin``,
    ``generate_egx_trade_plan``, ``analyze_egx_fibonacci``).
    """
    if not ticker or not screener_market:
        return None
    return fetch_atr_for_tickers([ticker], screener_market, timeframe, timeout).get(ticker)


def fetch_screener_indicators(
    exchange: str,
    symbols: Optional[List[str]] = None,
    limit: Optional[int] = None,
    timeframe: Optional[str] = None,
    cookies=None,
) -> List[Dict[str, Any]]:
    """
    Fetch indicator columns via TradingView-Screener.
    Two modes:
    - Tickers mode: pass symbols => .set_tickers(*symbols)
    - Exchange scan mode: pass symbols=None/[] => filter by exchange using .where(Column('exchange') == <EXCHANGE>)

    Args:
      exchange: e.g. 'kucoin' or 'binance'. Case-insensitive.
      symbols: list of 'EXCHANGE:SYMBOL' tickers. If empty/None, scans by exchange.
      limit: optional limit of rows to return.
      timeframe: optional timeframe like '5m', '15m', '1h', '4h', '1D', '1W', '1M'.
      cookies: optional requests cookies for live data.

    Returns: List[{ 'symbol': 'EXCHANGE:PAIR', 'indicators': {...} }]
    """
    try:
        from tradingview_screener import Query
        from tradingview_screener.column import Column
    except Exception as e:
        raise ImportError("tradingview-screener is not installed. Please add it to requirements.txt and install.") from e

    market = get_market_type(exchange) if exchange else 'crypto'
    base_cols = ['open', 'close', 'SMA20', 'BB.upper', 'BB.lower', 'EMA50', 'RSI', 'volume']

    suffix = _tf_to_tv_resolution(timeframe)
    cols = [f"{c}|{suffix}" if suffix else c for c in base_cols]

    q = Query().set_markets(market).select(*cols)

    exchange_code = (exchange or '').upper()

    if symbols:
        # Tickers mode
        q = q.set_tickers(*symbols)
    else:
        # Exchange scan mode (no symbol list). Filter by exchange and type via markets
        if exchange_code:
            q = q.where(Column('exchange') == exchange_code)

    if limit:
        q = q.limit(int(limit))

    # Cache key: scope to indicators_v1 to avoid collisions with multi_changes.
    _cache_key = (
        'indicators_v1',
        exchange_code,
        tuple(sorted(symbols)) if symbols else None,
        timeframe,
        int(limit) if limit else None,
    )
    _cached = _cache_get(_cache_key)
    if _cached is not None:
        total, df = _cached
    else:
        total, df = _scan_with_retry(q, cookies=cookies, cache_key=_cache_key)
        _cache_set(_cache_key, (total, df))

    rows: List[Dict[str, Any]] = []
    if df is None or df.empty:
        return rows

    # If we used timeframe suffix (e.g., 'close|240'), normalize column names back to base (e.g., 'close')
    df.rename(columns=lambda c: c.split('|')[0] if isinstance(c, str) else c, inplace=True)

    for _, row in df.iterrows():
        symbol = row.get('ticker')
        indicators = {
            'open': row.get('open'),
            'close': row.get('close'),
            'SMA20': row.get('SMA20'),
            'BB.upper': row.get('BB.upper'),
            'BB.lower': row.get('BB.lower'),
            'EMA50': row.get('EMA50'),
            'RSI': row.get('RSI'),
            'volume': row.get('volume'),
        }
        rows.append({'symbol': symbol, 'indicators': indicators})

    return rows


def fetch_screener_multi_changes(
    exchange: str,
    symbols: Optional[List[str]] = None,
    timeframes: Optional[List[str]] = None,
    base_timeframe: str = '4h',
    limit: Optional[int] = None,
    cookies=None,
) -> List[Dict[str, Any]]:
    """
    Fetch multi-timeframe open/close to compute percentage changes per timeframe,
    and also include base timeframe indicators needed for BB metrics.

    Returns rows like:
      {
        'symbol': 'KUCOIN:ABCUSDT',
        'changes': { '15m': 1.23, '1h': 2.34, '4h': -0.56, '1D': 3.21 },
        'base_indicators': { 'open': ..., 'close': ..., 'SMA20': ..., 'BB.upper': ..., 'BB.lower': ..., 'volume': ... }
      }
    """
    try:
        from tradingview_screener import Query
        from tradingview_screener.column import Column
    except Exception as e:
        raise ImportError("tradingview-screener is not installed. Please add it to requirements.txt and install.") from e

    # Default timeframe set
    if not timeframes:
        timeframes = ['15m', '1h', '4h', '1D']

    def _tf_to_tv_resolution(tf: Optional[str]) -> Optional[str]:
        mapping = {
            '5m': '5',
            '15m': '15',
            '1h': '60',
            '4h': '240',
            '1D': '1D',
            '1W': '1W',
            '1M': '1M',
        }
        return mapping.get(tf or '')

    # Build suffix map and filter invalid tfs
    suffix_map: Dict[str, str] = {}
    for tf in timeframes:
        s = _tf_to_tv_resolution(tf)
        if s:
            suffix_map[tf] = s
    if not suffix_map:
        # fallback to base only
        bs = _tf_to_tv_resolution(base_timeframe) or '240'
        suffix_map = {base_timeframe: bs}

    base_suffix = _tf_to_tv_resolution(base_timeframe) or next(iter(suffix_map.values()))

    # Build columns: for each tf -> open|s, close|s; for base -> add BB cols and volume
    cols: List[str] = []
    seen: set[str] = set()
    for tf, s in suffix_map.items():
        for c in (f'open|{s}', f'close|{s}'):
            if c not in seen:
                cols.append(c); seen.add(c)
    for c in (f'SMA20|{base_suffix}', f'BB.upper|{base_suffix}', f'BB.lower|{base_suffix}', f'volume|{base_suffix}'):
        if c not in seen:
            cols.append(c); seen.add(c)

    market = get_market_type(exchange) if exchange else 'crypto'
    q = Query().set_markets(market).select(*cols)

    exchange_code = (exchange or '').upper()
    if symbols:
        q = q.set_tickers(*symbols)
    else:
        if exchange_code:
            q = q.where(Column('exchange') == exchange_code)
    if limit:
        q = q.limit(int(limit))

    # Cache key: scope to multichanges_v1 to avoid collisions with indicators.
    _cache_key = (
        'multichanges_v1',
        exchange_code,
        tuple(sorted(symbols)) if symbols else None,
        tuple(sorted(suffix_map.keys())),
        base_timeframe,
        int(limit) if limit else None,
    )
    _cached = _cache_get(_cache_key)
    if _cached is not None:
        total, df = _cached
    else:
        total, df = _scan_with_retry(q, cookies=cookies, cache_key=_cache_key)
        _cache_set(_cache_key, (total, df))

    rows: List[Dict[str, Any]] = []
    if df is None or df.empty:
        return rows

    # Iterate rows and compute changes per tf; prepare base indicators
    for _, row in df.iterrows():
        symbol = row.get('ticker')
        changes: Dict[str, Optional[float]] = {}
        for tf, s in suffix_map.items():
            op = row.get(f'open|{s}')
            cl = row.get(f'close|{s}')
            try:
                changes[tf] = ((cl - op) / op) * 100 if op not in (None, 0) and cl is not None else None
            except Exception:
                changes[tf] = None

        base_indicators = {
            'open': row.get(f'open|{base_suffix}'),
            'close': row.get(f'close|{base_suffix}'),
            'SMA20': row.get(f'SMA20|{base_suffix}'),
            'BB.upper': row.get(f'BB.upper|{base_suffix}'),
            'BB.lower': row.get(f'BB.lower|{base_suffix}'),
            'volume': row.get(f'volume|{base_suffix}'),
        }

        rows.append({'symbol': symbol, 'changes': changes, 'base_indicators': base_indicators})

    return rows
