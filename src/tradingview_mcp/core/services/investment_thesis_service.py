"""
Investment Thesis Service — full investment-grade report on a single symbol.

Why this exists: existing tools each answer one question (technicals,
sentiment, fundamentals, news). A real analyst's deliverable is a SINGLE
document that pulls all of them into bull case, bear case, valuation,
catalysts, risks, and a verdict with conviction.

This service orchestrates — no new data sources, just synthesis:
  - Technical:    coin_analysis (TradingView indicators)
  - Fundamental:  get_fundamentals (Yahoo quoteSummary)
  - Sentiment:    analyze_sentiment (Reddit) — optional
  - News:         fetch_news_summary (RSS) — optional
  - Macro (crypto): get_bitcoin_market_pulse — optional
  - Risk:         value_at_risk on the position — optional

Each upstream call is wrapped in try/except so a single failed dependency
doesn't kill the thesis. Missing sections are flagged in `data_quality`
so the consumer can see what's incomplete.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from tradingview_mcp.core.services.fundamentals_service import get_fundamentals
from tradingview_mcp.core.services.screener_service import analyze_coin
from tradingview_mcp.core.services.sentiment_service import analyze_sentiment
from tradingview_mcp.core.services.news_service import fetch_news_summary
from tradingview_mcp.core.services.bitcoin_market_service import get_bitcoin_market_pulse
from tradingview_mcp.core.services.risk_service import value_at_risk


_CRYPTO_EXCHANGES = {"BINANCE", "KUCOIN", "BYBIT", "MEXC", "OKX", "GATEIO", "COINBASE", "HUOBI", "BITFINEX", "BITGET"}


def _is_crypto(exchange: str) -> bool:
    return exchange.upper() in _CRYPTO_EXCHANGES


def _safe(fn, *args, **kwargs):
    """Call fn but never raise — return (result, error_message)."""
    try:
        out = fn(*args, **kwargs)
        if isinstance(out, dict) and "error" in out:
            return None, out["error"]
        return out, None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _to_yahoo_symbol(symbol: str, exchange: str) -> str:
    """Map TradingView-style symbols to Yahoo Finance equivalents.

    - Crypto: BTCUSDT (Binance/KuCoin) → BTC-USD (Yahoo)
    - BIST:   THYAO → THYAO.IS
    - SSE:    600519 → 600519.SS
    - SZSE:   300251 → 300251.SZ
    - TWSE:   2330 → 2330.TW
    - HKEX:   00700 → 0700.HK
    - EGX:    COMI → COMI.CA
    - NASDAQ/NYSE/AMEX: leave as-is
    """
    s = symbol.upper().replace(":", "").strip()
    e = exchange.upper()

    if _is_crypto(e):
        for quote in ("USDT", "BUSD", "USDC", "USD"):
            if s.endswith(quote):
                base = s[: -len(quote)]
                return f"{base}-USD"
        return s

    suffix_map = {
        "BIST": ".IS",
        "SSE": ".SS",
        "SZSE": ".SZ",
        "TWSE": ".TW",
        "TPEX": ".TWO",
        "HKEX": ".HK",
        "EGX": ".CA",
        "BURSA": ".KL",
        "KLSE": ".KL",
    }
    suffix = suffix_map.get(e)
    if suffix and not s.endswith(suffix):
        return f"{s}{suffix}"
    return s


def _verdict_from_signals(scores: dict) -> tuple[str, str, list[str]]:
    """Aggregate signed scores into final verdict + conviction + reasoning.

    Each input contributes a signed weight; we sum and bucket the total.
    Reasoning list shows which signals agreed and which conflicted.
    """
    total = sum(scores.values())
    n_inputs = len([v for v in scores.values() if v != 0])
    agreement: list[str] = []

    if total >= 4:
        verdict = "STRONG_BUY"
    elif total >= 2:
        verdict = "BUY"
    elif total <= -4:
        verdict = "STRONG_SELL"
    elif total <= -2:
        verdict = "SELL"
    else:
        verdict = "HOLD"

    positives = [k for k, v in scores.items() if v > 0]
    negatives = [k for k, v in scores.items() if v < 0]

    if n_inputs >= 3 and len(positives) >= n_inputs - 1 and not negatives:
        conviction = "HIGH"
        agreement.append("All signals align bullish — high-conviction setup.")
    elif n_inputs >= 3 and len(negatives) >= n_inputs - 1 and not positives:
        conviction = "HIGH"
        agreement.append("All signals align bearish — high-conviction warning.")
    elif positives and negatives:
        conviction = "LOW"
        agreement.append(
            f"Mixed signals: bullish {positives} vs bearish {negatives}. "
            "Wait for confluence or reduce position size."
        )
    elif n_inputs <= 1:
        conviction = "LOW"
        agreement.append("Limited data — only one signal available. Treat as preliminary.")
    else:
        conviction = "MEDIUM"
        agreement.append(f"Partial confluence: {positives or negatives}")

    return verdict, conviction, agreement


def generate_investment_thesis(
    symbol: str,
    exchange: str = "NASDAQ",
    timeframe: str = "1D",
    position_value: Optional[float] = None,
    include_news: bool = True,
    include_sentiment: bool = True,
) -> dict:
    """Build a structured investment thesis pulling every dimension together.

    Args:
        symbol: Asset symbol (AAPL, BTCUSDT, THYAO, etc.)
        exchange: Exchange — crypto: KUCOIN/BINANCE/MEXC; stocks: NASDAQ/NYSE/BIST/EGX...
        timeframe: Technical analysis timeframe (1D recommended for investing horizon)
        position_value: If provided, add VaR risk section sized to this dollar exposure.
        include_news: Pull RSS news headlines (slower; disable for speed).
        include_sentiment: Pull Reddit sentiment (slower; disable for speed).

    Returns:
        Multi-section dict: identity, technical, fundamental, sentiment, news,
        macro_context, risk, bull_case, bear_case, catalysts, price_targets,
        verdict, data_quality.
    """
    symbol_clean = symbol.upper().strip()
    # sanitize_exchange (called in the MCP wrapper) returns the lowercase
    # canonical form that EXCHANGE_SCREENER expects. Pass it through verbatim
    # to analyze_coin; only uppercase the copy used for Yahoo-symbol mapping.
    exchange_canonical = exchange.strip().lower()
    is_crypto = _is_crypto(exchange_canonical)
    yahoo_sym = _to_yahoo_symbol(symbol_clean, exchange_canonical)

    bull_case: list[str] = []
    bear_case: list[str] = []
    catalysts: list[str] = []
    risks: list[str] = []
    scores: dict[str, int] = {}
    data_quality: dict[str, str] = {}

    # ── 1. Technical analysis ────────────────────────────────────────────
    # analyze_coin handles the exchange prefix internally; pass the raw symbol
    # to match the convention used by combined_analysis.
    tech, tech_err = _safe(analyze_coin, symbol_clean, exchange_canonical, timeframe)
    if tech_err:
        data_quality["technical"] = f"failed: {tech_err}"
        tech_signal = None
    else:
        data_quality["technical"] = "ok"
        ms = tech.get("market_sentiment", {}) if isinstance(tech, dict) else {}
        tech_signal = ms.get("buy_sell_signal") or ms.get("recommendation")
        momentum = ms.get("momentum", "")

        if tech_signal in ("STRONG_BUY", "BUY"):
            scores["technical"] = 2 if tech_signal == "STRONG_BUY" else 1
            bull_case.append(f"Technical: {tech_signal} on {timeframe} — {momentum or 'positive momentum'}.")
        elif tech_signal in ("STRONG_SELL", "SELL"):
            scores["technical"] = -2 if tech_signal == "STRONG_SELL" else -1
            bear_case.append(f"Technical: {tech_signal} on {timeframe} — {momentum or 'negative momentum'}.")
        else:
            scores["technical"] = 0

        indicators = tech.get("indicators", {}) if isinstance(tech, dict) else {}
        rsi = indicators.get("RSI")
        if rsi is not None:
            if rsi < 30:
                bull_case.append(f"RSI {rsi:.1f} — oversold, mean-reversion setup possible.")
            elif rsi > 70:
                bear_case.append(f"RSI {rsi:.1f} — overbought, vulnerable to pullback.")

    # ── 2. Fundamental (only meaningful for stocks) ──────────────────────
    if not is_crypto:
        fund, fund_err = _safe(get_fundamentals, yahoo_sym)
        if fund_err or not fund:
            data_quality["fundamental"] = f"failed: {fund_err}"
            fund = None
        else:
            data_quality["fundamental"] = "ok"
            v = fund.get("verdict", {})
            label = v.get("label", "")
            if "STRONG_FUNDAMENTAL_BUY" in label:
                scores["fundamental"] = 2
            elif "FUNDAMENTAL_BUY" in label:
                scores["fundamental"] = 1
            elif "STRONG_FUNDAMENTAL_SELL" in label:
                scores["fundamental"] = -2
            elif "FUNDAMENTAL_SELL" in label:
                scores["fundamental"] = -1
            else:
                scores["fundamental"] = 0

            for f in v.get("bullish_factors", []):
                bull_case.append(f"Fundamental: {f}.")
            for f in v.get("bearish_factors", []):
                bear_case.append(f"Fundamental: {f}.")

            targets = fund.get("analyst_targets", {})
            mean_t = targets.get("mean")
            current_price = None
            try:
                current_price = tech.get("price", {}).get("close") if tech else None
            except Exception:
                pass
            if mean_t and current_price:
                upside = (mean_t - current_price) / current_price * 100
                if upside > 15:
                    catalysts.append(f"Analyst mean target ${mean_t:.2f} implies {upside:+.1f}% upside.")
                elif upside < -10:
                    risks.append(f"Analyst mean target ${mean_t:.2f} implies {upside:+.1f}% downside.")
    else:
        fund = None
        data_quality["fundamental"] = "skipped (crypto)"

    # ── 3. Sentiment (Reddit) ────────────────────────────────────────────
    if include_sentiment:
        cat = "crypto" if is_crypto else "stocks"
        sent_base = symbol_clean.replace("USDT", "").replace("-USD", "")
        sent, sent_err = _safe(analyze_sentiment, sent_base, cat, 20)
        if sent_err or not sent:
            data_quality["sentiment"] = f"failed: {sent_err}"
            sent = None
        else:
            data_quality["sentiment"] = "ok"
            score = sent.get("sentiment_score", 0)
            label = sent.get("sentiment_label", "")
            n_posts = sent.get("posts_analyzed", 0)
            if n_posts < 5:
                data_quality["sentiment"] = f"thin ({n_posts} posts)"
            if score > 0.25:
                scores["sentiment"] = 1
                bull_case.append(f"Reddit sentiment: {label} ({score:+.2f}, {n_posts} posts).")
            elif score < -0.25:
                scores["sentiment"] = -1
                bear_case.append(f"Reddit sentiment: {label} ({score:+.2f}, {n_posts} posts).")
            else:
                scores["sentiment"] = 0
    else:
        sent = None
        data_quality["sentiment"] = "skipped"

    # ── 4. News headlines ────────────────────────────────────────────────
    if include_news:
        cat = "crypto" if is_crypto else "stocks"
        news_base = symbol_clean.replace("USDT", "").replace("-USD", "")
        news, news_err = _safe(fetch_news_summary, news_base, cat, 5)
        if news_err or not news:
            data_quality["news"] = f"failed: {news_err}"
            news = None
        else:
            data_quality["news"] = "ok"
            items = news.get("items", [])[:3]
            for it in items:
                title = it.get("title", "")
                if title:
                    catalysts.append(f"News: {title}")
    else:
        news = None
        data_quality["news"] = "skipped"

    # ── 5. Macro context (crypto only — BTC pulse) ───────────────────────
    macro = None
    if is_crypto:
        macro, macro_err = _safe(get_bitcoin_market_pulse)
        if macro_err or not macro:
            data_quality["macro"] = f"failed: {macro_err}"
            macro = None
        else:
            data_quality["macro"] = "ok"
            assessment = macro.get("assessment", {})
            label = assessment.get("label", "")
            if label in ("HIGH_RISK", "ALT_RISK"):
                scores["macro"] = -1
                risks.append(f"Macro: BTC environment is {label} — {assessment.get('summary', '')}")
            elif label == "ALT_FAVORABLE":
                scores["macro"] = 1
                bull_case.append(f"Macro: BTC environment is {label} — {assessment.get('summary', '')}")
            elif label == "OPPORTUNITY_WITH_CAUTION":
                scores["macro"] = 0
                catalysts.append(f"Macro: {assessment.get('summary', '')}")

    # ── 6. Risk sizing (only if position_value provided) ────────────────
    risk_block = None
    if position_value and position_value > 0:
        risk_block, risk_err = _safe(value_at_risk, yahoo_sym, position_value, "6mo", 0.95, 1)
        if risk_err or not risk_block:
            data_quality["risk"] = f"failed: {risk_err}"
            risk_block = None
        else:
            data_quality["risk"] = "ok"
            hist = risk_block.get("historical_var", {})
            loss_dollars = hist.get("loss_dollars", 0)
            if loss_dollars:
                risks.append(
                    f"1-day 95% VaR: ${abs(loss_dollars):,.0f} possible loss on "
                    f"${position_value:,.0f} position (historical method)."
                )

    # ── 7. Aggregate verdict ─────────────────────────────────────────────
    verdict, conviction, reasoning = _verdict_from_signals(scores)

    # ── 8. Price targets ─────────────────────────────────────────────────
    price_targets = {}
    if fund:
        targets = fund.get("analyst_targets", {})
        price_targets = {
            "analyst_mean": targets.get("mean"),
            "analyst_high": targets.get("high"),
            "analyst_low": targets.get("low"),
            "analyst_recommendation": targets.get("recommendation"),
        }
    if tech and isinstance(tech, dict):
        setup = tech.get("trade_setup", {}) or {}
        if setup:
            price_targets["technical_entry"] = setup.get("entry")
            price_targets["technical_stop"] = setup.get("stop_loss")
            price_targets["technical_target"] = setup.get("take_profit")

    return {
        "symbol": symbol_clean,
        "exchange": exchange_canonical,
        "yahoo_symbol": yahoo_sym,
        "timeframe": timeframe,
        "asset_class": "crypto" if is_crypto else "equity",
        "company_name": (fund.get("name") if fund else None),
        "timestamp": datetime.now(timezone.utc).isoformat(),

        "verdict": {
            "label": verdict,
            "conviction": conviction,
            "score_breakdown": scores,
            "total_score": sum(scores.values()),
            "reasoning": reasoning,
        },

        "bull_case": bull_case,
        "bear_case": bear_case,
        "catalysts": catalysts,
        "risks": risks,
        "price_targets": price_targets,

        "sections": {
            "technical": tech,
            "fundamental": fund,
            "sentiment": sent,
            "news": news,
            "macro_context": macro,
            "risk_sizing": risk_block,
        },

        "data_quality": data_quality,
    }
