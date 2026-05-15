from __future__ import annotations
from typing import List, Dict, Any, Optional, Tuple
from ..utils.validators import get_market_type
import json as _json
import os as _os
import sys as _sys
import time as _time
from threading import RLock as _RLock, Semaphore as _Semaphore, Lock as _Lock


# --- Resilience layer (added 2026-05-13) -----------------------------------
# TradingView's scanner.tradingview.com endpoint occasionally returns an empty
# body on transient hiccups, causing tradingview-screener to raise
# json.JSONDecodeError("Expecting value: line 1 column 1 (char 0)").
# We retry with exponential backoff and cache successful results briefly to
# absorb these blips without surfacing them to skill callers.
#
# Tunables (env vars):
#   TRADINGVIEW_MCP_CACHE_TTL   default 60 (seconds). Set 0 to disable cache.
#   TRADINGVIEW_MCP_RETRY_DELAYS default "0.5,1.5,4.0" (sec, comma-separated)

def _cache_ttl_s() -> float:
    try:
        return float(_os.environ.get('TRADINGVIEW_MCP_CACHE_TTL', '60'))
    except Exception:
        return 60.0


def _retry_delays() -> tuple:
    raw = _os.environ.get('TRADINGVIEW_MCP_RETRY_DELAYS', '0.5,1.5,4.0')
    try:
        return tuple(float(x) for x in raw.split(',') if x.strip())
    except Exception:
        return (0.5, 1.5, 4.0)


_SCREENER_CACHE: Dict[Tuple, Tuple[float, Tuple[int, Any]]] = {}
_SCREENER_CACHE_LOCK = _RLock()


def _cache_get(key: Tuple):
    ttl = _cache_ttl_s()
    if ttl <= 0:
        return None
    with _SCREENER_CACHE_LOCK:
        entry = _SCREENER_CACHE.get(key)
        if not entry:
            return None
        ts, payload = entry
        if _time.time() - ts > ttl:
            _SCREENER_CACHE.pop(key, None)
            return None
        return payload


def _cache_set(key: Tuple, payload: Tuple[int, Any]) -> None:
    if _cache_ttl_s() <= 0:
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
#   TRADINGVIEW_MCP_MAX_INFLIGHT    default 4 (max concurrent TA calls)
#   TRADINGVIEW_MCP_MIN_INTERVAL_S  default 0.8 (min seconds between starts)


def _max_inflight() -> int:
    try:
        return max(1, int(_os.environ.get('TRADINGVIEW_MCP_MAX_INFLIGHT', '4')))
    except Exception:
        return 4


def _min_interval_s() -> float:
    try:
        return max(0.0, float(_os.environ.get('TRADINGVIEW_MCP_MIN_INTERVAL_S', '0.8')))
    except Exception:
        return 0.8


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
    JSON parse failure, connection reset, rate limit message)."""
    if isinstance(e, _json.JSONDecodeError):
        return True
    msg = str(e)
    return any(s in msg for s in (
        'Expecting value',
        'Connection reset',
        'Connection aborted',
        'Read timed out',
        'Temporary failure',
    ))


def _scan_with_retry(q, cookies=None):
    """Wrap Query.get_scanner_data with retries on transient TV outages.
    Returns (total, df). Re-raises on non-transient errors or on final failure."""
    delays = (0.0,) + _retry_delays()  # immediate try, then back off
    last_exc: Optional[BaseException] = None
    for i, delay in enumerate(delays):
        if delay > 0:
            _time.sleep(delay)
        try:
            return q.get_scanner_data(cookies=cookies)
        except Exception as e:  # noqa: BLE001 - intentionally broad, narrowed below
            if not _is_transient_screener_error(e):
                raise
            last_exc = e
            try:
                print(
                    f"[tradingview_mcp] transient scanner error (attempt {i+1}/{len(delays)}): {e!r}",
                    file=_sys.stderr,
                )
            except Exception:
                pass
            continue
    # All attempts exhausted
    assert last_exc is not None
    raise last_exc


def resilient_get_multiple_analysis(screener, interval, symbols):
    """Drop-in replacement for tradingview_ta.get_multiple_analysis with the
    same resilience layer used by the screener calls (retry + 60s TTL cache).
    Required because coin_analysis / combined_analysis / multi_timeframe_analysis
    use tradingview_ta directly and hit the same transient JSON errors when
    TradingView's scanner endpoint returns an empty body."""
    try:
        from tradingview_ta import get_multiple_analysis as _gma  # type: ignore
    except Exception as e:
        raise ImportError("tradingview_ta is not installed") from e

    sym_key = tuple(sorted(symbols)) if symbols else ()
    cache_key = ('ta_multi_v1', screener, interval, sym_key)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    delays = (0.0,) + _retry_delays()
    last_exc: Optional[BaseException] = None
    for i, delay in enumerate(delays):
        if delay > 0:
            _time.sleep(delay)
        try:
            _ta_throttle_acquire()
            try:
                result = _gma(screener=screener, interval=interval, symbols=symbols)
            finally:
                _ta_throttle_release()
            _cache_set(cache_key, result)
            return result
        except Exception as e:  # noqa: BLE001
            if not _is_transient_screener_error(e):
                raise
            last_exc = e
            try:
                print(
                    f"[tradingview_mcp] transient TA error (attempt {i+1}/{len(delays)}): {e!r}",
                    file=_sys.stderr,
                )
            except Exception:
                pass
            continue
    assert last_exc is not None
    raise last_exc


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
        total, df = _scan_with_retry(q, cookies=cookies)
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
        total, df = _scan_with_retry(q, cookies=cookies)
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
