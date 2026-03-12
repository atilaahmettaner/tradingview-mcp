# 📈 TradingView MCP Server

A powerful Model Context Protocol (MCP) server that provides advanced cryptocurrency and stock market analysis using TradingView data. Perfect for traders, analysts, and AI assistants who need real-time market intelligence.

## 🎥 Demo Video

> **Quick 19-second demo showing the MCP server in action**
> 

https://github-production-user-asset-6210df.s3.amazonaws.com/67838093/478689497-4a605d98-43e8-49a6-8d3a-559315f6c01d.mp4?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAVCODYLSA53PQK4ZA%2F20250816%2Fus-east-1%2Fs3%2Faws4_request&X-Amz-Date=20250816T155717Z&X-Amz-Expires=300&X-Amz-Signature=1362a9ea0e886268315cfa5b63951c82929ea01c9d826c87060e3ac116cf9531&X-Amz-SignedHeaders=host

## ✨ Key Features

- 🚀 **Real-time Market Screening**: Find top gainers, losers, and trending stocks/crypto
- 📊 **Advanced Technical Analysis**: Bollinger Bands, RSI, MACD, and more indicators  
- 🎯 **Bollinger Band Intelligence**: Proprietary rating system (-3 to +3) for squeeze detection
- 🕯️ **Pattern Recognition**: Detect consecutive bullish/bearish candle formations
- 💎 **Multi-Market Support**: Crypto exchanges (KuCoin, Binance, Bybit) + Traditional markets (NASDAQ, BIST)
- ⏰ **Multi-Timeframe Analysis**: From 5-minute to monthly charts
- 🔍 **Individual Asset Deep-Dive**: Comprehensive technical analysis for any symbol

## 🚀 Quick Start

### Option 1: Claude Desktop (Recommended)

1. **Install UV Package Manager:**
   ```bash
   # macOS (Homebrew)
   brew install uv
   
   # Windows
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   
   # macOS/Linux (Direct)
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Add to Claude Desktop Configuration:**
   
   **Config Path:**
   - **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
   - **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
   
   ```json
   {
     "mcpServers": {
       "tradingview-mcp": {
         "command": "uv",
         "args": [
           "tool", "run", "--from",
           "git+https://github.com/atilaahmettaner/tradingview-mcp.git",
           "tradingview-mcp"
         ]
       }
     }
   }
   ```

3. **Restart Claude Desktop** - The server will be automatically available!

📋 **For detailed Windows instructions, see [INSTALLATION.md](INSTALLATION.md)**

### Option 2: Manual Installation

```bash
# Clone the repository
git clone https://github.com/atilaahmettaner/tradingview-mcp.git
cd tradingview-mcp

# Install dependencies
uv sync

# For local development, add to Claude Desktop:
```

**Windows Configuration Path:**
`%APPDATA%\Claude\claude_desktop_config.json`

**macOS Configuration Path:**
`~/Library/Application Support/Claude/claude_desktop_config.json`

**Configuration for Local Setup:**
```json
{
  "mcpServers": {
    "tradingview-mcp-local": {
      "command": "C:\\path\\to\\your\\tradingview-mcp\\.venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\your\\tradingview-mcp\\src\\tradingview_mcp\\server.py"],
      "cwd": "C:\\path\\to\\your\\tradingview-mcp"
    }
  }
}
```

**macOS/Linux Configuration:**
```json
{
  "mcpServers": {
    "tradingview-mcp-local": {
      "command": "uv",
      "args": ["run", "python", "src/tradingview_mcp/server.py"],
      "cwd": "/path/to/your/tradingview-mcp"
    }
  }
}
```

### Option 3: Connect to Deployed Cloud Server (Fastest)

If the server is already deployed on Render, just add this to your Claude Desktop config — no installation needed.

**Config file location:**
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

**Without API key:**
```json
{
  "mcpServers": {
    "tradingview-mcp": {
      "type": "streamable-http",
      "url": "https://tradingview-mcp-1gbt.onrender.com/mcp"
    }
  }
}
```

**With API key (if you set one in Render):**
```json
{
  "mcpServers": {
    "tradingview-mcp": {
      "type": "streamable-http",
      "url": "https://tradingview-mcp-1gbt.onrender.com/mcp",
      "headers": {
        "Authorization": "Bearer your-api-key"
      }
    }
  }
}
```

Then **restart Claude Desktop** — the TradingView tools will appear automatically.

> **Note:** Render's free tier sleeps after 15 min of inactivity. The first request after idle takes ~30s to wake up.

> **Mobile (iPhone):** Claude's iOS app does not currently support MCP servers. This is a Claude Desktop feature only.

---

### Option 4: One-Click Deploy to Render (No Terminal Needed)

Deploy the MCP server to the cloud directly from your browser — no CLI, no terminal, works on iPhone.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/hortonwill1-cloud/tradingview-mcp)

**Steps:**
1. Tap the button above → sign in with GitHub
2. Render auto-detects the config from `render.yaml`
3. Enter your `API_KEY` when prompted (generate one with any random string)
4. Tap **"Apply"** — deployment starts automatically

**After deploy**, use the server URL in your MCP client config:
```json
{
  "mcpServers": {
    "tradingview-mcp": {
      "type": "streamable-http",
      "url": "https://your-app-name.onrender.com/mcp",
      "headers": { "Authorization": "Bearer your-api-key" }
    }
  }
}
```

> **Note:** Render's free tier spins down after 15 minutes of inactivity (first request takes ~30s to wake up). Upgrade to a paid plan to keep it always-on.

## 🛠️ Available Tools

### 📈 Market Screening
| Tool | Description | Example Usage |
|------|-------------|---------------|
| `top_gainers` | Find highest performing assets | Top crypto gainers in 15m |
| `top_losers` | Find biggest declining assets | Worst performing stocks today |
| `bollinger_scan` | Find assets with tight Bollinger Bands | Coins ready for breakout |
| `rating_filter` | Filter by Bollinger Band rating | Strong buy signals (rating +2) |
| `volume_breakout_scanner` | Detect volume + price breakouts | High-volume movers |
| `smart_volume_scanner` | Volume + RSI combination scanner | Smart entry opportunities |
| `rsi_scanner` | Scan for overbought/oversold conditions | Oversold coins on 1h |
| `trend_scanner` | Find strongly trending assets via ADX | Bullish trending coins on 4h |

### 🔍 Technical Analysis
| Tool | Description | Example Usage |
|------|-------------|---------------|
| `coin_analysis` | Complete technical analysis | Analyze BTC with all indicators |
| `consecutive_candles_scan` | Find candlestick patterns | 3+ consecutive green candles |
| `advanced_candle_pattern` | Multi-timeframe pattern analysis | Complex pattern detection |
| `multi_timeframe_summary` | Signal summary across 15m/1h/4h/1D | Quick BTC multi-TF overview |
| `volume_confirmation_analysis` | Volume confirmation for a symbol | Confirm ETH breakout volume |

### 📋 Information
| Tool | Description |
|------|-------------|
| `exchanges://list` | List all supported exchanges and markets |

## 📝 Usage Examples

### Talk to Claude Like This:

**Basic Market Screening:**
```
"Show me the top 10 crypto gainers on KuCoin in the last 15 minutes"
"Find the biggest losers on Binance today"  
"Which Turkish stocks (BIST) are down more than 5% today?"
```

**Technical Analysis:**
```
"Analyze Bitcoin with all technical indicators"
"Find crypto coins with Bollinger Band squeeze (BBW < 0.05)"
"Show me coins with strong buy signals (rating +2)"
"Analyze IBM stock on NYSE with technical indicators"
```

**Pattern Recognition:**
```
"Find coins with 3 consecutive bullish candles on Bybit"
"Scan for stocks showing growing candle patterns"
"Which assets have tight Bollinger Bands ready for breakout?"
```

**RSI & Trend Analysis:**
```
"Find oversold coins on KuCoin (1h timeframe)"
"Show me overbought Binance coins on the daily chart"
"Scan for strongly trending Bybit coins on 4h"
"Find bullish-trending crypto with ADX above 40"
```

**Multi-Timeframe Overview:**
```
"Give me a multi-timeframe summary for BTCUSDT"
"What do the 15m, 1h, 4h and daily signals say for ETH?"
"Is SOLUSDT bullish or bearish across all timeframes?"
```

**Advanced Queries:**
```
"Compare AAPL vs TSLA technical indicators"
"Find high-volume crypto with RSI below 30"
"Show me NASDAQ stocks with strong momentum"
"Find NYSE stocks with Bollinger Band squeeze"
```

## 🎯 Understanding the Bollinger Band Rating System

Our proprietary rating system helps identify trading opportunities:

| Rating | Signal | Description |
|--------|---------|-------------|
| **+3** | 🔥 Strong Buy | Price above upper Bollinger Band |
| **+2** | ✅ Buy | Price in upper 50% of bands |
| **+1** | ⬆️ Weak Buy | Price above middle line |
| **0** | ➡️ Neutral | Price at middle line |
| **-1** | ⬇️ Weak Sell | Price below middle line |
| **-2** | ❌ Sell | Price in lower 50% of bands |
| **-3** | 🔥 Strong Sell | Price below lower Bollinger Band |

**Bollinger Band Width (BBW)**: Lower values indicate tighter bands → potential breakout coming!

## 🏢 Supported Markets & Exchanges

### 💰 Cryptocurrency Exchanges
- **KuCoin** (KUCOIN) - Primary recommendation
- **Binance** (BINANCE) - Largest crypto exchange  
- **Bybit** (BYBIT) - Derivatives focused
- **Bitget** (BITGET) - Fast-growing global exchange
- **OKX** (OKX) - Global crypto exchange
- **Coinbase** (COINBASE) - US-regulated exchange
- **Gate.io** (GATEIO) - Altcoin specialist
- **Huobi** (HUOBI) - Asian market leader
- **Bitfinex** (BITFINEX) - Professional trading

### 📊 Traditional Markets
- **NASDAQ** (NASDAQ) - US tech stocks (AAPL, MSFT, TSLA)
- **NYSE** (NYSE) - New York Stock Exchange (IBM, GE, JPM)
- **BIST** (BIST) - Turkish stock market (Borsa İstanbul)
- More markets coming soon!

### ⏰ Supported Timeframes
`5m`, `15m`, `1h`, `4h`, `1D`, `1W`, `1M`

## 📊 Technical Indicators Included

- **Bollinger Bands** (20, 2) - Volatility and squeeze detection
- **RSI** (14) - Momentum oscillator  
- **Moving Averages** - SMA20, EMA50, EMA200
- **MACD** - Trend and momentum
- **ADX** - Trend strength measurement
- **Stochastic** - Overbought/oversold conditions
- **Volume Analysis** - Market participation
- **Price Action** - OHLC data with percentage changes

## 🚨 Troubleshooting

### Common Issues:

**1. "No data found" errors:**
- Try different exchanges (KuCoin usually works best)
- Use standard timeframes (15m, 1h, 1D)
- Check symbol format (e.g., "BTCUSDT" not "BTC")

**2. Empty arrays or rate limiting:**
- If you get empty results, you may have hit TradingView's rate limits
- Wait 5-10 minutes between query sessions
- The server automatically handles retries
- KuCoin and BIST have the most reliable data

**3. Claude Desktop not detecting the server:**
- Restart Claude Desktop after adding configuration
- Check that UV is installed: `uv --version`
- Verify the configuration JSON syntax

**4. Slow responses:**
- First request may be slower (warming up)
- Subsequent requests are much faster
- Consider using smaller limits (5-10 items)

## 🔧 Development & Customization

### Running in Development Mode:
```bash
# Clone and setup
git clone https://github.com/atilaahmettaner/tradingview-mcp.git
cd tradingview-mcp
uv sync

# Run with MCP Inspector for debugging
uv run mcp dev src/tradingview_mcp/server.py

# Test individual functions
uv run python test_api.py
```

### Adding New Exchanges:
The server is designed to be easily extensible. Check `src/tradingview_mcp/core/` for the modular architecture.

## 🤝 Contributing

We welcome contributions! Here's how:

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

### Ideas for Contributions:
- Add new exchanges or markets
- Implement additional technical indicators  
- Improve error handling and rate limiting
- Add more candlestick pattern recognition
- Create comprehensive test suite

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🐛 Support & Issues

- **Report bugs**: [GitHub Issues](https://github.com/atilaahmettaner/tradingview-mcp/issues)
- **Feature requests**: Open an issue with the "enhancement" label
- **Questions**: Check existing issues or open a new discussion

## 🌟 Star This Project

If you find this MCP server useful, please ⭐ star the repository to help others discover it!

---

**Built with ❤️ for traders and AI enthusiasts**

*Empowering intelligent trading decisions through advanced market analysis*
