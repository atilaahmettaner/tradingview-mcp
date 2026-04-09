from __future__ import annotations
from typing import List, Dict, Any, Optional
from ..types import tf_to_tv_resolution as _tf_to_tv_resolution
from ..utils.validators import get_market_type


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

    total, df = q.get_scanner_data(cookies=cookies)

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

    total, df = q.get_scanner_data(cookies=cookies)
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
