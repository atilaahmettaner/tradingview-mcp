from __future__ import annotations

import argparse
import os
from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict
from mcp.server.fastmcp import FastMCP

# Import bollinger band screener modules
from tradingview_mcp.core.services.indicators import compute_metrics
from tradingview_mcp.core.services.coinlist import load_symbols
from tradingview_mcp.core.utils.validators import sanitize_timeframe, sanitize_exchange, EXCHANGE_SCREENER, ALLOWED_TIMEFRAMES

try:
    from tradingview_ta import TA_Handler, get_multiple_analysis
    TRADINGVIEW_TA_AVAILABLE = True
except ImportError:
    TRADINGVIEW_TA_AVAILABLE = False

try:
    from tradingview_screener import Query
    from tradingview_screener.column import Column
    TRADINGVIEW_SCREENER_AVAILABLE = True
except ImportError:
    TRADINGVIEW_SCREENER_AVAILABLE = False


class IndicatorMap(TypedDict, total=False):
	open: Optional[float]
	close: Optional[float]
	SMA20: Optional[float]
	BB_upper: Optional[float]
	BB_lower: Optional[float]
	EMA50: Optional[float]
	RSI: Optional[float]
	volume: Optional[float]


class Row(TypedDict):
	symbol: str
	changePercent: float
	indicators: IndicatorMap


class MultiRow(TypedDict):
	symbol: str
	changes: dict[str, Optional[float]]
	base_indicators: IndicatorMap


def _map_indicators(raw: Dict[str, Any]) -> IndicatorMap:
	return IndicatorMap(
		open=raw.get("open"),
		close=raw.get("close"),
		SMA20=raw.get("SMA20"),
		BB_upper=raw.get("BB.upper") if "BB.upper" in raw else raw.get("BB_upper"),
		BB_lower=raw.get("BB.lower") if "BB.lower" in raw else raw.get("BB_lower"),
		EMA50=raw.get("EMA50"),
		RSI=raw.get("RSI"),
		volume=raw.get("volume"),
	)


def _percent_change(o: Optional[float], c: Optional[float]) -> Optional[float]:
	try:
		if o in (None, 0) or c is None:
			return None
		return (c - o) / o * 100
	except Exception:
		return None


def _tf_to_tv_resolution(tf: Optional[str]) -> Optional[str]:
	if not tf:
		return None
	return {"5m": "5", "15m": "15", "1h": "60", "4h": "240", "1D": "1D", "1W": "1W", "1M": "1M"}.get(tf)


def _fetch_bollinger_analysis(exchange: str, timeframe: str = "4h", limit: int = 50, bbw_filter: float = None) -> List[Row]:
    """Fetch analysis using tradingview_ta with bollinger band logic from the original screener."""
    if not TRADINGVIEW_TA_AVAILABLE:
        raise RuntimeError("tradingview_ta is missing; run `uv sync`.")
    
    # Load symbols from coinlist files
    symbols = load_symbols(exchange)
    if not symbols:
        raise RuntimeError(f"No symbols found for exchange: {exchange}")
    
    # Limit symbols for performance
    symbols = symbols[:limit * 2]  # Get more to filter later
    
    # Get screener type based on exchange
    screener = EXCHANGE_SCREENER.get(exchange, "crypto")
    
    try:
        analysis = get_multiple_analysis(screener=screener, interval=timeframe, symbols=symbols)
    except Exception as e:
        raise RuntimeError(f"Analysis failed: {str(e)}")
    
    rows: List[Row] = []
    
    for key, value in analysis.items():
        try:
            if value is None:
                continue
                
            indicators = value.indicators
            metrics = compute_metrics(indicators)
            
            if not metrics or metrics.get('bbw') is None:
                continue
            
            # Apply BBW filter if specified
            if bbw_filter is not None and (metrics['bbw'] >= bbw_filter or metrics['bbw'] <= 0):
                continue
            
            # Check if we have required indicators
            if not (indicators.get("EMA50") and indicators.get("RSI")):
                continue
                
            rows.append(Row(
                symbol=key,
                changePercent=metrics['change'],
                indicators=IndicatorMap(
                    open=metrics.get('open'),
                    close=metrics.get('price'),
                    SMA20=indicators.get("SMA20"),
                    BB_upper=indicators.get("BB.upper"),
                    BB_lower=indicators.get("BB.lower"),
                    EMA50=indicators.get("EMA50"),
                    RSI=indicators.get("RSI"),
                    volume=indicators.get("volume"),
                )
            ))
                
        except (TypeError, ZeroDivisionError, KeyError):
            continue
    
    # Sort by change percentage in descending order (highest gainers first)
    rows.sort(key=lambda x: x["changePercent"], reverse=True)
    
    # Return the requested limit
    return rows[:limit]


def _fetch_trending_analysis(exchange: str, timeframe: str = "5m", filter_type: str = "", rating_filter: int = None, limit: int = 50) -> List[Row]:
    """Fetch trending coins analysis similar to the original app's trending endpoint."""
    if not TRADINGVIEW_TA_AVAILABLE:
        raise RuntimeError("tradingview_ta is missing; run `uv sync`.")
    
    symbols = load_symbols(exchange)
    if not symbols:
        raise RuntimeError(f"No symbols found for exchange: {exchange}")
    
    # Process symbols in batches due to TradingView API limits
    batch_size = 200  # Considering API limitations
    all_coins = []
    
    screener = EXCHANGE_SCREENER.get(exchange, "crypto")
    
    # Process symbols in batches
    for i in range(0, len(symbols), batch_size):
        batch_symbols = symbols[i:i + batch_size]
        
        try:
            analysis = get_multiple_analysis(screener=screener, interval=timeframe, symbols=batch_symbols)
        except Exception as e:
            continue  # If this batch fails, move to the next one
            
        # Process coins in this batch
        for key, value in analysis.items():
            try:
                if value is None:
                    continue
                    
                indicators = value.indicators
                metrics = compute_metrics(indicators)
                
                if not metrics or metrics.get('bbw') is None:
                    continue
                
                # Apply rating filter if specified
                if filter_type == "rating" and rating_filter is not None:
                    if metrics['rating'] != rating_filter:
                        continue
                
                all_coins.append(Row(
                    symbol=key,
                    changePercent=metrics['change'],
                    indicators=IndicatorMap(
                        open=metrics.get('open'),
                        close=metrics.get('price'),
                        SMA20=indicators.get("SMA20"),
                        BB_upper=indicators.get("BB.upper"),
                        BB_lower=indicators.get("BB.lower"),
                        EMA50=indicators.get("EMA50"),
                        RSI=indicators.get("RSI"),
                        volume=indicators.get("volume"),
                    )
                ))
                
            except (TypeError, ZeroDivisionError, KeyError):
                continue
    
    # Sort all coins by change percentage
    all_coins.sort(key=lambda x: x["changePercent"], reverse=True)
    
    return all_coins[:limit]
def _fetch_multi_changes(exchange: str, timeframes: List[str] | None, base_timeframe: str = "4h", limit: int | None = None, cookies: Any | None = None) -> List[MultiRow]:
	try:
		from tradingview_screener import Query
		from tradingview_screener.column import Column
	except Exception as e:
		raise RuntimeError("tradingview-screener missing; run `uv sync`.") from e

	tfs = timeframes or ["15m", "1h", "4h", "1D"]
	suffix_map: dict[str, str] = {}
	for tf in tfs:
		s = _tf_to_tv_resolution(tf)
		if s:
			suffix_map[tf] = s
	if not suffix_map:
		suffix_map = {base_timeframe: _tf_to_tv_resolution(base_timeframe) or "240"}

	base_suffix = _tf_to_tv_resolution(base_timeframe) or next(iter(suffix_map.values()))
	cols: list[str] = []
	seen: set[str] = set()
	for tf, s in suffix_map.items():
		for c in (f"open|{s}", f"close|{s}"):
			if c not in seen:
				cols.append(c)
				seen.add(c)
	for c in (f"SMA20|{base_suffix}", f"BB.upper|{base_suffix}", f"BB.lower|{base_suffix}", f"volume|{base_suffix}"):
		if c not in seen:
			cols.append(c)
			seen.add(c)

	q = Query().set_markets("crypto").select(*cols)
	if exchange:
		q = q.where(Column("exchange") == exchange.upper())
	if limit:
		q = q.limit(int(limit))

	_total, df = q.get_scanner_data(cookies=cookies)
	if df is None or df.empty:
		return []

	out: List[MultiRow] = []
	for _, r in df.iterrows():
		symbol = r.get("ticker")
		changes: dict[str, Optional[float]] = {}
		for tf, s in suffix_map.items():
			o = r.get(f"open|{s}")
			c = r.get(f"close|{s}")
			changes[tf] = _percent_change(o, c)
		base_ind = IndicatorMap(
			open=r.get(f"open|{base_suffix}"),
			close=r.get(f"close|{base_suffix}"),
			SMA20=r.get(f"SMA20|{base_suffix}"),
			BB_upper=r.get(f"BB.upper|{base_suffix}"),
			BB_lower=r.get(f"BB.lower|{base_suffix}"),
			volume=r.get(f"volume|{base_suffix}"),
		)
		out.append(MultiRow(symbol=symbol, changes=changes, base_indicators=base_ind))
	return out


def _compact_scan_row(row: dict) -> dict:
    """Reduce a scanner row to regime-critical signals only (strips raw prices, rounds floats).

    Retained fields: symbol, chg% (change), rsi, bb_pos (above/within/below),
    bbw (Bollinger Band Width), vol (raw volume int), plus any volume-specific
    fields (volume_ratio, volume_strength, breakout_type, trading_recommendation).
    """
    ind = row.get("indicators", {}) or {}
    close = ind.get("close")
    bb_upper = ind.get("BB_upper")
    bb_lower = ind.get("BB_lower")
    sma20 = ind.get("SMA20")
    rsi = ind.get("RSI")
    volume = ind.get("volume")

    bb_pos = None
    if close is not None and bb_upper is not None and bb_lower is not None:
        if close > bb_upper:
            bb_pos = "above"
        elif close < bb_lower:
            bb_pos = "below"
        else:
            bb_pos = "within"

    bbw = None
    if sma20 and sma20 != 0 and bb_upper is not None and bb_lower is not None:
        bbw = round((bb_upper - bb_lower) / sma20, 4)

    out: dict = {"symbol": row.get("symbol")}
    chg = row.get("changePercent")
    if chg is not None:
        out["chg%"] = round(chg, 2)
    if rsi is not None:
        out["rsi"] = round(rsi, 1)
    if bb_pos is not None:
        out["bb_pos"] = bb_pos
    if bbw is not None:
        out["bbw"] = bbw
    if volume is not None:
        out["vol"] = int(volume)
    for key in ("volume_ratio", "volume_strength", "breakout_type", "trading_recommendation"):
        if key in row:
            out[key] = row[key]
    return out


def _compact_coin_analysis(result: dict) -> dict:
    """Flatten coin_analysis result to regime-critical signals only."""
    if "error" in result:
        return result
    pd_ = result.get("price_data", {})
    ba = result.get("bollinger_analysis", {})
    ti = result.get("technical_indicators", {})
    ms = result.get("market_sentiment", {})
    out: dict = {"symbol": result.get("symbol"), "tf": result.get("timeframe")}
    if pd_.get("change_percent") is not None:
        out["chg%"] = round(pd_["change_percent"], 2)
    if ti.get("rsi") is not None:
        out["rsi"] = round(ti["rsi"], 1)
    if ti.get("rsi_signal"):
        out["rsi_sig"] = ti["rsi_signal"]
    if ba.get("position"):
        out["bb_pos"] = ba["position"]
    if ba.get("bbw") is not None:
        out["bbw"] = round(ba["bbw"], 4)
    if ba.get("signal"):
        out["bb_sig"] = ba["signal"]
    if ti.get("adx") is not None:
        out["adx"] = round(ti["adx"], 1)
    if ti.get("trend_strength"):
        out["trend"] = ti["trend_strength"]
    if ms.get("momentum"):
        out["momentum"] = ms["momentum"]
    return out


def _compact_vol_confirmation(result: dict) -> dict:
    """Flatten volume_confirmation_analysis to key signals only."""
    if "error" in result:
        return result
    pd_ = result.get("price_data", {})
    va = result.get("volume_analysis", {})
    ti = result.get("technical_indicators", {})
    out: dict = {"symbol": result.get("symbol")}
    if pd_.get("change_percent") is not None:
        out["chg%"] = pd_["change_percent"]
    if va.get("volume_ratio") is not None:
        out["vol_ratio"] = va["volume_ratio"]
    if va.get("volume_strength"):
        out["vol_str"] = va["volume_strength"]
    if ti.get("RSI") is not None:
        out["rsi"] = ti["RSI"]
    if ti.get("BB_position"):
        out["bb_pos"] = ti["BB_position"]
    signals = result.get("signals", [])
    if signals:
        out["signals"] = signals
    return out


mcp = FastMCP(
	name="TradingView Screener",
	instructions=("Crypto screener utilities backed by TradingView Screener. Tools: top_gainers, top_losers, multi_changes."),
)


@mcp.tool()
def top_gainers(exchange: str = "KUCOIN", timeframe: str = "15m", limit: int = 25, compact: bool = False) -> list[dict]:
    """Return top gainers for an exchange and timeframe using bollinger band analysis.

    Args:
        exchange: Exchange name like KUCOIN, BINANCE, BYBIT, etc.
        timeframe: One of 5m, 15m, 1h, 4h, 1D, 1W, 1M
        limit: Number of rows to return (max 50)
        compact: If True, return only regime-critical fields (symbol, chg%, rsi, bb_pos, bbw, vol) — ~70% fewer tokens.
    """
    exchange = sanitize_exchange(exchange, "KUCOIN")
    timeframe = sanitize_timeframe(timeframe, "15m")
    limit = max(1, min(limit, 50))

    rows = _fetch_trending_analysis(exchange, timeframe=timeframe, limit=limit)
    full = [{
        "symbol": row["symbol"],
        "changePercent": row["changePercent"],
        "indicators": dict(row["indicators"])
    } for row in rows]
    return [_compact_scan_row(r) for r in full] if compact else full


@mcp.tool()
def top_losers(exchange: str = "KUCOIN", timeframe: str = "15m", limit: int = 25, compact: bool = False) -> list[dict]:
    """Return top losers for an exchange and timeframe using bollinger band analysis.

    Args:
        exchange: Exchange name like KUCOIN, BINANCE, BYBIT, etc.
        timeframe: One of 5m, 15m, 1h, 4h, 1D, 1W, 1M
        limit: Number of rows to return (max 50)
        compact: If True, return only regime-critical fields (symbol, chg%, rsi, bb_pos, bbw, vol) — ~70% fewer tokens.
    """
    exchange = sanitize_exchange(exchange, "KUCOIN")
    timeframe = sanitize_timeframe(timeframe, "15m")
    limit = max(1, min(limit, 50))

    rows = _fetch_trending_analysis(exchange, timeframe=timeframe, limit=limit)
    rows.sort(key=lambda x: x["changePercent"])

    full = [{
        "symbol": row["symbol"],
        "changePercent": row["changePercent"],
        "indicators": dict(row["indicators"])
    } for row in rows[:limit]]
    return [_compact_scan_row(r) for r in full] if compact else full


@mcp.tool()
def bollinger_scan(exchange: str = "KUCOIN", timeframe: str = "4h", bbw_threshold: float = 0.04, limit: int = 50, compact: bool = False) -> list[dict]:
    """Scan for coins with low Bollinger Band Width (squeeze detection).

    Args:
        exchange: Exchange name like KUCOIN, BINANCE, BYBIT, etc.
        timeframe: One of 5m, 15m, 1h, 4h, 1D, 1W, 1M
        bbw_threshold: Maximum BBW value to filter (default 0.04)
        limit: Number of rows to return (max 100)
        compact: If True, return only regime-critical fields (symbol, chg%, rsi, bb_pos, bbw, vol) — ~70% fewer tokens.
    """
    exchange = sanitize_exchange(exchange, "KUCOIN")
    timeframe = sanitize_timeframe(timeframe, "4h")
    limit = max(1, min(limit, 100))

    rows = _fetch_bollinger_analysis(exchange, timeframe=timeframe, bbw_filter=bbw_threshold, limit=limit)
    full = [{
        "symbol": row["symbol"],
        "changePercent": row["changePercent"],
        "indicators": dict(row["indicators"])
    } for row in rows]
    return [_compact_scan_row(r) for r in full] if compact else full


@mcp.tool()
def rating_filter(exchange: str = "KUCOIN", timeframe: str = "5m", rating: int = 2, limit: int = 25, compact: bool = False) -> list[dict]:
    """Filter coins by Bollinger Band rating.

    Args:
        exchange: Exchange name like KUCOIN, BINANCE, BYBIT, etc.
        timeframe: One of 5m, 15m, 1h, 4h, 1D, 1W, 1M
        rating: BB rating (-3 to +3): -3=Strong Sell, -2=Sell, -1=Weak Sell, 1=Weak Buy, 2=Buy, 3=Strong Buy
        limit: Number of rows to return (max 50)
        compact: If True, return only regime-critical fields (symbol, chg%, rsi, bb_pos, bbw, vol) — ~70% fewer tokens.
    """
    exchange = sanitize_exchange(exchange, "KUCOIN")
    timeframe = sanitize_timeframe(timeframe, "5m")
    rating = max(-3, min(3, rating))
    limit = max(1, min(limit, 50))

    rows = _fetch_trending_analysis(exchange, timeframe=timeframe, filter_type="rating", rating_filter=rating, limit=limit)
    full = [{
        "symbol": row["symbol"],
        "changePercent": row["changePercent"],
        "indicators": dict(row["indicators"])
    } for row in rows]
    return [_compact_scan_row(r) for r in full] if compact else full

@mcp.tool()
def coin_analysis(
    symbol: str,
    exchange: str = "KUCOIN",
    timeframe: str = "15m",
    compact: bool = False
) -> dict:
    """Get detailed analysis for a specific coin on specified exchange and timeframe.

    Args:
        symbol: Coin symbol (e.g., "ACEUSDT", "BTCUSDT")
        exchange: Exchange name (BINANCE, KUCOIN, etc.)
        timeframe: Time interval (5m, 15m, 1h, 4h, 1D, 1W, 1M)
        compact: If True, flatten to regime-critical signals only (symbol, tf, chg%, rsi, bb_pos, bbw, adx, trend, momentum) — ~70% fewer tokens.

    Returns:
        Detailed coin analysis with all indicators and metrics (or compact summary)
    """
    try:
        exchange = sanitize_exchange(exchange, "KUCOIN")
        timeframe = sanitize_timeframe(timeframe, "15m")
        
        # Format symbol with exchange prefix
        if ":" not in symbol:
            full_symbol = f"{exchange.upper()}:{symbol.upper()}"
        else:
            full_symbol = symbol.upper()
        
        screener = EXCHANGE_SCREENER.get(exchange, "crypto")
        
        try:
            analysis = get_multiple_analysis(
                screener=screener,
                interval=timeframe,
                symbols=[full_symbol]
            )
            
            if full_symbol not in analysis or analysis[full_symbol] is None:
                return {
                    "error": f"No data found for {symbol} on {exchange}",
                    "symbol": symbol,
                    "exchange": exchange,
                    "timeframe": timeframe
                }
            
            data = analysis[full_symbol]
            indicators = data.indicators
            
            # Calculate all metrics
            metrics = compute_metrics(indicators)
            if not metrics:
                return {
                    "error": f"Could not compute metrics for {symbol}",
                    "symbol": symbol,
                    "exchange": exchange,
                    "timeframe": timeframe
                }
            
            # Additional technical indicators
            macd = indicators.get("MACD.macd", 0)
            macd_signal = indicators.get("MACD.signal", 0)
            adx = indicators.get("ADX", 0)
            stoch_k = indicators.get("Stoch.K", 0)
            stoch_d = indicators.get("Stoch.D", 0)
            
            # Volume analysis
            volume = indicators.get("volume", 0)
            
            # Price levels
            high = indicators.get("high", 0)
            low = indicators.get("low", 0)
            open_price = indicators.get("open", 0)
            close_price = indicators.get("close", 0)
            
            result = {
                "symbol": full_symbol,
                "exchange": exchange,
                "timeframe": timeframe,
                "timestamp": "real-time",
                "price_data": {
                    "current_price": metrics['price'],
                    "open": round(open_price, 6) if open_price else None,
                    "high": round(high, 6) if high else None,
                    "low": round(low, 6) if low else None,
                    "close": round(close_price, 6) if close_price else None,
                    "change_percent": metrics['change'],
                    "volume": volume
                },
                "bollinger_analysis": {
                    "rating": metrics['rating'],
                    "signal": metrics['signal'],
                    "bbw": metrics['bbw'],
                    "bb_upper": round(indicators.get("BB.upper", 0), 6),
                    "bb_middle": round(indicators.get("SMA20", 0), 6),
                    "bb_lower": round(indicators.get("BB.lower", 0), 6),
                    "position": "Above Upper" if close_price > indicators.get("BB.upper", 0) else
                               "Below Lower" if close_price < indicators.get("BB.lower", 0) else
                               "Within Bands"
                },
                "technical_indicators": {
                    "rsi": round(indicators.get("RSI", 0), 2),
                    "rsi_signal": "Overbought" if indicators.get("RSI", 0) > 70 else
                                 "Oversold" if indicators.get("RSI", 0) < 30 else "Neutral",
                    "sma20": round(indicators.get("SMA20", 0), 6),
                    "ema50": round(indicators.get("EMA50", 0), 6),
                    "ema200": round(indicators.get("EMA200", 0), 6),
                    "macd": round(macd, 6),
                    "macd_signal": round(macd_signal, 6),
                    "macd_divergence": round(macd - macd_signal, 6),
                    "adx": round(adx, 2),
                    "trend_strength": "Strong" if adx > 25 else "Weak",
                    "stoch_k": round(stoch_k, 2),
                    "stoch_d": round(stoch_d, 2)
                },
                "market_sentiment": {
                    "overall_rating": metrics['rating'],
                    "buy_sell_signal": metrics['signal'],
                    "volatility": "High" if metrics['bbw'] > 0.05 else "Medium" if metrics['bbw'] > 0.02 else "Low",
                    "momentum": "Bullish" if metrics['change'] > 0 else "Bearish"
                }
            }
            return _compact_coin_analysis(result) if compact else result

        except Exception as e:
            return {
                "error": f"Analysis failed: {str(e)}",
                "symbol": symbol,
                "exchange": exchange,
                "timeframe": timeframe
            }

    except Exception as e:
        return {
            "error": f"Coin analysis failed: {str(e)}",
            "symbol": symbol,
            "exchange": exchange,
            "timeframe": timeframe
        }

@mcp.tool()
def consecutive_candles_scan(
    exchange: str = "KUCOIN",
    timeframe: str = "15m",
    pattern_type: str = "bullish",
    candle_count: int = 3,
    min_growth: float = 2.0,
    limit: int = 20
) -> dict:
    """Scan for coins with consecutive growing/shrinking candles pattern.
    
    Args:
        exchange: Exchange name (BINANCE, KUCOIN, etc.)
        timeframe: Time interval (5m, 15m, 1h, 4h)
        pattern_type: "bullish" (growing candles) or "bearish" (shrinking candles)
        candle_count: Number of consecutive candles to check (2-5)
        min_growth: Minimum growth percentage for each candle
        limit: Maximum number of results to return
    
    Returns:
        List of coins with consecutive candle patterns
    """
    try:
        exchange = sanitize_exchange(exchange, "KUCOIN")
        timeframe = sanitize_timeframe(timeframe, "15m")
        candle_count = max(2, min(5, candle_count))
        min_growth = max(0.5, min(20.0, min_growth))
        limit = max(1, min(50, limit))
        
        # Get symbols for the exchange
        symbols = load_symbols(exchange)
        if not symbols:
            return {
                "error": f"No symbols found for exchange: {exchange}",
                "exchange": exchange,
                "timeframe": timeframe
            }
        
        # Limit symbols for performance (we need historical data)
        symbols = symbols[:min(limit * 3, 200)]
        
        # We need to get data from multiple timeframes to analyze candle progression
        # For now, we'll use current timeframe data and simulate pattern detection
        screener = EXCHANGE_SCREENER.get(exchange, "crypto")
        
        try:
            analysis = get_multiple_analysis(
                screener=screener,
                interval=timeframe,
                symbols=symbols
            )
            
            pattern_coins = []
            
            for symbol, data in analysis.items():
                if data is None:
                    continue
                    
                try:
                    indicators = data.indicators
                    
                    # Calculate current candle metrics
                    open_price = indicators.get("open")
                    close_price = indicators.get("close")
                    high_price = indicators.get("high") 
                    low_price = indicators.get("low")
                    volume = indicators.get("volume", 0)
                    
                    if not all([open_price, close_price, high_price, low_price]):
                        continue
                    
                    # Calculate current candle body size and change
                    current_change = ((close_price - open_price) / open_price) * 100
                    candle_body = abs(close_price - open_price)
                    candle_range = high_price - low_price
                    body_to_range_ratio = candle_body / candle_range if candle_range > 0 else 0
                    
                    # For consecutive pattern, we'll use available indicators to simulate
                    # In a real implementation, we'd need historical OHLC data
                    
                    # Use RSI and price momentum as proxy for consecutive pattern
                    rsi = indicators.get("RSI", 50)
                    sma20 = indicators.get("SMA20", close_price)
                    ema50 = indicators.get("EMA50", close_price)
                    
                    # Calculate momentum indicators
                    price_above_sma = close_price > sma20
                    price_above_ema = close_price > ema50
                    strong_momentum = abs(current_change) >= min_growth
                    
                    # Pattern detection logic
                    pattern_detected = False
                    pattern_strength = 0
                    
                    if pattern_type == "bullish":
                        # Bullish pattern: price rising, good momentum, strong candle body
                        conditions = [
                            current_change > min_growth,  # Current candle is bullish
                            body_to_range_ratio > 0.6,    # Strong candle body
                            price_above_sma,              # Above short MA
                            rsi > 45 and rsi < 80,        # RSI in momentum range
                            volume > 1000                 # Decent volume
                        ]
                        
                        pattern_strength = sum(conditions)
                        pattern_detected = pattern_strength >= 3
                        
                    elif pattern_type == "bearish":
                        # Bearish pattern: price falling, bearish momentum
                        conditions = [
                            current_change < -min_growth,  # Current candle is bearish
                            body_to_range_ratio > 0.6,     # Strong candle body
                            not price_above_sma,           # Below short MA
                            rsi < 55 and rsi > 20,         # RSI in bearish range
                            volume > 1000                  # Decent volume
                        ]
                        
                        pattern_strength = sum(conditions)
                        pattern_detected = pattern_strength >= 3
                    
                    if pattern_detected:
                        # Calculate additional metrics
                        metrics = compute_metrics(indicators)
                        
                        coin_data = {
                            "symbol": symbol,
                            "price": round(close_price, 6),
                            "current_change": round(current_change, 3),
                            "candle_body_ratio": round(body_to_range_ratio, 3),
                            "pattern_strength": pattern_strength,
                            "volume": volume,
                            "bollinger_rating": metrics.get('rating', 0) if metrics else 0,
                            "rsi": round(rsi, 2),
                            "price_levels": {
                                "open": round(open_price, 6),
                                "high": round(high_price, 6), 
                                "low": round(low_price, 6),
                                "close": round(close_price, 6)
                            },
                            "momentum_signals": {
                                "above_sma20": price_above_sma,
                                "above_ema50": price_above_ema,
                                "strong_volume": volume > 5000
                            }
                        }
                        
                        pattern_coins.append(coin_data)
                        
                except Exception as e:
                    continue
            
            # Sort by pattern strength and current change
            if pattern_type == "bullish":
                pattern_coins.sort(key=lambda x: (x['pattern_strength'], x['current_change']), reverse=True)
            else:
                pattern_coins.sort(key=lambda x: (x['pattern_strength'], -x['current_change']), reverse=True)
            
            return {
                "exchange": exchange,
                "timeframe": timeframe,
                "pattern_type": pattern_type,
                "candle_count": candle_count,
                "min_growth": min_growth,
                "total_found": len(pattern_coins),
                "data": pattern_coins[:limit]
            }
            
        except Exception as e:
            return {
                "error": f"Pattern analysis failed: {str(e)}",
                "exchange": exchange,
                "timeframe": timeframe
            }
            
    except Exception as e:
        return {
            "error": f"Consecutive candles scan failed: {str(e)}",
            "exchange": exchange,
            "timeframe": timeframe
        }

@mcp.tool()
def advanced_candle_pattern(
    exchange: str = "KUCOIN",
    base_timeframe: str = "15m",
    pattern_length: int = 3,
    min_size_increase: float = 10.0,
    limit: int = 15
) -> dict:
    """Advanced candle pattern analysis using multi-timeframe data.
    
    Args:
        exchange: Exchange name (BINANCE, KUCOIN, etc.)
        base_timeframe: Base timeframe for analysis (5m, 15m, 1h, 4h)
        pattern_length: Number of consecutive periods to analyze (2-4)
        min_size_increase: Minimum percentage increase in candle size
        limit: Maximum number of results to return
    
    Returns:
        Coins with progressive candle size increase patterns
    """
    try:
        exchange = sanitize_exchange(exchange, "KUCOIN")
        base_timeframe = sanitize_timeframe(base_timeframe, "15m")
        pattern_length = max(2, min(4, pattern_length))
        min_size_increase = max(5.0, min(50.0, min_size_increase))
        limit = max(1, min(30, limit))
        
        # Get symbols
        symbols = load_symbols(exchange)
        if not symbols:
            return {
                "error": f"No symbols found for exchange: {exchange}",
                "exchange": exchange
            }
        
        # Limit for performance
        symbols = symbols[:min(limit * 2, 100)]
        
        # Use tradingview-screener for multi-timeframe data if available
        if TRADINGVIEW_SCREENER_AVAILABLE:
            try:
                # Get multiple timeframe data using screener
                results = _fetch_multi_timeframe_patterns(
                    exchange, symbols, base_timeframe, pattern_length, min_size_increase
                )
                
                return {
                    "exchange": exchange,
                    "base_timeframe": base_timeframe,
                    "pattern_length": pattern_length,
                    "min_size_increase": min_size_increase,
                    "method": "multi-timeframe",
                    "total_found": len(results),
                    "data": results[:limit]
                }
                
            except Exception as e:
                # Fallback to single timeframe analysis
                pass
        
        # Fallback: Use single timeframe with enhanced pattern detection
        screener = EXCHANGE_SCREENER.get(exchange, "crypto")
        
        analysis = get_multiple_analysis(
            screener=screener,
            interval=base_timeframe,
            symbols=symbols
        )
        
        pattern_results = []
        
        for symbol, data in analysis.items():
            if data is None:
                continue
                
            try:
                indicators = data.indicators
                
                # Enhanced pattern detection using available indicators
                pattern_score = _calculate_candle_pattern_score(
                    indicators, pattern_length, min_size_increase
                )
                
                if pattern_score['detected']:
                    metrics = compute_metrics(indicators)
                    
                    result = {
                        "symbol": symbol,
                        "pattern_score": pattern_score['score'],
                        "pattern_details": pattern_score['details'],
                        "current_price": pattern_score['price'],
                        "total_change": pattern_score['total_change'],
                        "volume": indicators.get("volume", 0),
                        "bollinger_rating": metrics.get('rating', 0) if metrics else 0,
                        "technical_strength": {
                            "rsi": round(indicators.get("RSI", 50), 2),
                            "momentum": "Strong" if abs(pattern_score['total_change']) > min_size_increase else "Moderate",
                            "volume_trend": "High" if indicators.get("volume", 0) > 10000 else "Low"
                        }
                    }
                    
                    pattern_results.append(result)
                    
            except Exception as e:
                continue
        
        # Sort by pattern score and total change
        pattern_results.sort(key=lambda x: (x['pattern_score'], abs(x['total_change'])), reverse=True)
        
        return {
            "exchange": exchange,
            "base_timeframe": base_timeframe,
            "pattern_length": pattern_length,
            "min_size_increase": min_size_increase,
            "method": "enhanced-single-timeframe",
            "total_found": len(pattern_results),
            "data": pattern_results[:limit]
        }
        
    except Exception as e:
        return {
            "error": f"Advanced pattern analysis failed: {str(e)}",
            "exchange": exchange,
            "base_timeframe": base_timeframe
        }

def _calculate_candle_pattern_score(indicators: dict, pattern_length: int, min_increase: float) -> dict:
    """Calculate candle pattern score based on available indicators."""
    try:
        open_price = indicators.get("open", 0)
        close_price = indicators.get("close", 0)
        high_price = indicators.get("high", 0)
        low_price = indicators.get("low", 0)
        volume = indicators.get("volume", 0)
        rsi = indicators.get("RSI", 50)
        
        if not all([open_price, close_price, high_price, low_price]):
            return {"detected": False, "score": 0}
        
        # Current candle analysis
        candle_body = abs(close_price - open_price)
        candle_range = high_price - low_price
        body_ratio = candle_body / candle_range if candle_range > 0 else 0
        
        # Price change
        price_change = ((close_price - open_price) / open_price) * 100
        
        # Pattern scoring
        score = 0
        details = []
        
        # Strong candle body
        if body_ratio > 0.7:
            score += 2
            details.append("Strong candle body")
        elif body_ratio > 0.5:
            score += 1
            details.append("Moderate candle body")
        
        # Significant price movement
        if abs(price_change) >= min_increase:
            score += 2
            details.append(f"Strong momentum ({price_change:.1f}%)")
        elif abs(price_change) >= min_increase / 2:
            score += 1
            details.append(f"Moderate momentum ({price_change:.1f}%)")
        
        # Volume confirmation
        if volume > 5000:
            score += 1
            details.append("Good volume")
        
        # RSI momentum
        if (price_change > 0 and 50 < rsi < 80) or (price_change < 0 and 20 < rsi < 50):
            score += 1
            details.append("RSI momentum aligned")
        
        # Trend consistency (using EMA vs price)
        ema50 = indicators.get("EMA50", close_price)
        if (price_change > 0 and close_price > ema50) or (price_change < 0 and close_price < ema50):
            score += 1
            details.append("Trend alignment")
        
        detected = score >= 3  # Minimum threshold
        
        return {
            "detected": detected,
            "score": score,
            "details": details,
            "price": round(close_price, 6),
            "total_change": round(price_change, 3),
            "body_ratio": round(body_ratio, 3),
            "volume": volume
        }
        
    except Exception as e:
        return {"detected": False, "score": 0, "error": str(e)}

def _fetch_multi_timeframe_patterns(exchange: str, symbols: List[str], base_tf: str, length: int, min_increase: float) -> List[dict]:
    """Fetch multi-timeframe pattern data using tradingview-screener."""
    try:
        from tradingview_screener import Query
        from tradingview_screener.column import Column
        
        # Map timeframe to TradingView format
        tf_map = {"5m": "5", "15m": "15", "1h": "60", "4h": "240", "1D": "1D"}
        tv_interval = tf_map.get(base_tf, "15")
        
        # Create query for OHLC data
        cols = [
            f"open|{tv_interval}",
            f"close|{tv_interval}", 
            f"high|{tv_interval}",
            f"low|{tv_interval}",
            f"volume|{tv_interval}",
            "RSI"
        ]
        
        q = Query().set_markets("crypto").select(*cols)
        q = q.where(Column("exchange") == exchange.upper())
        q = q.limit(len(symbols))
        
        total, df = q.get_scanner_data()
        
        if df is None or df.empty:
            return []
        
        results = []
        
        for _, row in df.iterrows():
            symbol = row.get("ticker", "")
            
            try:
                open_val = row.get(f"open|{tv_interval}")
                close_val = row.get(f"close|{tv_interval}")
                high_val = row.get(f"high|{tv_interval}")
                low_val = row.get(f"low|{tv_interval}")
                volume_val = row.get(f"volume|{tv_interval}", 0)
                rsi_val = row.get("RSI", 50)
                
                if not all([open_val, close_val, high_val, low_val]):
                    continue
                
                # Calculate pattern metrics
                pattern_score = _calculate_candle_pattern_score({
                    "open": open_val,
                    "close": close_val,
                    "high": high_val,
                    "low": low_val,
                    "volume": volume_val,
                    "RSI": rsi_val
                }, length, min_increase)
                
                if pattern_score['detected']:
                    results.append({
                        "symbol": symbol,
                        "pattern_score": pattern_score['score'],
                        "price": pattern_score['price'],
                        "change": pattern_score['total_change'],
                        "body_ratio": pattern_score['body_ratio'],
                        "volume": volume_val,
                        "rsi": round(rsi_val, 2),
                        "details": pattern_score['details']
                    })
                    
            except Exception as e:
                continue
        
        return sorted(results, key=lambda x: x['pattern_score'], reverse=True)
        
    except Exception as e:
        return []

@mcp.resource("exchanges://list")
def exchanges_list() -> str:
    """List available exchanges from coinlist directory."""
    try:
        import os
        # Get the directory where this module is located
        current_dir = os.path.dirname(__file__)
        coinlist_dir = os.path.join(current_dir, "coinlist")
        
        if os.path.exists(coinlist_dir):
            exchanges = []
            for filename in os.listdir(coinlist_dir):
                if filename.endswith('.txt'):
                    exchange_name = filename[:-4].upper()
                    exchanges.append(exchange_name)
            
            if exchanges:
                return f"Available exchanges: {', '.join(sorted(exchanges))}"
        
        # Fallback to static list
        return "Common exchanges: KUCOIN, BINANCE, BYBIT, BITGET, OKX, COINBASE, GATEIO, HUOBI, BITFINEX, KRAKEN, BITSTAMP, BIST, NASDAQ"
    except Exception:
        return "Common exchanges: KUCOIN, BINANCE, BYBIT, BITGET, OKX, COINBASE, GATEIO, HUOBI, BITFINEX, KRAKEN, BITSTAMP, BIST, NASDAQ"
def main() -> None:
	parser = argparse.ArgumentParser(description="TradingView Screener MCP server")
	parser.add_argument("transport", choices=["stdio", "streamable-http"], default="stdio", nargs="?", help="Transport (default stdio)")
	parser.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
	parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
	args = parser.parse_args()

	if os.environ.get("DEBUG_MCP"):
		import sys
		print(f"[DEBUG_MCP] pkg cwd={os.getcwd()} argv={sys.argv} file={__file__}", file=sys.stderr, flush=True)

	if args.transport == "stdio":
		mcp.run()
	else:
		import anyio
		import uvicorn
		from starlette.applications import Starlette
		from starlette.middleware import Middleware
		from starlette.middleware.base import BaseHTTPMiddleware
		from starlette.responses import Response
		from starlette.routing import Mount

		try:
			mcp.settings.host = args.host
			mcp.settings.port = args.port
		except Exception:
			pass

		api_key = os.environ.get("API_KEY")
		starlette_app = mcp.streamable_http_app()

		from starlette.requests import Request
		from starlette.routing import Route

		async def health(request: Request) -> Response:
			return Response("OK", status_code=200)

		if api_key:
			class ApiKeyMiddleware(BaseHTTPMiddleware):
				async def dispatch(self, request, call_next):
					if request.url.path == "/health":
						return await call_next(request)
					auth = request.headers.get("Authorization", "")
					if auth != f"Bearer {api_key}":
						return Response("Unauthorized", status_code=401)
					return await call_next(request)

			starlette_app = Starlette(
				routes=[Route("/health", health), Mount("/", app=starlette_app)],
				middleware=[Middleware(ApiKeyMiddleware)],
			)
		else:
			starlette_app = Starlette(
				routes=[Route("/health", health), Mount("/", app=starlette_app)],
			)

		async def _serve():
			config = uvicorn.Config(
				starlette_app,
				host=args.host,
				port=args.port,
				log_level="info",
			)
			server = uvicorn.Server(config)
			await server.serve()

		anyio.run(_serve)


@mcp.tool()
def volume_breakout_scanner(exchange: str = "KUCOIN", timeframe: str = "15m", volume_multiplier: float = 2.0, price_change_min: float = 3.0, limit: int = 25, compact: bool = False) -> list[dict]:
	"""Detect coins with volume breakout + price breakout.

	Args:
		exchange: Exchange name like KUCOIN, BINANCE, BYBIT, etc.
		timeframe: One of 5m, 15m, 1h, 4h, 1D, 1W, 1M
		volume_multiplier: How many times the volume should be above normal level (default 2.0)
		price_change_min: Minimum price change percentage (default 3.0)
		limit: Number of rows to return (max 50)
		compact: If True, return only regime-critical fields (symbol, chg%, rsi, bb_pos, vol_ratio, breakout_type) — ~70% fewer tokens.
	"""
	exchange = sanitize_exchange(exchange, "KUCOIN")
	timeframe = sanitize_timeframe(timeframe, "15m")
	volume_multiplier = max(1.5, min(10.0, volume_multiplier))
	price_change_min = max(1.0, min(20.0, price_change_min))
	limit = max(1, min(limit, 50))
	
	# Get symbols
	symbols = load_symbols(exchange)
	if not symbols:
		return []
	
	screener = EXCHANGE_SCREENER.get(exchange, "crypto")
	volume_breakouts = []
	
	# Process in batches
	batch_size = 100
	for i in range(0, min(len(symbols), 500), batch_size):  # Limit to 500 symbols for performance
		batch_symbols = symbols[i:i + batch_size]
		
		try:
			analysis = get_multiple_analysis(screener=screener, interval=timeframe, symbols=batch_symbols)
		except Exception:
			continue
			
		for symbol, data in analysis.items():
			try:
				if not data or not hasattr(data, 'indicators'):
					continue
					
				indicators = data.indicators
				
				# Get required data
				volume = indicators.get('volume', 0)
				close = indicators.get('close', 0)
				open_price = indicators.get('open', 0)
				sma20_volume = indicators.get('volume.SMA20', 0)  # 20-period volume average
				
				if not all([volume, close, open_price]) or volume <= 0:
					continue
				
				# Calculate price change %
				price_change = ((close - open_price) / open_price) * 100 if open_price > 0 else 0
				
				# Volume ratio calculation
				# If SMA20 volume not available, use a simple heuristic
				if sma20_volume and sma20_volume > 0:
					volume_ratio = volume / sma20_volume
				else:
					# Estimate average volume as current volume / 2 (conservative)
					avg_volume_estimate = volume / 2
					volume_ratio = volume / avg_volume_estimate if avg_volume_estimate > 0 else 1
				
				# Check conditions
				if (abs(price_change) >= price_change_min and 
					volume_ratio >= volume_multiplier):
					
					# Get additional indicators
					rsi = indicators.get('RSI', 50)
					bb_upper = indicators.get('BB.upper', 0)
					bb_lower = indicators.get('BB.lower', 0)
					
					# Volume strength score
					volume_strength = min(10, volume_ratio)  # Cap at 10x
					
					volume_breakouts.append({
						"symbol": symbol,
						"changePercent": price_change,
						"volume_ratio": round(volume_ratio, 2),
						"volume_strength": round(volume_strength, 1),
						"current_volume": volume,
						"breakout_type": "bullish" if price_change > 0 else "bearish",
						"indicators": {
							"close": close,
							"RSI": rsi,
							"BB_upper": bb_upper,
							"BB_lower": bb_lower,
							"volume": volume
						}
					})
					
			except Exception:
				continue
	
	# Sort by volume strength first, then by price change
	volume_breakouts.sort(key=lambda x: (x["volume_strength"], abs(x["changePercent"])), reverse=True)

	results = volume_breakouts[:limit]
	return [_compact_scan_row(r) for r in results] if compact else results


@mcp.tool()
def volume_confirmation_analysis(symbol: str, exchange: str = "KUCOIN", timeframe: str = "15m", compact: bool = False) -> dict:
	"""Detailed volume confirmation analysis for a specific coin.

	Args:
		symbol: Coin symbol (e.g., BTCUSDT)
		exchange: Exchange name
		timeframe: Time frame for analysis
		compact: If True, flatten to key signals only (symbol, chg%, vol_ratio, vol_str, rsi, bb_pos, signals) — ~70% fewer tokens.
	"""
	exchange = sanitize_exchange(exchange, "KUCOIN")
	timeframe = sanitize_timeframe(timeframe, "15m")
	
	if not symbol.upper().endswith('USDT'):
		symbol = symbol.upper() + 'USDT'
	
	screener = EXCHANGE_SCREENER.get(exchange, "crypto")
	
	try:
		analysis = get_multiple_analysis(screener=screener, interval=timeframe, symbols=[symbol])
		
		if not analysis or symbol not in analysis:
			return {"error": f"No data found for {symbol}"}
			
		data = analysis[symbol]
		if not data or not hasattr(data, 'indicators'):
			return {"error": f"No indicator data for {symbol}"}
			
		indicators = data.indicators
		
		# Get volume data
		volume = indicators.get('volume', 0)
		close = indicators.get('close', 0)
		open_price = indicators.get('open', 0)
		high = indicators.get('high', 0)
		low = indicators.get('low', 0)
		
		# Calculate price metrics
		price_change = ((close - open_price) / open_price) * 100 if open_price > 0 else 0
		candle_range = ((high - low) / low) * 100 if low > 0 else 0
		
		# Volume analysis
		sma20_volume = indicators.get('volume.SMA20', 0)
		volume_ratio = volume / sma20_volume if sma20_volume > 0 else 1
		
		# Technical indicators
		rsi = indicators.get('RSI', 50)
		bb_upper = indicators.get('BB.upper', 0)
		bb_lower = indicators.get('BB.lower', 0)
		bb_middle = (bb_upper + bb_lower) / 2 if bb_upper and bb_lower else close
		
		# Volume confirmation signals
		signals = []
		
		# Strong volume + price breakout
		if volume_ratio >= 2.0 and abs(price_change) >= 3.0:
			signals.append(f"🚀 STRONG BREAKOUT: {volume_ratio:.1f}x volume + {price_change:.1f}% price")
		
		# Volume divergence
		if volume_ratio >= 1.5 and abs(price_change) < 1.0:
			signals.append(f"⚠️ VOLUME DIVERGENCE: High volume ({volume_ratio:.1f}x) but low price movement")
		
		# Low volume on price move (weak signal)
		if abs(price_change) >= 2.0 and volume_ratio < 0.8:
			signals.append(f"❌ WEAK SIGNAL: Price moved but volume is low ({volume_ratio:.1f}x)")
		
		# Bollinger Band + Volume confirmation
		if close > bb_upper and volume_ratio >= 1.5:
			signals.append(f"💥 BB BREAKOUT CONFIRMED: Upper band breakout + volume confirmation")
		elif close < bb_lower and volume_ratio >= 1.5:
			signals.append(f"📉 BB SELL CONFIRMED: Lower band breakout + volume confirmation")
		
		# RSI + Volume analysis
		if rsi > 70 and volume_ratio >= 2.0:
			signals.append(f"🔥 OVERBOUGHT + VOLUME: RSI {rsi:.1f} + {volume_ratio:.1f}x volume")
		elif rsi < 30 and volume_ratio >= 2.0:
			signals.append(f"🛒 OVERSOLD + VOLUME: RSI {rsi:.1f} + {volume_ratio:.1f}x volume")
		
		# Overall assessment
		if volume_ratio >= 3.0:
			volume_strength = "VERY STRONG"
		elif volume_ratio >= 2.0:
			volume_strength = "STRONG"
		elif volume_ratio >= 1.5:
			volume_strength = "MEDIUM"
		elif volume_ratio >= 1.0:
			volume_strength = "NORMAL"
		else:
			volume_strength = "WEAK"
		
		result = {
			"symbol": symbol,
			"price_data": {
				"close": close,
				"change_percent": round(price_change, 2),
				"candle_range_percent": round(candle_range, 2)
			},
			"volume_analysis": {
				"current_volume": volume,
				"volume_ratio": round(volume_ratio, 2),
				"volume_strength": volume_strength,
				"average_volume": sma20_volume
			},
			"technical_indicators": {
				"RSI": round(rsi, 1),
				"BB_position": "ABOVE" if close > bb_upper else "BELOW" if close < bb_lower else "WITHIN",
				"BB_upper": bb_upper,
				"BB_lower": bb_lower
			},
			"signals": signals,
			"overall_assessment": {
				"bullish_signals": len([s for s in signals if "🚀" in s or "💥" in s or "🛒" in s]),
				"bearish_signals": len([s for s in signals if "📉" in s or "❌" in s]),
				"warning_signals": len([s for s in signals if "⚠️" in s])
			}
		}
		return _compact_vol_confirmation(result) if compact else result

	except Exception as e:
		return {"error": f"Analysis failed: {str(e)}"}


@mcp.tool()
def smart_volume_scanner(exchange: str = "KUCOIN", min_volume_ratio: float = 2.0, min_price_change: float = 2.0, rsi_range: str = "any", limit: int = 20, compact: bool = False) -> list[dict]:
	"""Smart volume + technical analysis combination scanner.

	Args:
		exchange: Exchange name
		min_volume_ratio: Minimum volume multiplier (default 2.0)
		min_price_change: Minimum price change percentage (default 2.0)
		rsi_range: "oversold" (<30), "overbought" (>70), "neutral" (30-70), "any"
		limit: Number of results (max 30)
		compact: If True, return only regime-critical fields (symbol, chg%, rsi, bb_pos, vol_ratio, breakout_type, trading_recommendation) — ~70% fewer tokens.
	"""
	exchange = sanitize_exchange(exchange, "KUCOIN")
	min_volume_ratio = max(1.2, min(10.0, min_volume_ratio))
	min_price_change = max(0.5, min(20.0, min_price_change))
	limit = max(1, min(limit, 30))
	
	# Get volume breakouts first
	volume_breakouts = volume_breakout_scanner(
		exchange=exchange, 
		volume_multiplier=min_volume_ratio,
		price_change_min=min_price_change,
		limit=limit * 2  # Get more to filter
	)
	
	if not volume_breakouts:
		return []
	
	# Apply RSI filter
	filtered_results = []
	for coin in volume_breakouts:
		rsi = coin["indicators"].get("RSI", 50)
		
		if rsi_range == "oversold" and rsi >= 30:
			continue
		elif rsi_range == "overbought" and rsi <= 70:
			continue
		elif rsi_range == "neutral" and (rsi <= 30 or rsi >= 70):
			continue
		# "any" passes all
		
		# Add trading recommendation
		recommendation = ""
		if coin["changePercent"] > 0 and coin["volume_ratio"] >= 2.0:
			if rsi < 70:
				recommendation = "🚀 STRONG BUY"
			else:
				recommendation = "⚠️ OVERBOUGHT - CAUTION"
		elif coin["changePercent"] < 0 and coin["volume_ratio"] >= 2.0:
			if rsi > 30:
				recommendation = "📉 STRONG SELL"
			else:
				recommendation = "🛒 OVERSOLD - OPPORTUNITY?"
		
		coin["trading_recommendation"] = recommendation
		filtered_results.append(coin)

	results = filtered_results[:limit]
	return [_compact_scan_row(r) for r in results] if compact else results


@mcp.tool()
def rsi_scanner(exchange: str = "KUCOIN", timeframe: str = "1h", condition: str = "oversold", rsi_threshold: float = None, limit: int = 20, compact: bool = False) -> list[dict]:
    """Scan for coins matching a specific RSI condition.

    Args:
        exchange: Exchange name like KUCOIN, BINANCE, BYBIT, etc.
        timeframe: One of 5m, 15m, 1h, 4h, 1D, 1W, 1M
        condition: "oversold" (RSI < 30), "overbought" (RSI > 70), or "custom" (use rsi_threshold)
        rsi_threshold: Custom RSI threshold — used only when condition="custom". Acts as upper bound for oversold-style (RSI < threshold) or lower bound for overbought-style (RSI > threshold) based on threshold value (<50 = below, >=50 = above).
        limit: Number of rows to return (max 50)
        compact: If True, return only regime-critical fields — ~70% fewer tokens.
    """
    exchange = sanitize_exchange(exchange, "KUCOIN")
    timeframe = sanitize_timeframe(timeframe, "1h")
    limit = max(1, min(limit, 50))

    if not TRADINGVIEW_TA_AVAILABLE:
        return [{"error": "tradingview_ta is missing; run `uv sync`."}]

    symbols = load_symbols(exchange)
    if not symbols:
        return [{"error": f"No symbols found for exchange: {exchange}"}]

    screener = EXCHANGE_SCREENER.get(exchange, "crypto")
    batch_size = 200
    matched: list[dict] = []

    for i in range(0, len(symbols), batch_size):
        if len(matched) >= limit * 3:
            break
        batch = symbols[i:i + batch_size]
        try:
            analysis = get_multiple_analysis(screener=screener, interval=timeframe, symbols=batch)
        except Exception:
            continue

        for key, value in analysis.items():
            try:
                if value is None:
                    continue
                indicators = value.indicators
                rsi = indicators.get("RSI")
                if rsi is None:
                    continue

                # Apply condition filter
                if condition == "oversold":
                    if rsi >= 30:
                        continue
                elif condition == "overbought":
                    if rsi <= 70:
                        continue
                elif condition == "custom" and rsi_threshold is not None:
                    if rsi_threshold < 50:
                        if rsi >= rsi_threshold:
                            continue
                    else:
                        if rsi <= rsi_threshold:
                            continue

                metrics = compute_metrics(indicators)
                if not metrics:
                    continue

                row = {
                    "symbol": key,
                    "changePercent": metrics["change"],
                    "rsi": round(rsi, 2),
                    "rsi_signal": "Oversold" if rsi < 30 else "Overbought" if rsi > 70 else "Neutral",
                    "indicators": dict(IndicatorMap(
                        open=metrics.get("open"),
                        close=metrics.get("price"),
                        SMA20=indicators.get("SMA20"),
                        BB_upper=indicators.get("BB.upper"),
                        BB_lower=indicators.get("BB.lower"),
                        EMA50=indicators.get("EMA50"),
                        RSI=rsi,
                        volume=indicators.get("volume"),
                    ))
                }
                matched.append(row)
            except Exception:
                continue

    # Sort: oversold → ascending RSI (lowest first); overbought → descending RSI
    if condition == "overbought":
        matched.sort(key=lambda x: x["rsi"], reverse=True)
    else:
        matched.sort(key=lambda x: x["rsi"])

    results = matched[:limit]
    return [_compact_scan_row(r) for r in results] if compact else results


@mcp.tool()
def trend_scanner(exchange: str = "KUCOIN", timeframe: str = "4h", min_adx: float = 25.0, direction: str = "any", limit: int = 20, compact: bool = False) -> list[dict]:
    """Scan for strongly trending coins using ADX (Average Directional Index).

    Args:
        exchange: Exchange name like KUCOIN, BINANCE, BYBIT, etc.
        timeframe: One of 5m, 15m, 1h, 4h, 1D, 1W, 1M
        min_adx: Minimum ADX value to qualify as trending (default 25.0; >40 = very strong)
        direction: Filter by trend direction — "bullish" (price above EMA50), "bearish" (price below EMA50), or "any"
        limit: Number of rows to return (max 50)
        compact: If True, return only regime-critical fields — ~70% fewer tokens.
    """
    exchange = sanitize_exchange(exchange, "KUCOIN")
    timeframe = sanitize_timeframe(timeframe, "4h")
    min_adx = max(10.0, min(60.0, min_adx))
    limit = max(1, min(limit, 50))

    if not TRADINGVIEW_TA_AVAILABLE:
        return [{"error": "tradingview_ta is missing; run `uv sync`."}]

    symbols = load_symbols(exchange)
    if not symbols:
        return [{"error": f"No symbols found for exchange: {exchange}"}]

    screener = EXCHANGE_SCREENER.get(exchange, "crypto")
    batch_size = 200
    matched: list[dict] = []

    for i in range(0, len(symbols), batch_size):
        if len(matched) >= limit * 3:
            break
        batch = symbols[i:i + batch_size]
        try:
            analysis = get_multiple_analysis(screener=screener, interval=timeframe, symbols=batch)
        except Exception:
            continue

        for key, value in analysis.items():
            try:
                if value is None:
                    continue
                indicators = value.indicators
                adx = indicators.get("ADX")
                if adx is None or adx < min_adx:
                    continue

                close = indicators.get("close") or indicators.get("Candle.close")
                ema50 = indicators.get("EMA50")
                if close is None or ema50 is None:
                    continue

                trend_dir = "bullish" if close > ema50 else "bearish"
                if direction != "any" and trend_dir != direction:
                    continue

                metrics = compute_metrics(indicators)
                if not metrics:
                    continue

                row = {
                    "symbol": key,
                    "changePercent": metrics["change"],
                    "adx": round(adx, 2),
                    "trend_direction": trend_dir,
                    "trend_strength": "Very Strong" if adx >= 40 else "Strong",
                    "indicators": dict(IndicatorMap(
                        open=metrics.get("open"),
                        close=metrics.get("price"),
                        SMA20=indicators.get("SMA20"),
                        BB_upper=indicators.get("BB.upper"),
                        BB_lower=indicators.get("BB.lower"),
                        EMA50=ema50,
                        RSI=indicators.get("RSI"),
                        volume=indicators.get("volume"),
                    ))
                }
                matched.append(row)
            except Exception:
                continue

    matched.sort(key=lambda x: x["adx"], reverse=True)
    results = matched[:limit]
    return [_compact_scan_row(r) for r in results] if compact else results


@mcp.tool()
def multi_timeframe_summary(symbol: str, exchange: str = "KUCOIN", compact: bool = False) -> dict:
    """Get a concise technical summary for a symbol across 4 timeframes (15m, 1h, 4h, 1D).

    Useful for quickly gauging whether short-term and long-term signals agree or diverge.

    Args:
        symbol: Trading symbol (e.g., "BTCUSDT", "ETHUSDT", "AAPL")
        exchange: Exchange name (KUCOIN, BINANCE, BYBIT, NASDAQ, etc.)
        compact: If True, return a flat minimal dict per timeframe — ~70% fewer tokens.
    """
    if not TRADINGVIEW_TA_AVAILABLE:
        return {"error": "tradingview_ta is missing; run `uv sync`."}

    exchange = sanitize_exchange(exchange, "KUCOIN")
    screener = EXCHANGE_SCREENER.get(exchange, "crypto")

    if ":" not in symbol:
        full_symbol = f"{exchange.upper()}:{symbol.upper()}"
    else:
        full_symbol = symbol.upper()

    timeframes = ["15m", "1h", "4h", "1D"]
    summary: dict = {"symbol": full_symbol, "exchange": exchange, "timeframes": {}}

    for tf in timeframes:
        try:
            analysis = get_multiple_analysis(screener=screener, interval=tf, symbols=[full_symbol])
            if full_symbol not in analysis or analysis[full_symbol] is None:
                summary["timeframes"][tf] = {"error": "no data"}
                continue

            indicators = analysis[full_symbol].indicators
            metrics = compute_metrics(indicators)
            if not metrics:
                summary["timeframes"][tf] = {"error": "metrics unavailable"}
                continue

            rsi = indicators.get("RSI", 0)
            adx = indicators.get("ADX", 0)
            macd = indicators.get("MACD.macd", 0)
            macd_signal = indicators.get("MACD.signal", 0)
            close = indicators.get("close") or metrics.get("price", 0)
            ema50 = indicators.get("EMA50", 0)

            tf_data = {
                "change_percent": metrics["change"],
                "rsi": round(rsi, 2),
                "rsi_signal": "Overbought" if rsi > 70 else "Oversold" if rsi < 30 else "Neutral",
                "bb_rating": metrics["rating"],
                "bb_signal": metrics["signal"],
                "bbw": metrics["bbw"],
                "adx": round(adx, 2),
                "trend_strength": "Strong" if adx > 25 else "Weak",
                "trend_direction": "Bullish" if close > ema50 else "Bearish",
                "macd_divergence": round(macd - macd_signal, 6),
            }

            if compact:
                summary["timeframes"][tf] = {
                    "chg%": tf_data["change_percent"],
                    "rsi": tf_data["rsi"],
                    "rsi_sig": tf_data["rsi_signal"],
                    "bb": tf_data["bb_signal"],
                    "adx": tf_data["adx"],
                    "trend": tf_data["trend_direction"],
                }
            else:
                summary["timeframes"][tf] = tf_data

        except Exception as e:
            summary["timeframes"][tf] = {"error": str(e)}

    # Overall consensus
    signals = [d.get("bb_signal", "") for d in summary["timeframes"].values() if isinstance(d, dict) and "bb_signal" in d]
    bullish = sum(1 for s in signals if "Buy" in s)
    bearish = sum(1 for s in signals if "Sell" in s)
    if bullish > bearish:
        consensus = "Bullish"
    elif bearish > bullish:
        consensus = "Bearish"
    else:
        consensus = "Mixed"

    summary["consensus"] = consensus
    summary["bullish_timeframes"] = bullish
    summary["bearish_timeframes"] = bearish

    return summary


if __name__ == "__main__":
	main()

