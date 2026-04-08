"""
Multi-Agent Service — sentiment scoring, risk assessment, and the
multi-agent debate pipeline for technical analysis.

All functions are pure business logic with no MCP coupling.
"""
from __future__ import annotations

from tradingview_mcp.core.services.indicators import compute_metrics
from tradingview_mcp.core.utils.validators import EXCHANGE_SCREENER

try:
    from tradingview_ta import get_multiple_analysis
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
    rsi = indicators.get("RSI", 50.0)
    macd = indicators.get("MACD.macd", 0.0)
    macd_signal = indicators.get("MACD.signal", 0.0)

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
    close = indicators.get("close", 0.0)
    sma20 = indicators.get("SMA20", close)
    ema200 = indicators.get("EMA200", close)

    score = 0
    warnings: list[str] = []

    if bbw > 0.1:
        score -= 2
        warnings.append("High volatility (Wide BBW > 0.1)")
    elif bbw < 0.03:
        score += 1
        warnings.append("Low volatility (Squeeze)")

    if ema200 is not None and close < ema200:
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

    price = metrics.get("price", 0.0)
    change = metrics.get("change", 0.0)
    bb_rating = metrics.get("rating", 0)
    bbw = metrics.get("bbw", 0.0)

    # Agent 1 — Technical Analyst
    tech_analyst = {
        "role": "Technical Analyst",
        "stance": "Bullish" if bb_rating > 0 else "Bearish" if bb_rating < 0 else "Neutral",
        "score": bb_rating,
        "key_observations": [
            f"Price is {price} ({change:+.2f}%)",
            f"Bollinger Rating: {bb_rating} ({metrics.get('signal', 'Neutral')})",
            f"RSI: {indicators.get('RSI', 50):.1f}",
        ],
    }

    # Agent 2 — Sentiment Analyst
    sentiment_data = calculate_sentiment_score(indicators, change)
    sentiment_analyst = {
        "role": "Sentiment & Momentum Analyst",
        "stance": (
            "Bullish" if sentiment_data["normalized"] > 0
            else "Bearish" if sentiment_data["normalized"] < 0
            else "Neutral"
        ),
        "score": sentiment_data["normalized"],
        "key_observations": sentiment_data["signals"],
    }

    # Agent 3 — Risk Manager
    risk_data = calculate_risk_score(indicators, bbw)
    risk_manager = {
        "role": "Risk Manager",
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

    if total_score >= 3 and risk_manager["risk_level"] != "High":
        final_decision, confidence = "STRONG BUY", "High"
    elif total_score > 0:
        final_decision, confidence = "BUY", "Medium"
    elif total_score <= -3:
        final_decision, confidence = "STRONG SELL", "High"
    elif total_score < 0:
        final_decision, confidence = "SELL", "Medium"
    else:
        final_decision, confidence = "HOLD", "Low"

    return {
        "framework_name": "TradingAgents-MCP Pipeline",
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
                f"Technical score: {tech_analyst['score']}, "
                f"Sentiment score: {sentiment_analyst['score']}, "
                f"Risk adjustment: {risk_manager['risk_score']}"
            ),
        },
    }
