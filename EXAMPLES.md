# 📚 Usage Examples - TradingView MCP Server

This guide shows real-world examples of how to use the TradingView MCP Server with Claude Desktop.

## Market quote with web research (Python MCP client)

Use the optional [market research example](examples/market_research.py) to pair
`yahoo_price` with free web search and page fetching from
[Parallel Search MCP](https://docs.parallel.ai/integrations/mcp/search-mcp).
Search uses Fast mode, with no account or API key needed. Anonymous access is
rate limited and intended for light use.

From a source checkout with Python 3.10–3.13 and `uv` installed:

```bash
uv sync
uv run python examples/market_research.py AAPL "Apple latest earnings revenue"
```

The example starts the local TradingView server over stdio, calls `yahoo_price`,
then connects to `https://search.parallel.ai/mcp` over Streamable HTTP. It discovers
and calls `web_search`, then calls `web_fetch` for the first search result. All
Python dependencies are already declared in this project's `pyproject.toml`.
It prints JSON containing `quote`, `search` (URLs and excerpts), and `source`
(fetched excerpts, with any warnings or errors from the service).

Replace `AAPL` with a Yahoo Finance symbol and use a short, specific research
question that names the company or asset. This script collects source evidence;
it does not run a model or generate an investment recommendation. Review source
dates and relevance yourself. It exits with an error if a tool fails, search
returns no sources, or the selected page cannot be fetched. Requests have bounded
timeouts; if anonymous access is rate limited, wait before trying again.

## 🚀 Quick Start Examples

### Basic Market Screening

#### Find Top Gainers
```
💬 You: "Show me the top 5 crypto gainers on KuCoin in the last 15 minutes"

🤖 Claude: I'll find the top-performing cryptocurrencies for you.

[Uses: top_gainers(exchange="KUCOIN", timeframe="15m", limit=5)]

📈 Top 5 Crypto Gainers (KuCoin, 15m):

1. **ACEUSDT** - $2.34 (+8.75%)
   - Volume: 2.4M USDT
   - RSI: 72.3 (Overbought)

2. **SOLUSDT** - $145.67 (+6.23%)
   - Volume: 15.2M USDT  
   - RSI: 68.1 (Strong)

[... and so on]
```

#### Find Biggest Losers
```
💬 You: "Which cryptos are falling the most on Binance today?"

🤖 Claude: [Uses: top_losers(exchange="BINANCE", timeframe="1D", limit=10)]

📉 Biggest Crypto Losers (Binance, 24h):

1. **XRPUSDT** - $0.52 (-12.4%)
2. **ADAUSDT** - $0.38 (-9.8%)
3. **DOTUSDT** - $6.12 (-8.9%)
```

#### NYSE Stock Screening
```
💬 You: "Show me the top 5 gainers on NYSE today"

🤖 Claude: [Uses: top_gainers(exchange="NYSE", timeframe="1D", limit=5)]

📈 Top 5 NYSE Gainers (Daily):

1. **NYSE:IBM** - $293.87 (+5.2%)
   - Volume: 4.2M shares
   - RSI: 65.4 (Bullish)

2. **NYSE:GE** - $168.45 (+4.8%)
   - Volume: 8.7M shares
   - RSI: 62.1 (Strong)

[... and so on]
```

### Technical Analysis

#### Individual Coin Analysis
```
💬 You: "Give me a complete technical analysis of Bitcoin"

🤖 Claude: [Uses: coin_analysis(symbol="BTCUSDT", exchange="KUCOIN", timeframe="1D")]

📊 Bitcoin (BTCUSDT) Technical Analysis:

**Price Action:**
- Current Price: $42,750
- 24h Change: +3.2% (+$1,320)
- High: $43,100 | Low: $41,200

**Bollinger Bands:**
- Rating: +2 (BUY Signal)
- BBW: 0.0342 (Medium volatility)
- Position: Upper 50% of bands

**Technical Indicators:**
- RSI: 64.2 (Bullish momentum)
- MACD: Bullish crossover
- EMA50: $41,800 (Price above)
- EMA200: $39,500 (Strong uptrend)

**Trading Signal: BUY** 🟢
```

#### Bollinger Band Squeeze Detection
```
💬 You: "Find crypto coins ready for a breakout (tight Bollinger Bands)"

🤖 Claude: [Uses: bollinger_scan(exchange="KUCOIN", bbw_threshold=0.03, limit=10)]

🎯 Bollinger Band Squeeze Alert (BBW < 0.03):

**Ready for Breakout:**
1. **ETHUSDT** - BBW: 0.0287 ⚡
   - Price: $2,534 (Middle band)
   - Volume spike: +45%

2. **BNBUSDT** - BBW: 0.0295 ⚡
   - Price: $312 (Near upper band)
   - RSI: 58 (Neutral)

*Note: Low BBW indicates potential big price movement coming!*
```

## 🎯 Advanced Trading Strategies

### Multi-Timeframe Analysis
```
💬 You: "Compare Bitcoin's performance across different timeframes"

🤖 Claude: Let me analyze Bitcoin across multiple timeframes.

[Uses multiple calls with different timeframes]

📊 Bitcoin Multi-Timeframe Analysis:

**Short-term (15m):** +0.8% - Mild bullish
**Medium-term (1h):** +2.1% - Strong bullish  
**Daily (1D):** +3.2% - Very bullish
**Weekly (1W):** +12.5% - Extremely bullish

**Trend Alignment:** ✅ All timeframes bullish
**Signal Strength:** Strong BUY across all periods
```

### Pattern Recognition
```
💬 You: "Find coins showing consecutive bullish candle patterns"

🤖 Claude: [Uses: consecutive_candles_scan(pattern_type="bullish", timeframe="1h")]

🕯️ Consecutive Bullish Patterns Found:

**Strong Momentum Coins:**
1. **SOLUSDT** - 4 consecutive green candles (1h)
   - Total gain: +8.4%
   - Volume increasing

2. **AVAXUSDT** - 3 consecutive green candles (1h)  
   - Total gain: +5.2%
   - Breaking resistance

**Pattern Strength:** High - These show sustained buying pressure
```

## 🏢 Different Markets & Exchanges

### Traditional Stock Markets
```
💬 You: "How are Turkish stocks performing today? Show me BIST gainers"

🤖 Claude: [Uses: top_gainers(exchange="BIST", timeframe="1D")]

🇹🇷 BIST (Turkish Stock Market) Top Gainers:

1. **AKBNK** - ₺58.40 (+4.2%)
2. **THYAO** - ₺245.50 (+3.8%)  
3. **ISCTR** - ₺12.35 (+3.1%)

*Turkish market showing strong performance today!*
```

```
💬 You: "What about NASDAQ tech stocks?"

🤖 Claude: [Uses: top_gainers(exchange="NASDAQ", timeframe="1D")]

🇺🇸 NASDAQ Top Gainers Today:

1. **AAPL** - $175.30 (+2.1%)
2. **MSFT** - $378.45 (+1.8%)
3. **NVDA** - $721.50 (+3.4%)
```

### Cross-Exchange Comparison
```
💬 You: "Compare Bitcoin prices across different exchanges"

🤖 Claude: Let me check Bitcoin across multiple exchanges.

[Uses coin_analysis for different exchanges]

₿ Bitcoin Price Comparison:

**KuCoin:** $42,750 (Main reference)
**Binance:** $42,735 (-$15 spread)
**Bybit:** $42,760 (+$10 spread)

**Best Exchange:** Bybit (highest price)
**Arbitrage Opportunity:** Minimal ($25 spread)
```

## 🎨 Creative Analysis Requests

### Sentiment Analysis
```
💬 You: "What's the overall crypto market sentiment right now?"

🤖 Claude: [Uses: top_gainers + top_losers + bollinger_scan]

📊 Crypto Market Sentiment Analysis:

**Overall Mood:** 🟢 Bullish (65% coins positive)

**Market Indicators:**
- Gainers vs Losers: 347 vs 198 (Bullish ratio)
- Average RSI: 58.3 (Healthy momentum)
- Bollinger Breakouts: 23 coins (High activity)
- Volume: +15% above average

**Interpretation:** Market showing strong bullish sentiment with healthy participation.
```

### Sector Rotation Analysis  
```
💬 You: "Which crypto sectors are hot right now?"

🤖 Claude: [Analyzes different crypto categories]

🔥 Hot Crypto Sectors:

**DeFi Tokens:** 🚀🚀🚀
- UNIUSDT: +12.4%
- AAVEUSDT: +8.9%
- COMPUSDT: +7.2%

**Layer 1s:** 🚀🚀
- SOLUSDT: +6.3%
- AVAXUSDT: +5.1%
- DOTUSDT: +3.8%

**Meme Coins:** 🚀
- DOGEUSDT: +4.2%
- SHIBUSDT: +2.9%

**Strongest Sector:** DeFi leading the rally!
```

## 🛠️ Troubleshooting Examples

### When Data Isn't Available
```
💬 You: "Show me Ethereum analysis"

🤖 Claude: [Tries coin_analysis but gets error]

I encountered an issue accessing Ethereum data. Let me try a different approach.

[Switches to different exchange or timeframe]

Found the data! Here's your Ethereum analysis...
```

### Handling Rate Limits
```
💬 You: "Give me analysis for 20 different coins"

🤖 Claude: I'll analyze these coins for you, but I'll pace the requests to avoid rate limits.

[Processes in batches]

📊 Analysis Results (Processing 5 at a time):

**Batch 1 Complete:** BTC, ETH, BNB, ADA, SOL
**Batch 2 Complete:** AVAX, DOT, MATIC, LINK, UNI
...
```

## 📈 Real Trading Scenarios

### Day Trading Setup
```
💬 You: "I'm day trading. Find me volatile coins with good volume on 15-minute charts"

🤖 Claude: Perfect for day trading! Let me find high-volume, volatile opportunities.

[Uses: bollinger_scan + volume filtering]

⚡ Day Trading Opportunities (15m):

**High Volatility + Volume:**
1. **BTCUSDT** - BBW: 0.045, Volume: 890M
2. **ETHUSDT** - BBW: 0.052, Volume: 456M  
3. **SOLUSDT** - BBW: 0.038, Volume: 123M

**Best Setup:** SOLUSDT - Tight bands + volume spike = breakout imminent
```

### Swing Trading
```
💬 You: "Find me coins in oversold territory for swing trades"

🤖 Claude: [Uses: rating_filter(rating=-2) + RSI analysis]

📉➡️📈 Swing Trading Opportunities:

**Oversold But Quality:**
1. **ADAUSDT** - Rating: -2, RSI: 28 (Oversold)
   - Near strong support at $0.35
   - Good risk/reward setup

2. **DOTUSDT** - Rating: -2, RSI: 31 (Oversold)
   - Bouncing off $5.80 support
   - Potential 15-20% upside

**Strategy:** Buy oversold quality projects near support
```

### Risk Management
```
💬 You: "Help me assess the risk of my current crypto positions"

🤖 Claude: [Analyzes portfolio coins individually]

⚠️ Portfolio Risk Assessment:

**High Risk:**
- ACEUSDT: RSI 78 (Extremely overbought)
- Recommendation: Take profits

**Medium Risk:**  
- BTCUSDT: RSI 64 (Strong but manageable)
- Recommendation: Hold with stop loss

**Low Risk:**
- ETHUSDT: RSI 52 (Neutral territory)  
- Recommendation: Safe to hold

**Overall Portfolio Risk:** Medium-High
**Suggestion:** Reduce exposure in overbought positions
```

## 🎯 Pro Tips for Best Results

### Effective Prompting
```
✅ Good: "Find oversold crypto with RSI below 30 on KuCoin"
❌ Avoid: "Find good crypto"

✅ Good: "Compare Bitcoin 15m vs 1h trends"  
❌ Avoid: "How is Bitcoin?"

✅ Good: "Show BIST stocks with Bollinger squeeze"
❌ Avoid: "Turkish stocks analysis"
```

### Combining Multiple Tools
```
💬 You: "Give me a complete market overview"

🤖 Claude: [Combines multiple tool calls]

🌍 Complete Crypto Market Overview:

**Market Leaders (Gainers):** [top_gainers results]
**Market Laggards (Losers):** [top_losers results]  
**Breakout Candidates:** [bollinger_scan results]
**Individual Spotlight:** [coin_analysis for BTC]

**Market Summary:** Bullish sentiment with healthy rotation
```

---

## 🎓 Learning Resources

Want to understand the technical indicators better?

- **Bollinger Bands:** Measure volatility and potential breakouts
- **RSI:** Shows overbought (>70) vs oversold (<30) conditions  
- **MACD:** Reveals trend changes and momentum shifts
- **Volume:** Confirms the strength of price movements

**Remember:** This tool provides data and analysis, but always do your own research and risk management!

---

**Happy Trading! May your analysis be sharp and your profits be green! 📈✨**
