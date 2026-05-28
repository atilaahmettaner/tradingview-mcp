"""
Scanner Service — volume breakout and technical pattern scanning logic.

All functions take validated parameters and return plain dicts / lists.
They have zero dependency on the MCP layer and are independently testable.

Batched scanners raise :class:`BatchExecutionError` when 100% of upstream
batches fail, so the tool wrapper at the MCP boundary can convert that into a
structured error envelope. Returning ``[]`` on total failure (the historical
behavior) hid rate-limit cliffs as "no results today".
"""
from __future__ import annotations

import sys
import time as _time
from typing import List, Optional

from tradingview_mcp.core.errors import BatchExecutionError
from tradingview_mcp.core.services.coinlist import load_symbols
from tradingview_mcp.core.services.indicators import compute_metrics
from tradingview_mcp.core.services.screener_service import (
    _batch_budget_s,
    _batch_max_consecutive_fails,
)
from tradingview_mcp.core.utils.validators import EXCHANGE_SCREENER, is_stock_exchange

try:
    # Patched: route through resilience layer (retry + 60s TTL cache).
    import tradingview_ta  # noqa: F401  presence check
    from tradingview_mcp.core.services.screener_provider import (
        resilient_get_multiple_analysis as get_multiple_analysis,
    )
    _TA_AVAILABLE = True
except ImportError:
    _TA_AVAILABLE = False


# ── Volume breakout ────────────────────────────────────────────────────────────

def volume_breakout_scan(
    exchange: str,
    timeframe: str = "15m",
    volume_multiplier: float = 2.0,
    price_change_min: float = 3.0,
    limit: int = 25,
) -> List[dict]:
    """
    Detect coins with simultaneous volume and price breakouts.

    Args:
        exchange:          Exchange identifier.
        timeframe:         TradingView interval string.
        volume_multiplier: Minimum current-volume / avg-volume ratio.
        price_change_min:  Minimum abs(price change %) required.
        limit:             Maximum results to return.

    Returns:
        List of dicts sorted by volume_strength desc, then abs(changePercent) desc.
    """
    symbols = load_symbols(exchange)
    if not symbols:
        return []

    screener = EXCHANGE_SCREENER.get(exchange, "crypto")
    volume_breakouts: List[dict] = []
    batch_size = 100

    batches_attempted = 0
    batches_failed = 0
    consecutive_failures = 0
    first_error: Optional[str] = None

    max_consec = _batch_max_consecutive_fails()
    budget_s = _batch_budget_s()
    started_at = _time.time()

    capped_symbols = min(len(symbols), 500)
    total_batches = (capped_symbols + batch_size - 1) // batch_size

    for i in range(0, capped_symbols, batch_size):
        # Bail fast if we've spent the wall-clock budget on retries.
        if (_time.time() - started_at) >= budget_s:
            try:
                print(
                    f"[tradingview_mcp] volume_breakout_scan aborted: "
                    f"wall-clock budget ({budget_s:.0f}s) exhausted at batch "
                    f"{batches_attempted}/{total_batches}",
                    file=sys.stderr,
                )
            except Exception:
                pass
            break

        batch = symbols[i : i + batch_size]
        batches_attempted += 1
        try:
            analysis = get_multiple_analysis(screener=screener, interval=timeframe, symbols=batch)
            consecutive_failures = 0
        except Exception as exc:
            batches_failed += 1
            consecutive_failures += 1
            if first_error is None:
                first_error = repr(exc)
            try:
                print(
                    f"[tradingview_mcp] volume_breakout_scan batch "
                    f"{i // batch_size + 1} failed: {exc!r}",
                    file=sys.stderr,
                )
            except Exception:
                pass

            if consecutive_failures >= max_consec:
                try:
                    print(
                        f"[tradingview_mcp] volume_breakout_scan aborted: "
                        f"{consecutive_failures} consecutive batch failures "
                        f"at batch {batches_attempted}/{total_batches}",
                        file=sys.stderr,
                    )
                except Exception:
                    pass
                break
            continue

        for symbol, data in analysis.items():
            try:
                if not data or not hasattr(data, "indicators"):
                    continue
                ind = data.indicators

                volume = ind.get("volume", 0)
                close = ind.get("close", 0)
                open_price = ind.get("open", 0)
                sma20_volume = ind.get("volume.SMA20", 0)

                if not all([volume, close, open_price]) or volume <= 0:
                    continue

                price_change = ((close - open_price) / open_price) * 100 if open_price > 0 else 0

                if sma20_volume and sma20_volume > 0:
                    volume_ratio = volume / sma20_volume
                else:
                    avg_estimate = volume / 2
                    volume_ratio = volume / avg_estimate if avg_estimate > 0 else 1

                if abs(price_change) >= price_change_min and volume_ratio >= volume_multiplier:
                    rsi = ind.get("RSI", 50)
                    bb_upper = ind.get("BB.upper", 0)
                    bb_lower = ind.get("BB.lower", 0)
                    volume_strength = min(10, volume_ratio)

                    volume_breakouts.append(
                        {
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
                                "volume": volume,
                            },
                        }
                    )
            except Exception:
                continue

    # Sentinel: every batch failed means the upstream is unavailable
    # (rate limit, blocked, outage). Raise so the tool wrapper can return a
    # typed error envelope instead of an indistinguishable empty list.
    if batches_attempted > 0 and batches_failed == batches_attempted:
        raise BatchExecutionError(
            batches_attempted=batches_attempted,
            batches_failed=batches_failed,
            first_error=first_error or "unknown",
        )

    volume_breakouts.sort(
        key=lambda x: (x["volume_strength"], abs(x["changePercent"])),
        reverse=True,
    )
    return volume_breakouts[:limit]


# ── Volume confirmation (single symbol) ───────────────────────────────────────

def volume_confirmation_analyze(
    symbol: str,
    exchange: str,
    timeframe: str,
) -> dict:
    """
    Detailed volume confirmation analysis for a single asset.

    Args:
        symbol:    Validated symbol string (with exchange prefix if needed).
        exchange:  Exchange identifier.
        timeframe: TradingView interval string.

    Returns:
        Dict with price data, volume analysis, technical indicators, and signals.
    """
    # Normalise symbol
    if not is_stock_exchange(exchange) and not symbol.upper().endswith("USDT"):
        symbol = symbol.upper() + "USDT"
    else:
        symbol = symbol.upper()

    if is_stock_exchange(exchange) and ":" not in symbol:
        full_symbol = f"{exchange.upper()}:{symbol}"
    else:
        full_symbol = symbol

    screener = EXCHANGE_SCREENER.get(exchange, "crypto")

    try:
        analysis = get_multiple_analysis(screener=screener, interval=timeframe, symbols=[full_symbol])
        if not analysis or full_symbol not in analysis:
            return {"error": f"No data found for {full_symbol}"}

        data = analysis[full_symbol]
        if not data or not hasattr(data, "indicators"):
            return {"error": f"No indicator data for {full_symbol}"}

        ind = data.indicators
        volume = ind.get("volume", 0)
        close = ind.get("close", 0)
        open_price = ind.get("open", 0)
        high = ind.get("high", 0)
        low = ind.get("low", 0)

        price_change = ((close - open_price) / open_price) * 100 if open_price > 0 else 0
        candle_range = ((high - low) / low) * 100 if low > 0 else 0

        sma20_volume = ind.get("volume.SMA20", 0)
        volume_ratio = volume / sma20_volume if sma20_volume > 0 else 1

        rsi = ind.get("RSI", 50)
        bb_upper = ind.get("BB.upper", 0)
        bb_lower = ind.get("BB.lower", 0)

        signals: list[str] = []
        if volume_ratio >= 2.0 and abs(price_change) >= 3.0:
            signals.append(f"🚀 STRONG BREAKOUT: {volume_ratio:.1f}x volume + {price_change:.1f}% price")
        if volume_ratio >= 1.5 and abs(price_change) < 1.0:
            signals.append(f"⚠️ VOLUME DIVERGENCE: High volume ({volume_ratio:.1f}x) but low price movement")
        if abs(price_change) >= 2.0 and volume_ratio < 0.8:
            signals.append(f"❌ WEAK SIGNAL: Price moved but volume is low ({volume_ratio:.1f}x)")
        if close > bb_upper and volume_ratio >= 1.5:
            signals.append("💥 BB BREAKOUT CONFIRMED: Upper band breakout + volume confirmation")
        elif close < bb_lower and volume_ratio >= 1.5:
            signals.append("📉 BB SELL CONFIRMED: Lower band breakout + volume confirmation")
        if rsi > 70 and volume_ratio >= 2.0:
            signals.append(f"🔥 OVERBOUGHT + VOLUME: RSI {rsi:.1f} + {volume_ratio:.1f}x volume")
        elif rsi < 30 and volume_ratio >= 2.0:
            signals.append(f"🛒 OVERSOLD + VOLUME: RSI {rsi:.1f} + {volume_ratio:.1f}x volume")

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

        return {
            "symbol": symbol,
            "price_data": {
                "close": close,
                "change_percent": round(price_change, 2),
                "candle_range_percent": round(candle_range, 2),
            },
            "volume_analysis": {
                "current_volume": volume,
                "volume_ratio": round(volume_ratio, 2),
                "volume_strength": volume_strength,
                "average_volume": sma20_volume,
            },
            "technical_indicators": {
                "RSI": round(rsi, 1),
                "BB_position": "ABOVE" if close > bb_upper else "BELOW" if close < bb_lower else "WITHIN",
                "BB_upper": bb_upper,
                "BB_lower": bb_lower,
            },
            "signals": signals,
            "overall_assessment": {
                "bullish_signals": len([s for s in signals if any(e in s for e in ["🚀", "💥", "🛒"])]),
                "bearish_signals": len([s for s in signals if any(e in s for e in ["📉", "❌"])]),
                "warning_signals": len([s for s in signals if "⚠️" in s]),
            },
        }
    except Exception as exc:
        return {"error": f"Analysis failed: {exc}"}


# ── Smart volume scanner ───────────────────────────────────────────────────────

def smart_volume_scan(
    exchange: str,
    min_volume_ratio: float = 2.0,
    min_price_change: float = 2.0,
    rsi_range: str = "any",
    limit: int = 20,
) -> List[dict]:
    """
    Combine volume breakout scan with RSI filtering and trading recommendation.

    Args:
        exchange:         Exchange identifier.
        min_volume_ratio: Minimum volume multiplier.
        min_price_change: Minimum abs(price change %).
        rsi_range:        'oversold', 'overbought', 'neutral', or 'any'.
        limit:            Maximum results.

    Returns:
        Filtered list of volume breakout dicts with 'trading_recommendation' added.
    """
    breakouts = volume_breakout_scan(
        exchange=exchange,
        volume_multiplier=min_volume_ratio,
        price_change_min=min_price_change,
        limit=limit * 2,
    )
    if not breakouts:
        return []

    filtered: List[dict] = []
    for coin in breakouts:
        rsi = coin["indicators"].get("RSI", 50)

        if rsi_range == "oversold" and rsi >= 30:
            continue
        elif rsi_range == "overbought" and rsi <= 70:
            continue
        elif rsi_range == "neutral" and (rsi <= 30 or rsi >= 70):
            continue

        recommendation = ""
        if coin["changePercent"] > 0 and coin["volume_ratio"] >= 2.0:
            recommendation = "🚀 STRONG BUY" if rsi < 70 else "⚠️ OVERBOUGHT - CAUTION"
        elif coin["changePercent"] < 0 and coin["volume_ratio"] >= 2.0:
            recommendation = "📉 STRONG SELL" if rsi > 30 else "🛒 OVERSOLD - OPPORTUNITY?"

        coin["trading_recommendation"] = recommendation
        filtered.append(coin)

    return filtered[:limit]
