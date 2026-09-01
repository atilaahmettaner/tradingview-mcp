"""
Multi-Agent Service — sentiment scoring, risk assessment, and the
multi-agent debate pipeline for technical analysis.

All functions are pure business logic with no MCP coupling.
"""
from __future__ import annotations

from tradingview_mcp.core.services.indicators import compute_metrics
from tradingview_mcp.core.utils.validators import EXCHANGE_SCREENER

try:
    # Patched: route through resilience layer (retry + 60s TTL cache).
    import tradingview_ta  # noqa: F401  presence check
    from tradingview_mcp.core.services.screener_provider import (
        resilient_get_multiple_analysis as get_multiple_analysis,
    )
    _TA_AVAILABLE = True
except ImportError:
    _TA_AVAILABLE = False


# ── Scoring helpers ────────────────────────────────────────────────────────────

def calculate_sentiment_score(indicators: dict, price_change: float) -> dict:
    """
    Heuristic sentiment score based on price momentum and MACD/RSI alignment.

    Args:
        indicators:   Raw TradingView indicators dict.
        price_change: Percentage price change of the current candle.

    Returns:
        Dict with 'score' (raw), 'normalized' (-3..+3), and 'signals' list.
    """
    # TradingView returns explicit nulls, so dict.get defaults don't fire —
    # `indicators.get("RSI", 50.0)` yields None when the key exists as None,
    # and `None > 60` crashes the whole tool.
    rsi = indicators.get("RSI")
    rsi = 50.0 if rsi is None else rsi
    macd = indicators.get("MACD.macd")
    macd_signal = indicators.get("MACD.signal")

    score = 0
    signals: list[str] = []

    if price_change > 0:
        score += 1
        signals.append("Positive price momentum")
    elif price_change < 0:
        score -= 1
        signals.append("Negative price momentum")

    if rsi > 60:
        score += 1
        signals.append("Bullish RSI (>60)")
    elif rsi < 40:
        score -= 1
        signals.append("Bearish RSI (<40)")

    if macd is not None and macd_signal is not None:
        if macd > macd_signal:
            score += 1
            signals.append("MACD bullish crossover")
        elif macd < macd_signal:
            score -= 1
            signals.append("MACD bearish crossover")

    return {
        "score": score,
        "normalized": max(-3, min(3, score)),
        "signals": signals,
    }


def calculate_risk_score(indicators: dict, bbw: float) -> dict:
    """
    Risk assessment based on Bollinger Band volatility and moving average structure.

    Args:
        indicators: Raw TradingView indicators dict.
        bbw:        Bollinger Band Width value.

    Returns:
        Dict with 'score' (negative = more risk), 'warnings' list, and 'level' label.
    """
    # Explicit-null-safe reads (see calculate_sentiment_score).
    close = indicators.get("close") or 0.0
    sma20 = indicators.get("SMA20") or close
    ema200 = indicators.get("EMA200") or close
    bbw = bbw or 0.0

    score = 0
    warnings: list[str] = []

    if bbw > 0.1:
        score -= 2
        warnings.append("High volatility (Wide BBW > 0.1)")
    elif bbw < 0.03:
        score += 1
        warnings.append("Low volatility (Squeeze)")

    if ema200 and close < ema200:
        score -= 1
        warnings.append("Price below 200 EMA (Long-term bearish structure)")

    if sma20 and sma20 > 0:
        dist = abs(close - sma20) / sma20
        if dist > 0.05:
            score -= 1
            direction = "above" if close > sma20 else "below"
            warnings.append(f"Extended from 20 SMA (5%+ {direction} mean)")

    return {
        "score": score,
        "warnings": warnings if warnings else ["Normal risk parameters"],
        "level": "High" if score < -1 else "Medium" if score == -1 else "Low",
    }


# ── Multi-agent debate pipeline ────────────────────────────────────────────────

def run_multi_agent_analysis(
    symbol: str,
    exchange: str,
    timeframe: str,
) -> dict:
    """
    Run a three-agent debate (Technical, Sentiment, Risk) and return a consensus.

    Args:
        symbol:    Full symbol string with exchange prefix (e.g. 'KUCOIN:BTCUSDT').
        exchange:  Validated exchange identifier.
        timeframe: Validated timeframe string.

    Returns:
        Structured debate result with per-agent view and final decision.
    """
    screener = EXCHANGE_SCREENER.get(exchange, "crypto")

    analysis = get_multiple_analysis(
        screener=screener,
        interval=timeframe,
        symbols=[symbol],
    )

    if symbol not in analysis or analysis[symbol] is None:
        return {"error": f"No data found for {symbol}"}

    indicators = analysis[symbol].indicators
    metrics = compute_metrics(indicators)
    if not metrics:
        return {"error": f"Could not compute metrics for {symbol}"}

    price = metrics.get("price") or 0.0
    change = metrics.get("change") or 0.0
    bb_rating = metrics.get("rating") or 0
    bbw = metrics.get("bbw") or 0.0  # compute_metrics returns bbw=None sometimes

    # Rule set 1 — Bollinger/price checklist
    tech_analyst = {
        "role": "Trend & Bands (rule set)",
        "stance": "Bullish" if bb_rating > 0 else "Bearish" if bb_rating < 0 else "Neutral",
        "score": bb_rating,
        "key_observations": [
            f"Price is {price} ({change:+.2f}%)",
            f"Bollinger Rating: {bb_rating} ({metrics.get('signal', 'Neutral')})",
            f"RSI: {indicators.get('RSI') or 50.0:.1f}",
        ],
    }

    # Rule set 2 — momentum checklist (RSI/MACD only; no news or sentiment
    # source feeds this, so it must not be labeled "sentiment").
    sentiment_data = calculate_sentiment_score(indicators, change)
    sentiment_analyst = {
        "role": "Momentum (RSI/MACD rule set)",
        "stance": (
            "Bullish" if sentiment_data["normalized"] > 0
            else "Bearish" if sentiment_data["normalized"] < 0
            else "Neutral"
        ),
        "score": sentiment_data["normalized"],
        "key_observations": sentiment_data["signals"],
    }

    # Rule set 3 — volatility/structure checklist
    risk_data = calculate_risk_score(indicators, bbw)
    risk_manager = {
        "role": "Volatility & Structure (rule set)",
        "risk_level": risk_data["level"],
        "risk_score": risk_data["score"],
        "warnings": risk_data["warnings"],
    }

    # Final consensus
    total_score = (
        tech_analyst["score"]
        + sentiment_analyst["score"]
        + risk_manager["risk_score"]
    )

    # "confidence" here is rule agreement, not a probability — the wording
    # must never suggest conviction the underlying single snapshot can't carry.
    if total_score >= 3 and risk_manager["risk_level"] != "High":
        final_decision, confidence = "BUY (strong rule alignment)", "rules strongly aligned"
    elif total_score > 0:
        final_decision, confidence = "BUY (mixed rules)", "rules partially aligned"
    elif total_score <= -3:
        final_decision, confidence = "SELL (strong rule alignment)", "rules strongly aligned"
    elif total_score < 0:
        final_decision, confidence = "SELL (mixed rules)", "rules partially aligned"
    else:
        final_decision, confidence = "HOLD", "rules disagree"

    return {
        "framework_name": "Rule-Based Signal Summary",
        "method_note": (
            "Deterministic indicator checklist computed from a single delayed "
            "snapshot. This is not an AI debate, contains no news/sentiment "
            "input, and the decision is a threshold artifact, not a probability."
        ),
        "target": symbol,
        "timeframe": timeframe,
        "agents_debate": {
            "technical_analyst": tech_analyst,
            "sentiment_analyst": sentiment_analyst,
            "risk_manager": risk_manager,
        },
        "consensus": {
            "decision": final_decision,
            "confidence": confidence,
            "net_score": total_score,
            "summary": (
                f"Bands score: {tech_analyst['score']}, "
                f"Momentum score: {sentiment_analyst['score']}, "
                f"Volatility adjustment: {risk_manager['risk_score']}"
            ),
        },
    }
