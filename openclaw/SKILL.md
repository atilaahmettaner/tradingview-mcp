---
name: tradingview-mcp
description: AI Trading Intelligence — live prices, 30+ technical indicators, backtesting (6 strategies), walk-forward overfitting detection, trade logs, equity curves, licensed news sentiment (Marketaux), and multi-market screener. Supports stocks, crypto, ETFs, indices, Turkish (BIST), and Egyptian (EGX) markets.
metadata: { "openclaw": { "emoji": "📈", "always": true, "homepage": "https://github.com/atilaahmettaner/tradingview-mcp" } }
---

# TradingView MCP — AI Trading Intelligence

You have a trading intelligence tool available via bash. **NEVER use `sessions_spawn` or ask for an agent ID for trading tasks.** Run commands directly.

Use this tool whenever users ask about:
- Stock, crypto, ETF, or index prices
- Technical analysis (RSI, MACD, Bollinger Bands, etc.)
- Backtesting trading strategies
- Market sentiment or news
- Screening for trading opportunities

## How to Run Trading Tools

Execute via bash using the wrapper script:
```bash
python3 ~/.openclaw/tools/trading.py <command> [args]
```

## Behavior Guidelines

1. **Run bash immediately.** For any trading/market question → execute the command directly, don't ask for clarification.
2. **Always combine signals.** For "should I buy X?" → run price + backtest + sentiment together.
3. **Qualify with timeframe.** Default to `1y` period and `1d` interval unless specified.
4. **Explain metrics briefly.** Sharpe (risk-adjusted return), Max Drawdown (worst loss), Profit Factor (wins/losses).
5. **Add a disclaimer** on all backtests: "⚠️ Past performance does not guarantee future results."
6. **Be concise on Telegram.** Use emoji, bullet lists — no walls of JSON.
7. **Detect language.** Reply in the same language the user writes in.

## Tool Quick Reference

### Prices & Market
| Intent | Tool |
|--------|------|
| "What is AAPL's price?" | `yahoo_price(symbol="AAPL")` |
| "Show me BTC and ETH prices" | `get_prices_bulk(symbols=["BTC-USD","ETH-USD"])` |
| "How are markets today?" | `market_snapshot()` |

### Technical Analysis
| Intent | Tool |
|--------|------|
| "Analyze AAPL technically" | `technical_analysis(symbol="AAPL", exchange="NASDAQ", screener="america", interval="1h")` |
| "What is the RSI for BTC?" | `calculate_rsi(symbol="BTC-USD", period="14")` |
| "Supertrend signal for AAPL?" | `calculate_supertrend(symbol="AAPL")` |

### Backtesting
| Intent | Tool |
|--------|------|
| "Backtest RSI strategy for 1 year" | `backtest_strategy(symbol="AAPL", strategy="rsi", period="1y")` |
| "Show me the full trade log" | `backtest_strategy(symbol="BTC-USD", strategy="supertrend", period="1y", include_trade_log=True)` |
| "Run hourly backtest" | `backtest_strategy(symbol="AAPL", strategy="bollinger", period="3mo", interval="1h")` |
| "Which strategy is best?" | `compare_strategies(symbol="BTC-USD", period="2y")` |
| "Is this strategy overfitted?" | `walk_forward_backtest_strategy(symbol="AAPL", strategy="rsi", period="2y", n_splits=3)` |

### Sentiment & News
| Intent | Tool |
|--------|------|
| "What is the news sentiment on BTC?" | `analyze_sentiment(symbol="BTC")` |
| "Latest news on AAPL" | `fetch_news_summary(symbol="AAPL")` |
| "Combine technical + sentiment" | `analyze_confluence(symbol="AAPL", exchange="NASDAQ")` |

### Screener
| Intent | Tool |
|--------|------|
| "Strong bullish stocks" | `screener_bullish(exchange="NASDAQ")` |
| "Find oversold stocks" | `screener_oversold(exchange="NASDAQ")` |
| "Scan Turkish BIST stocks" | `screener_bullish(exchange="BIST")` |
| "Egyptian Exchange stocks" | `egx_stock_screen()` |

## Example Response Formats

### Price Query (Telegram-friendly)
```
📊 AAPL — Apple Inc.
💵 Price: $189.42
📈 Change: +1.23% (+$2.30)
📅 52w High: $199.62 | Low: $164.08
🏦 Exchange: NASDAQ | Market: REGULAR
```

### Backtest Summary (Telegram-friendly)
```
🔬 AAPL — RSI Strategy (1Y daily)
────────────────────────────────
📊 Trades: 8 | Win Rate: 62.5%
💰 Return: +14.3% vs B&H: +21.2%
📉 Max Drawdown: -6.8%
⚡ Sharpe: 1.42 | Calmar: 2.10
🏆 Profit Factor: 2.31

⚠️ Past performance does not guarantee future results.
```

### Walk-Forward (Overfitting Check)
```
🧪 Walk-Forward: AAPL RSI (2Y, 3 folds)
────────────────────────────────────────
Robustness Score: 0.87 → ROBUST ✅
Train avg: +12.4% | Test avg: +10.8%

Fold 1: Train +18% → Test +15% (rob: 0.83)
Fold 2: Train +8%  → Test +7%  (rob: 0.88)
Fold 3: Train +11% → Test +10% (rob: 0.91)

✅ Strategy performs well out-of-sample.
```

## Supported Symbols

- **US Stocks:** AAPL, TSLA, NVDA, MSFT, GOOGL, META, AMZN
- **Crypto:** BTC-USD, ETH-USD, SOL-USD, BNB-USD, XRP-USD
- **ETFs:** SPY, QQQ, GLD, VTI, IWM
- **Indices:** ^GSPC (S&P500), ^IXIC (NASDAQ), ^DJI (Dow), ^VIX
- **Turkish (BIST):** THYAO.IS, SASA.IS, BIMAS.IS, KCHOL.IS, EKGYO.IS
- **Egyptian (EGX):** COMI.CA, HRHO.CA, EAST.CA
- **FX:** EURUSD=X, GBPUSD=X, JPYUSD=X, TRYUSD=X

## Strategies Available for Backtesting

| Strategy | Key | Best For |
|----------|-----|---------|
| RSI Mean Reversion | `rsi` | Ranging/sideways markets |
| Bollinger Band | `bollinger` | Mean reversion in volatile markets |
| MACD Crossover | `macd` | Trend following |
| EMA 20/50 Cross | `ema_cross` | Medium-term trends |
| Supertrend (ATR) | `supertrend` | Strong trending markets |
| Donchian Channel | `donchian` | Breakout / Turtle Trading |
