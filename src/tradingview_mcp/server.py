"""
TradingView MCP Server — routing layer only.

Each @mcp.tool() handler is responsible for:
  1. Validating / sanitising parameters
  2. Delegating to the appropriate service module
  3. Returning the result

No business logic lives here. All computation is in core/services/*.
"""
from __future__ import annotations

import argparse
import os

from mcp.server.fastmcp import FastMCP

# ── Service imports ────────────────────────────────────────────────────────────
from tradingview_mcp.core.services.coinlist import load_symbols
from tradingview_mcp.core.services.screener_service import (
    fetch_bollinger_analysis,
    fetch_trending_analysis,
    analyze_coin,
    scan_consecutive_candles,
    scan_advanced_candle_patterns_single_tf,
    fetch_multi_timeframe_patterns,
    run_multi_timeframe_analysis,
)
from tradingview_mcp.core.services.scanner_service import (
    volume_breakout_scan,
    volume_confirmation_analyze,
    smart_volume_scan,
)
from tradingview_mcp.core.services.multi_agent_service import run_multi_agent_analysis
from tradingview_mcp.core.services.egx_service import (
    get_egx_market_overview,
    scan_egx_sector,
    run_egx_sector_scanner,
    analyze_egx_index,
    screen_egx_stocks,
    generate_egx_trade_plan,
    analyze_egx_fibonacci,
)
from tradingview_mcp.core.services.sentiment_service import analyze_sentiment
from tradingview_mcp.core.services.news_service import fetch_news_summary
from tradingview_mcp.core.services.yahoo_finance_service import (
    get_price,
    get_market_snapshot,
)
from tradingview_mcp.core.services.bitcoin_market_service import get_bitcoin_market_pulse
from tradingview_mcp.core.services.extended_hours_service import get_extended_hours_price
from tradingview_mcp.core.services.backtest_service import (
    run_backtest,
    compare_strategies as _compare_strategies,
    walk_forward_backtest,
)
from tradingview_mcp.core.services.fundamentals_service import (
    get_fundamentals,
    compare_peers as _compare_peers,
    get_dividend_info,
)
from tradingview_mcp.core.services.risk_service import (
    position_size as _position_size,
    risk_reward as _risk_reward,
    kelly_criterion as _kelly_criterion,
    correlation_matrix as _correlation_matrix,
    value_at_risk as _value_at_risk,
)
from tradingview_mcp.core.services.investment_thesis_service import generate_investment_thesis
from tradingview_mcp.core.utils.validators import (
    sanitize_timeframe,
    sanitize_exchange,
    normalize_tradingview_symbol,
    normalize_yahoo_symbol,
)

try:
    import tradingview_screener  # noqa: F401
    TRADINGVIEW_SCREENER_AVAILABLE = True
except ImportError:
    TRADINGVIEW_SCREENER_AVAILABLE = False


# ── MCP server instance ────────────────────────────────────────────────────────

mcp = FastMCP(
    name="TradingView Multi-Market Screener",
    instructions=(
        "Multi-market screener backed by TradingView. "
        "Supports crypto exchanges (KuCoin, Binance, Bybit, MEXC, etc.) and stock markets "
        "(EGX, BIST, NASDAQ, NYSE, Bursa Malaysia, HKEX, SSE, SZSE, TWSE, TPEX). "
        "Tools: top_gainers, top_losers, bollinger_scan, coin_analysis, multi_agent_analysis, "
        "volume_breakout_scanner, egx_market_overview, egx_sector_scan, and more."
    ),
)


# ── Screener tools ─────────────────────────────────────────────────────────────

@mcp.tool()
def top_gainers(exchange: str = "KUCOIN", timeframe: str = "15m", limit: int = 25) -> list[dict]:
    """Return top gainers for an exchange and timeframe using Bollinger Band analysis.

    Args:
        exchange: Exchange name — crypto: KUCOIN, BINANCE, BYBIT, MEXC; stocks: EGX, BIST, NASDAQ, NYSE, BURSA, HKEX, SSE, SZSE, TWSE, TPEX
        timeframe: One of 5m, 15m, 1h, 4h, 1D, 1W, 1M
        limit: Number of rows to return (max 50)
    """
    exchange = sanitize_exchange(exchange, "KUCOIN")
    timeframe = sanitize_timeframe(timeframe, "15m")
    limit = max(1, min(limit, 50))
    rows = fetch_trending_analysis(exchange, timeframe=timeframe, limit=limit)
    return [{"symbol": r["symbol"], "changePercent": r["changePercent"], "indicators": dict(r["indicators"])} for r in rows]


@mcp.tool()
def top_losers(exchange: str = "KUCOIN", timeframe: str = "15m", limit: int = 25) -> list[dict]:
    """Return top losers for an exchange and timeframe. Supports crypto (KUCOIN, BINANCE, MEXC) and stocks (EGX, BIST, NASDAQ)."""
    exchange = sanitize_exchange(exchange, "KUCOIN")
    timeframe = sanitize_timeframe(timeframe, "15m")
    limit = max(1, min(limit, 50))
    rows = fetch_trending_analysis(exchange, timeframe=timeframe, limit=limit)
    rows.sort(key=lambda x: x["changePercent"])
    return [{"symbol": r["symbol"], "changePercent": r["changePercent"], "indicators": dict(r["indicators"])} for r in rows[:limit]]


@mcp.tool()
def bollinger_scan(exchange: str = "KUCOIN", timeframe: str = "4h", bbw_threshold: float = 0.04, limit: int = 50) -> list[dict]:
    """Scan for assets with low Bollinger Band Width (squeeze detection). Works with crypto and stocks.

    Args:
        exchange: Exchange — crypto: KUCOIN, BINANCE, BYBIT, MEXC; stocks: EGX, BIST, NASDAQ, NYSE, BURSA, HKEX, SSE, SZSE, TWSE, TPEX
        timeframe: One of 5m, 15m, 1h, 4h, 1D, 1W, 1M
        bbw_threshold: Maximum BBW value to filter (default 0.04)
        limit: Number of rows to return (max 100)
    """
    exchange = sanitize_exchange(exchange, "KUCOIN")
    timeframe = sanitize_timeframe(timeframe, "4h")
    limit = max(1, min(limit, 100))
    rows = fetch_bollinger_analysis(exchange, timeframe=timeframe, bbw_filter=bbw_threshold, limit=limit)
    return [{"symbol": r["symbol"], "changePercent": r["changePercent"], "indicators": dict(r["indicators"])} for r in rows]


@mcp.tool()
def rating_filter(exchange: str = "KUCOIN", timeframe: str = "5m", rating: int = 2, limit: int = 25) -> list[dict]:
    """Filter coins by Bollinger Band rating.

    Args:
        exchange: Exchange name like KUCOIN, BINANCE, BYBIT, MEXC, etc.
        timeframe: One of 5m, 15m, 1h, 4h, 1D, 1W, 1M
        rating: BB rating (-3 to +3): -3=Strong Sell, -2=Sell, -1=Weak Sell, 1=Weak Buy, 2=Buy, 3=Strong Buy
        limit: Number of rows to return (max 50)
    """
    exchange = sanitize_exchange(exchange, "KUCOIN")
    timeframe = sanitize_timeframe(timeframe, "5m")
    rating = max(-3, min(3, rating))
    limit = max(1, min(limit, 50))
    rows = fetch_trending_analysis(exchange, timeframe=timeframe, filter_type="rating", rating_filter=rating, limit=limit)
    return [{"symbol": r["symbol"], "changePercent": r["changePercent"], "indicators": dict(r["indicators"])} for r in rows]


# ── Coin / asset analysis ──────────────────────────────────────────────────────

@mcp.tool()
def coin_analysis(symbol: str, exchange: str = "KUCOIN", timeframe: str = "15m") -> dict:
    """Get detailed analysis for a specific asset (coin or stock) on specified exchange and timeframe.

    Args:
        symbol: Symbol — crypto: "BTCUSDT", "ETHUSDT"; stocks: "COMI" (EGX), "THYAO" (BIST), "600519" (SSE), "300251" (SZSE), "2330" (TWSE), "3105" (TPEX)
        exchange: Exchange — crypto: KUCOIN, BINANCE, MEXC; stocks: EGX, BIST, NASDAQ, NYSE, BURSA, HKEX, SSE, SZSE, TWSE, TPEX
        timeframe: Time interval (5m, 15m, 1h, 4h, 1D, 1W, 1M)

    Returns:
        Detailed analysis with all indicators and metrics
    """
    exchange = sanitize_exchange(exchange, "KUCOIN")
    timeframe = sanitize_timeframe(timeframe, "15m")
    return analyze_coin(symbol, exchange, timeframe)


# ── Candle pattern tools ───────────────────────────────────────────────────────

@mcp.tool()
def consecutive_candles_scan(
    exchange: str = "KUCOIN",
    timeframe: str = "15m",
    pattern_type: str = "bullish",
    candle_count: int = 3,
    min_growth: float = 2.0,
    limit: int = 20,
) -> dict:
    """Scan for coins with consecutive growing/shrinking candles pattern.

    Args:
        exchange: Exchange name (BINANCE, KUCOIN, etc.)
        timeframe: Time interval (5m, 15m, 1h, 4h)
        pattern_type: "bullish" (growing candles) or "bearish" (shrinking candles)
        candle_count: Number of consecutive candles to check (2-5)
        min_growth: Minimum growth percentage for each candle
        limit: Maximum number of results to return
    """
    exchange = sanitize_exchange(exchange, "KUCOIN")
    timeframe = sanitize_timeframe(timeframe, "15m")
    candle_count = max(2, min(5, candle_count))
    min_growth = max(0.5, min(20.0, min_growth))
    limit = max(1, min(50, limit))
    return scan_consecutive_candles(exchange, timeframe, pattern_type, candle_count, min_growth, limit)


@mcp.tool()
def advanced_candle_pattern(
    exchange: str = "KUCOIN",
    base_timeframe: str = "15m",
    pattern_length: int = 3,
    min_size_increase: float = 10.0,
    limit: int = 15,
) -> dict:
    """Advanced candle pattern analysis using multi-timeframe data.

    Args:
        exchange: Exchange name (BINANCE, KUCOIN, etc.)
        base_timeframe: Base timeframe for analysis (5m, 15m, 1h, 4h)
        pattern_length: Number of consecutive periods to analyse (2-4)
        min_size_increase: Minimum percentage increase in candle size
        limit: Maximum number of results to return
    """
    exchange = sanitize_exchange(exchange, "KUCOIN")
    base_timeframe = sanitize_timeframe(base_timeframe, "15m")
    pattern_length = max(2, min(4, pattern_length))
    min_size_increase = max(5.0, min(50.0, min_size_increase))
    limit = max(1, min(30, limit))

    symbols = load_symbols(exchange)
    if not symbols:
        return {"error": f"No symbols found for exchange: {exchange}", "exchange": exchange}
    symbols = symbols[: min(limit * 2, 100)]

    if TRADINGVIEW_SCREENER_AVAILABLE:
        try:
            results = fetch_multi_timeframe_patterns(exchange, symbols, base_timeframe, pattern_length, min_size_increase)
            return {
                "exchange": exchange,
                "base_timeframe": base_timeframe,
                "pattern_length": pattern_length,
                "min_size_increase": min_size_increase,
                "method": "multi-timeframe",
                "total_found": len(results),
                "data": results[:limit],
            }
        except Exception:
            pass  # Fall through to single-timeframe fallback

    return scan_advanced_candle_patterns_single_tf(exchange, symbols, base_timeframe, pattern_length, min_size_increase, limit)


# ── Volume scanner tools ───────────────────────────────────────────────────────

@mcp.tool()
def volume_breakout_scanner(
    exchange: str = "KUCOIN",
    timeframe: str = "15m",
    volume_multiplier: float = 2.0,
    price_change_min: float = 3.0,
    limit: int = 25,
) -> list[dict]:
    """Detect coins with volume breakout + price breakout.

    Args:
        exchange: Exchange name like KUCOIN, BINANCE, BYBIT, MEXC, etc.
        timeframe: One of 5m, 15m, 1h, 4h, 1D, 1W, 1M
        volume_multiplier: How many times the volume should be above normal level (default 2.0)
        price_change_min: Minimum price change percentage (default 3.0)
        limit: Number of rows to return (max 50)
    """
    exchange = sanitize_exchange(exchange, "KUCOIN")
    timeframe = sanitize_timeframe(timeframe, "15m")
    volume_multiplier = max(1.5, min(10.0, volume_multiplier))
    price_change_min = max(1.0, min(20.0, price_change_min))
    limit = max(1, min(limit, 50))
    return volume_breakout_scan(exchange, timeframe, volume_multiplier, price_change_min, limit)


@mcp.tool()
def volume_confirmation_analysis(symbol: str, exchange: str = "KUCOIN", timeframe: str = "15m") -> dict:
    """Detailed volume confirmation analysis for a specific coin.

    Args:
        symbol: Coin symbol (e.g., BTCUSDT)
        exchange: Exchange name
        timeframe: Time frame for analysis
    """
    exchange = sanitize_exchange(exchange, "KUCOIN")
    timeframe = sanitize_timeframe(timeframe, "15m")
    return volume_confirmation_analyze(symbol, exchange, timeframe)


@mcp.tool()
def smart_volume_scanner(
    exchange: str = "KUCOIN",
    min_volume_ratio: float = 2.0,
    min_price_change: float = 2.0,
    rsi_range: str = "any",
    limit: int = 20,
) -> list[dict]:
    """Smart volume + technical analysis combination scanner.

    Args:
        exchange: Exchange name
        min_volume_ratio: Minimum volume multiplier (default 2.0)
        min_price_change: Minimum price change percentage (default 2.0)
        rsi_range: "oversold" (<30), "overbought" (>70), "neutral" (30-70), "any"
        limit: Number of results (max 30)
    """
    exchange = sanitize_exchange(exchange, "KUCOIN")
    min_volume_ratio = max(1.2, min(10.0, min_volume_ratio))
    min_price_change = max(0.5, min(20.0, min_price_change))
    limit = max(1, min(limit, 30))
    return smart_volume_scan(exchange, min_volume_ratio, min_price_change, rsi_range, limit)


# ── Multi-agent analysis ───────────────────────────────────────────────────────

@mcp.tool()
def multi_agent_analysis(symbol: str, exchange: str = "KUCOIN", timeframe: str = "15m") -> dict:
    """Run a multi-agent debate (Technical, Sentiment, Risk) for a specific symbol.

    Args:
        symbol: Symbol — crypto: "BTCUSDT"; stocks: "COMI" (EGX), "THYAO" (BIST), "600519" (SSE), "300251" (SZSE), "2330" (TWSE), "3105" (TPEX), "GDX" (AMEX)
        exchange: Exchange — crypto: KUCOIN, BINANCE, MEXC; stocks: EGX, BIST, NASDAQ, NYSE, AMEX, NYSEARCA, PCX, SSE, SZSE, TWSE, TPEX
        timeframe: Time interval (5m, 15m, 1h, 4h, 1D, 1W)

    Returns:
        A structured debate between 3 AI agents culminating in a final trading decision.
    """
    exchange = sanitize_exchange(exchange, "KUCOIN")
    timeframe = sanitize_timeframe(timeframe, "15m")
    full_symbol = normalize_tradingview_symbol(symbol, exchange)
    return run_multi_agent_analysis(full_symbol, exchange, timeframe)


# ── EGX market tools ───────────────────────────────────────────────────────────

@mcp.tool()
def egx_market_overview(timeframe: str = "1D", limit: int = 10) -> dict:
    """Get a comprehensive overview of the Egyptian Exchange (EGX) market.

    Args:
        timeframe: One of 5m, 15m, 1h, 4h, 1D, 1W, 1M (default 1D for stocks)
        limit: Number of stocks per category (max 20)
    """
    timeframe = sanitize_timeframe(timeframe, "1D")
    limit = max(1, min(limit, 20))
    return get_egx_market_overview(timeframe, limit)


@mcp.tool()
def egx_sector_scan(sector: str = "", timeframe: str = "1D", limit: int = 20) -> dict:
    """Scan EGX stocks by sector. Shows available sectors if none specified.

    Args:
        sector: Sector name (banks, healthcare_and_pharma, real_estate, etc.)
                Leave empty to list all sectors.
        timeframe: One of 5m, 15m, 1h, 4h, 1D, 1W, 1M
        limit: Max results per sector (max 50)
    """
    timeframe = sanitize_timeframe(timeframe, "1D")
    limit = max(1, min(limit, 50))
    return scan_egx_sector(sector, timeframe, limit)


@mcp.tool()
def egx_sector_scanner(
    timeframe: str = "1D",
    top_n_sectors: int = 5,
    top_n_stocks: int = 3,
    min_stock_score: int = 60,
) -> dict:
    """Sector rotation scanner for EGX — identifies hot/cold sectors and top picks.

    Args:
        timeframe: One of 5m, 15m, 1h, 4h, 1D, 1W, 1M (default 1D)
        top_n_sectors: Number of top sectors to show stock picks for (1-18, default 5)
        top_n_stocks: Number of top stocks per highlighted sector (1-10, default 3)
        min_stock_score: Minimum stock score for picks (0-100, default 60)
    """
    timeframe = sanitize_timeframe(timeframe, "1D")
    top_n_sectors = max(1, min(18, top_n_sectors))
    top_n_stocks = max(1, min(10, top_n_stocks))
    min_stock_score = max(0, min(100, min_stock_score))
    return run_egx_sector_scanner(timeframe, top_n_sectors, top_n_stocks, min_stock_score)


@mcp.tool()
def egx_index_analysis(index: str = "EGX30", timeframe: str = "1D", limit: int = 30) -> dict:
    """Analyse an EGX index showing constituent performance with full indicators.

    Args:
        index: EGX30, EGX70, EGX100, SHARIAH33, EGX35LV, TAMAYUZ
        timeframe: One of 5m, 15m, 1h, 4h, 1D, 1W, 1M (default 1D)
        limit: Number of stocks to show in detail (max 100)
    """
    timeframe = sanitize_timeframe(timeframe, "1D")
    limit = max(1, min(limit, 100))
    return analyze_egx_index(index, timeframe, limit)


@mcp.tool()
def egx_stock_screener(
    timeframe: str = "1D",
    min_score: int = 55,
    index_filter: str = "",
    limit: int = 20,
) -> dict:
    """Production stock ranking engine for EGX — finds strong stocks with actionable setups.

    Args:
        timeframe: One of 5m, 15m, 1h, 4h, 1D, 1W, 1M (default 1D)
        min_score: Minimum stock score to include (0-100, default 55)
        index_filter: Filter by index — EGX30, EGX70, EGX100, SHARIAH33, EGX35LV, TAMAYUZ
        limit: Number of results (max 50)
    """
    timeframe = sanitize_timeframe(timeframe, "1D")
    min_score = max(0, min(100, min_score))
    limit = max(1, min(50, limit))
    return screen_egx_stocks(timeframe, min_score, index_filter, limit)


@mcp.tool()
def egx_trade_plan(symbol: str, timeframe: str = "1D") -> dict:
    """Generate a full trade plan for a specific EGX stock.

    Args:
        symbol: EGX stock symbol (e.g., "COMI", "TMGH", "FWRY")
        timeframe: One of 5m, 15m, 1h, 4h, 1D, 1W, 1M (default 1D)
    """
    timeframe = sanitize_timeframe(timeframe, "1D")
    return generate_egx_trade_plan(symbol, timeframe)


@mcp.tool()
def egx_fibonacci_retracement(symbol: str, lookback: str = "52W", timeframe: str = "1D") -> dict:
    """Fibonacci retracement analysis for EGX stocks.

    Args:
        symbol: EGX stock symbol (e.g., "COMI", "TMGH", "FWRY")
        lookback: Period for swing high/low — "1M", "3M", "6M", "52W", "ALL" (default 52W)
        timeframe: Analysis timeframe (5m, 15m, 1h, 4h, 1D, 1W, 1M — default 1D)
    """
    timeframe = sanitize_timeframe(timeframe, "1D")
    lookback = lookback.strip().upper()
    return analyze_egx_fibonacci(symbol, lookback, timeframe)


# ── Multi-timeframe analysis ───────────────────────────────────────────────────

@mcp.tool()
def multi_timeframe_analysis(symbol: str, exchange: str = "KUCOIN") -> dict:
    """Multi-timeframe alignment analysis (Weekly → Daily → 4H → 1H → 15m).

    Args:
        symbol: Symbol — crypto: "BTCUSDT"; stocks: "COMI" (EGX), "THYAO" (BIST), "600519" (SSE), "300251" (SZSE), "2330" (TWSE), "3105" (TPEX), "GDX" (AMEX)
        exchange: Exchange — crypto: KUCOIN, BINANCE, MEXC; stocks: EGX, BIST, NASDAQ, NYSE, AMEX, NYSEARCA, PCX, SSE, SZSE, TWSE, TPEX
    """
    exchange = sanitize_exchange(exchange, "KUCOIN")
    full_symbol = normalize_tradingview_symbol(symbol, exchange)
    return run_multi_timeframe_analysis(full_symbol, exchange)


# ── Sentiment & news tools ─────────────────────────────────────────────────────

@mcp.tool()
def market_sentiment(symbol: str, category: str = "all", limit: int = 20) -> dict:
    """Real-time Reddit sentiment analysis for stocks and crypto.

    Args:
        symbol: Asset symbol ("AAPL", "BTC", "ETH", "TSLA")
        category: Subreddit group to search ("crypto", "stocks", "all")
        limit: Number of posts to analyse
    """
    return analyze_sentiment(symbol, category, limit)


@mcp.tool()
def financial_news(symbol: str = None, category: str = "stocks", limit: int = 10) -> dict:
    """Real-time financial news from RSS feeds (Reuters, CoinDesk, etc.)

    Args:
        symbol: Optional symbol filter ("AAPL", "BTC"). None = all news.
        category: Feed category ("crypto", "stocks", "all")
        limit: Max number of news items
    """
    return fetch_news_summary(symbol, category, limit)


@mcp.tool()
def combined_analysis(symbol: str, exchange: str = "NASDAQ", timeframe: str = "1D") -> dict:
    """POWER TOOL: TradingView technical analysis + Reddit sentiment + Financial news.

    Args:
        symbol: Asset symbol ("AAPL", "BTCUSDT", "THYAO", "GDX")
        exchange: Exchange (NASDAQ, NYSE, AMEX, NYSEARCA, PCX, BINANCE, KUCOIN, MEXC, BIST, EGX, TWSE, TPEX)
        timeframe: Analysis timeframe (5m, 15m, 1h, 4h, 1D, 1W)
    """
    tech = coin_analysis(symbol, exchange, timeframe)
    cat = "crypto" if exchange.upper() in ["BINANCE", "KUCOIN", "BYBIT", "MEXC"] else "stocks"
    sentiment = analyze_sentiment(symbol, category=cat)
    news = fetch_news_summary(symbol, category=cat, limit=5)

    tech_momentum = tech.get("market_sentiment", {}).get("momentum", "") if isinstance(tech, dict) else ""
    tech_bullish = tech_momentum == "Bullish"
    sent_bullish = sentiment.get("sentiment_score", 0) > 0.1
    signals_agree = tech_bullish == sent_bullish
    confidence = "HIGH" if signals_agree else "MIXED"
    tech_signal = tech.get("market_sentiment", {}).get("buy_sell_signal", "N/A") if isinstance(tech, dict) else "N/A"

    return {
        "symbol": symbol,
        "exchange": exchange,
        "timeframe": timeframe,
        "technical": tech,
        "sentiment": sentiment,
        "news": {"count": news.get("count", 0), "latest": news.get("items", [])[:3]},
        "confluence": {
            "signals_agree": signals_agree,
            "confidence": confidence,
            "recommendation": (
                f"Technical {tech_signal} "
                f"{'confirmed by' if signals_agree else 'conflicts with'} "
                f"{sentiment.get('sentiment_label', 'Neutral')} Reddit sentiment "
                f"({sentiment.get('posts_analyzed', 0)} posts analyzed)"
            ),
        },
    }


# ── Backtest tools ─────────────────────────────────────────────────────────────

@mcp.tool()
def backtest_strategy(
    symbol: str,
    strategy: str,
    period: str = "1y",
    initial_capital: float = 10000.0,
    commission_pct: float = 0.1,
    slippage_pct: float = 0.05,
    interval: str = "1d",
    include_trade_log: bool = False,
    include_equity_curve: bool = False,
) -> dict:
    """Backtest a trading strategy on historical data with institutional-grade metrics.

    Args:
        symbol: Yahoo Finance symbol (AAPL, BTC-USD, THYAO.IS, ^GSPC)
        strategy: rsi | bollinger | macd | ema_cross | supertrend | donchian
        period: '1mo', '3mo', '6mo', '1y', '2y'
        initial_capital: Starting capital in USD (default $10,000)
        commission_pct: Per-trade commission % (default 0.1%)
        slippage_pct: Per-trade slippage % (default 0.05%)
        interval: '1d' (daily) or '1h' (hourly)
        include_trade_log: Include full per-trade log (default False)
        include_equity_curve: Include equity curve data points (default False)
    """
    return run_backtest(
        symbol, strategy, period, initial_capital,
        commission_pct, slippage_pct, interval,
        include_trade_log, include_equity_curve,
    )


@mcp.tool()
def compare_strategies(
    symbol: str,
    period: str = "1y",
    initial_capital: float = 10000.0,
    interval: str = "1d",
) -> dict:
    """Run all 6 strategies (RSI, Bollinger, MACD, EMA Cross, Supertrend, Donchian) and return a ranked leaderboard.

    Args:
        symbol: Yahoo Finance symbol (AAPL, BTC-USD, SPY…)
        period: '1mo', '3mo', '6mo', '1y', '2y'
        initial_capital: Starting capital in USD (default $10,000)
        interval: '1d' (daily) or '1h' (hourly)
    """
    return _compare_strategies(symbol, period, initial_capital, interval=interval)


@mcp.tool()
def walk_forward_backtest_strategy(
    symbol: str,
    strategy: str,
    period: str = "2y",
    initial_capital: float = 10000.0,
    commission_pct: float = 0.1,
    slippage_pct: float = 0.05,
    n_splits: int = 3,
    train_ratio: float = 0.7,
    interval: str = "1d",
) -> dict:
    """Walk-forward backtest to detect overfitting — validates strategy on unseen data.

    Args:
        symbol: Yahoo Finance symbol (AAPL, BTC-USD, SPY…)
        strategy: rsi | bollinger | macd | ema_cross | supertrend | donchian
        period: '1mo', '3mo', '6mo', '1y', '2y' (recommend '2y')
        initial_capital: Starting capital per fold in USD (default $10,000)
        commission_pct: Per-trade commission % (default 0.1%)
        slippage_pct: Per-trade slippage % (default 0.05%)
        n_splits: Number of walk-forward folds (default 3, max 10)
        train_ratio: Fraction of each fold used for training (default 0.7)
        interval: '1d' (daily) or '1h' (hourly)
    """
    return walk_forward_backtest(
        symbol, strategy, period, initial_capital,
        commission_pct, slippage_pct, n_splits, train_ratio, interval,
    )


# ── Fundamental analysis tools ─────────────────────────────────────────────────

@mcp.tool()
def stock_fundamentals(symbol: str) -> dict:
    """Full fundamental analysis: valuation, profitability, growth, balance sheet, dividend.

    Pulls P/E, P/B, EPS, ROE, ROA, profit margins, revenue/earnings growth,
    debt/equity, free cash flow, dividend yield, and analyst targets from
    Yahoo Finance — then synthesises a fundamental verdict
    (STRONG_FUNDAMENTAL_BUY / FUNDAMENTAL_BUY / HOLD / SELL / STRONG_SELL)
    with bullish and bearish factor lists.

    Use this for ANY equity question that's not purely technical — "Is AAPL
    fairly valued?", "Is TSLA's growth slowing?", "How leveraged is META?".

    Args:
        symbol: Yahoo Finance ticker — AAPL, MSFT, TSLA, THYAO.IS, COMI.CA, 600519.SS, 2330.TW
    """
    return get_fundamentals(symbol)


@mcp.tool()
def compare_peers(symbols: list[str]) -> dict:
    """Side-by-side fundamental comparison across up to 8 tickers.

    Returns a row-per-symbol table of valuation/profitability/growth metrics
    plus per-metric leaders (cheapest P/E, highest ROE, lowest leverage, etc.).
    Useful for "is AAPL cheaper than its FAANG peers?" or "which BIST bank
    has the best fundamentals right now?".

    Args:
        symbols: List of Yahoo tickers, e.g. ["AAPL", "MSFT", "NVDA", "GOOG"]
                 BIST: ["GARAN.IS", "AKBNK.IS", "ISCTR.IS"]
    """
    if not symbols:
        return {"error": "provide at least one symbol"}
    return _compare_peers(symbols)


@mcp.tool()
def dividend_info(symbol: str) -> dict:
    """Income-focused view: yield, payout ratio, ex-dividend date, sustainability flags.

    For dividend investors who care about cash flow over capital appreciation.
    Grades the income (LOW/STANDARD/HIGH/ULTRA_HIGH) and flags unsustainable
    payouts (e.g. dividend exceeds free cash flow).

    Args:
        symbol: Yahoo Finance ticker — KO, JNJ, T, VZ, AAPL, etc.
    """
    return get_dividend_info(symbol)


# ── Risk & position sizing tools ───────────────────────────────────────────────

@mcp.tool()
def position_sizing(
    account_size: float,
    risk_pct: float,
    entry: float,
    stop: float,
) -> dict:
    """Calculate how many units to buy given account, max-risk %, and stop-loss.

    Implements the 1-2% rule: never risk more than X% of account on a single
    trade. Output includes unit count, total position value, exposure %,
    and warnings for over-concentration or unreasonable stop distances.

    Args:
        account_size: Total trading capital in dollars (e.g. 50000)
        risk_pct: Max % of account to lose if stop hits (typically 0.5-2)
        entry: Planned entry price
        stop: Planned stop-loss price (below entry for long, above for short)
    """
    return _position_size(account_size, risk_pct, entry, stop)


@mcp.tool()
def risk_reward_calc(entry: float, stop: float, target: float) -> dict:
    """R-multiple risk/reward analyzer for a planned trade.

    Returns the reward/risk ratio (R-multiple), a grade (EXCELLENT 3R+ /
    GOOD 2-3R / MARGINAL 1-2R / POOR <1R), and the breakeven win rate
    needed. Below 1R the trade is a structural negative-edge bet that no
    win rate can save.

    Args:
        entry: Entry price
        stop: Stop-loss price
        target: Take-profit / target price
    """
    return _risk_reward(entry, stop, target)


@mcp.tool()
def kelly_position_size(
    win_rate_pct: float,
    win_loss_ratio: float,
    capital: float = 10000.0,
    kelly_fraction: float = 0.5,
) -> dict:
    """Kelly Criterion optimal bet sizing based on historical win rate and avg win/loss.

    Full Kelly is mathematically optimal but emotionally brutal (50%+ drawdowns).
    Most pros use Half Kelly (default 0.5) or Quarter Kelly. Returns NEGATIVE_EDGE
    verdict if Kelly is non-positive — meaning the strategy has no edge and you
    shouldn't trade it at any size.

    Args:
        win_rate_pct: Historical win rate, e.g. 55 for 55%
        win_loss_ratio: Average win size / average loss size (e.g. 1.5)
        capital: Account size (default $10,000)
        kelly_fraction: Multiplier on full Kelly — 0.25 quarter, 0.5 half (default), 1.0 full
    """
    return _kelly_criterion(win_rate_pct, win_loss_ratio, capital, kelly_fraction)


@mcp.tool()
def correlation_matrix(symbols: list[str], period: str = "6mo") -> dict:
    """Pairwise correlation of daily returns across a portfolio.

    Diversification check: > 0.7 means assets move as one (no real diversification),
    < 0.3 means meaningfully diversified, < 0 means hedged. Flags notable pairs
    that warrant rebalancing.

    Args:
        symbols: Up to 8 Yahoo tickers — ["AAPL", "MSFT", "TSLA", "BTC-USD", "GLD"]
        period: '1mo' | '3mo' | '6mo' | '1y' | '2y' (default 6mo)
    """
    return _correlation_matrix(symbols, period)


@mcp.tool()
def value_at_risk_analysis(
    symbol: str,
    position_value: float,
    period: str = "6mo",
    confidence: float = 0.95,
    horizon_days: int = 1,
) -> dict:
    """Value at Risk for a single position — historical, parametric, and expected shortfall.

    Tells you the worst plausible loss on a position over a given horizon at a
    given confidence level. Historical VaR uses the empirical return distribution
    (no normality assumption), parametric assumes Normal returns. Expected
    Shortfall (CVaR) gives the average loss when things go beyond VaR.

    Args:
        symbol: Yahoo ticker — AAPL, BTC-USD, SPY, ^GSPC
        position_value: Current dollar value of the position
        period: History window — '3mo', '6mo', '1y', '2y' (default 6mo)
        confidence: 0.90, 0.95, 0.975, or 0.99 (default 0.95)
        horizon_days: Forward-looking loss horizon in days (default 1)
    """
    return _value_at_risk(symbol, position_value, period, confidence, horizon_days)


# ── Investment thesis (orchestration) ──────────────────────────────────────────

@mcp.tool()
def investment_thesis(
    symbol: str,
    exchange: str = "NASDAQ",
    timeframe: str = "1D",
    position_value: float = 0.0,
    include_news: bool = True,
    include_sentiment: bool = True,
) -> dict:
    """FULL investment-grade thesis: technical + fundamental + sentiment + news + macro + risk.

    The flagship analyst tool. Synthesizes every dimension into:
      - Bull case: bulleted reasons to be long
      - Bear case: bulleted reasons to be short / avoid
      - Catalysts: news + analyst targets that move the stock
      - Risks: macro headwinds, VaR exposure (if position_value given)
      - Price targets: analyst consensus + technical entry/stop/target
      - Verdict: STRONG_BUY / BUY / HOLD / SELL / STRONG_SELL
      - Conviction: HIGH (signals align) / MEDIUM (partial confluence) / LOW (mixed)

    Use this when the user asks "should I buy X?" or "give me a full report on Y".
    For pure technicals use combined_analysis or coin_analysis; for pure fundamentals
    use stock_fundamentals. This tool is the everything-at-once view.

    Args:
        symbol: Asset symbol — AAPL, BTCUSDT, THYAO, COMI, 600519
        exchange: Exchange — crypto: KUCOIN/BINANCE/MEXC; stocks: NASDAQ/NYSE/BIST/EGX/SSE/SZSE/TWSE
        timeframe: Technical TF — 1D recommended for investing, 4h/1h for swing trades
        position_value: Optional $ amount — if >0, adds VaR risk section sized to this
        include_news: Pull RSS news headlines (slower; default True)
        include_sentiment: Pull Reddit sentiment (slower; default True)
    """
    exchange = sanitize_exchange(exchange, "NASDAQ")
    timeframe = sanitize_timeframe(timeframe, "1D")
    pos_val = position_value if position_value and position_value > 0 else None
    return generate_investment_thesis(
        symbol=symbol,
        exchange=exchange,
        timeframe=timeframe,
        position_value=pos_val,
        include_news=include_news,
        include_sentiment=include_sentiment,
    )


# ── Yahoo Finance tools ────────────────────────────────────────────────────────

@mcp.tool()
def yahoo_price(symbol: str) -> dict:
    """Real-time price quote from Yahoo Finance for any stock, crypto, ETF or index.

    Args:
        symbol: Yahoo Finance symbol — e.g. AAPL, BTC-USD, SPY, ^GSPC, EURUSD=X, THYAO.IS
    """
    return get_price(normalize_yahoo_symbol(symbol))


@mcp.tool()
def market_snapshot() -> dict:
    """Global market overview: major indices, top crypto, FX rates, and key ETFs.
    Powered by Yahoo Finance.
    """
    return get_market_snapshot()


@mcp.tool()
def bitcoin_market_pulse() -> dict:
    """Single-call BTC macro context: price, dominance, total market cap + risk assessment.

    Use this WHENEVER analyzing any cryptocurrency (altcoin or BTC itself) to
    get the broader market frame in one shot. A SOL/ETH/whatever setup looks
    very different when BTC is dumping with rising dominance vs. when alts
    are leading. Calling this once gives Claude the macro context to provide
    Bitcoin-aware commentary alongside the per-coin analysis - without
    chaining 2-3 separate yahoo_price + manual reasoning calls.

    Returns:
      - bitcoin: price, 24h change %, volume, market cap
      - dominance: BTC and ETH market-cap share of total crypto
      - total_market: total crypto mcap + 24h change + active coin count
      - assessment: label (HIGH_RISK / ALT_RISK / ALT_FAVORABLE / OPPORTUNITY_WITH_CAUTION / NEUTRAL) + 1-paragraph reasoning
    """
    return get_bitcoin_market_pulse()


@mcp.tool()
def stock_extended_hours(symbol: str) -> dict:
    """Real-time pre-market and after-hours prices for a US stock symbol.

    Use this when the user asks about a stock outside the regular 9:30am-4pm
    ET session — earnings reactions, overnight news, "what is X doing in
    after-hours?", "how did Y open in pre-market?". Returns the most recent
    valid print from each session window (pre-market, regular, post-market)
    along with computed % changes vs. the previous close and the regular
    close, respectively.

    During the regular session, post_market will be null (no data yet).
    On weekends/holidays, returns whatever's most recent in each window.

    Args:
        symbol: US stock symbol — AAPL, NVDA, TSLA, SPY, ^GSPC, etc.

    Returns:
        - pre_market: {price, as_of_utc, change_vs_previous_close_pct} or null
        - regular: {price, as_of_utc, change_pct} (consolidated tape close)
        - post_market: {price, as_of_utc, change_vs_regular_close_pct} or null
        - previous_close, currency, exchange, market_state for context
    """
    return get_extended_hours_price(symbol)


# ── Resource ───────────────────────────────────────────────────────────────────

@mcp.resource("exchanges://list")
def exchanges_list() -> str:
    """List available exchanges from the coinlist directory."""
    try:
        current_dir = os.path.dirname(__file__)
        coinlist_dir = os.path.join(current_dir, "coinlist")
        if os.path.exists(coinlist_dir):
            exchanges = [
                f[:-4].upper()
                for f in os.listdir(coinlist_dir)
                if f.endswith(".txt")
            ]
            if exchanges:
                return f"Available exchanges: {', '.join(sorted(exchanges))}"
    except Exception:
        pass
    return "Common exchanges: KUCOIN, BINANCE, BYBIT, MEXC, BITGET, OKX, COINBASE, GATEIO, HUOBI, BITFINEX, KRAKEN, BITSTAMP, BIST, EGX, NASDAQ, TWSE, TPEX"


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="TradingView Screener MCP server")
    parser.add_argument(
        "transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        nargs="?",
        help="Transport (default stdio)",
    )
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    args = parser.parse_args()

    if os.environ.get("DEBUG_MCP"):
        import sys
        print(f"[DEBUG_MCP] pkg cwd={os.getcwd()} argv={sys.argv} file={__file__}", file=sys.stderr, flush=True)

    if args.transport == "stdio":
        mcp.run()
    else:
        try:
            mcp.settings.host = args.host
            mcp.settings.port = args.port
        except Exception:
            pass
        mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
