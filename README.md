# 📈 AI Trading Intelligence Framework — MCP Server

<a href="https://trendshift.io/repositories/25110" target="_blank"><img src="https://trendshift.io/api/badge/repositories/25110" alt="atilaahmettaner%2Ftradingview-mcp | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>

**The most complete AI-powered trading toolkit for Claude and MCP clients.**
Backtesting + Live Sentiment + Yahoo Finance + 30+ Technical Analysis Tools — all in one MCP server.

> [!IMPORTANT]
> **Not financial advice.** Nothing produced by this software is investment, financial, legal, tax, or accounting advice. tradingview-mcp is an informational and educational analysis tool. Its outputs, including indicators, scores, signals, "trade setups", entries, stop losses, and targets, are computed from third party market data and are **not** recommendations to buy, sell, or hold any asset. It does not execute trades, manage money, or guarantee any result. Trading and investing carry a substantial risk of loss, and you can lose some or all of your capital. Always do your own research and consult a licensed professional before making any financial decision. You are solely responsible for your own decisions and for complying with the laws and regulations that apply to you. Market data may be delayed, inaccurate, or incomplete, and is provided without warranty.

> [!TIP]
> **Skip the setup. Use the hosted version.** [**pro.cryptosieve.com**](https://pro.cryptosieve.com) gives you all 30+ tools as one connector URL for Claude.ai, ChatGPT, Copilot, and Cursor. No `uv`, `pandas`, or Python to wrangle. **$9 per month, with a 3 day free trial.** Self hosting stays free forever; the hosted plan is just for folks who would rather skip the ops.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP Ready](https://img.shields.io/badge/MCP-Ready-brightgreen)](https://modelcontextprotocol.com/)
[![OpenClaw Ready](https://img.shields.io/badge/OpenClaw-Ready-blueviolet)](https://openclaw.ai)
[![Version](https://img.shields.io/badge/version-v0.7.0-blue)](https://github.com/atilaahmettaner/tradingview-mcp/releases)
[![PyPI](https://img.shields.io/badge/PyPI-tradingview--mcp--server-orange)](https://pypi.org/project/tradingview-mcp-server/)
[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-❤️-pink?logo=github-sponsors)](https://github.com/sponsors/atilaahmettaner)

> **⭐ If this tool improves your workflow, please star the repo and consider [sponsoring](https://github.com/sponsors/atilaahmettaner) — it keeps the project alive and growing!**

<a href="https://github.com/sponsors/atilaahmettaner">
  <img src="https://img.shields.io/badge/☕_Coffee_($5)-Sponsor-orange?style=for-the-badge&logo=github-sponsors" alt="Sponsor $5"/>
</a>
<a href="https://github.com/sponsors/atilaahmettaner">
  <img src="https://img.shields.io/badge/🚀_Supporter_($15)-Sponsor-blueviolet?style=for-the-badge&logo=github-sponsors" alt="Sponsor $15"/>
</a>
<a href="https://github.com/sponsors/atilaahmettaner">
  <img src="https://img.shields.io/badge/💎_Pro_($30)-Sponsor-gold?style=for-the-badge&logo=github-sponsors" alt="Sponsor $30"/>
</a>

---

## 🎥 Framework Demo

https://github-production-user-asset-6210df.s3.amazonaws.com/67838093/478689497-4a605d98-43e8-49a6-8d3a-559315f6c01d.mp4

---

## 🆕 What's New

**Stability & Strategy Expansion (May 2026)**

- **9 backtest strategies** (up from 6) — added `rsi_pullback`, `keltner_breakout`, and `triple_ema`, covering trend-pullback, ATR-normalized breakout, and SMA200-filtered EMA cross edges. `compare_strategies` now ranks the full 9.
- **Generic per-tool TTL cache** — `yahoo_price`, `extended_hours`, `financial_news`, `sentiment`, and both options tools no longer re-issue HTTP on every call. Per-tool TTLs are env-tunable (`CACHE_TTL_YAHOO_PRICE`, `CACHE_TTL_NEWS`, etc. — see [Caching & throttle env vars](#caching--throttle-env-vars)). Error responses are not cached, so transient upstream failures aren't memoized. *(PR [#43](https://github.com/atilaahmettaner/tradingview-mcp/pull/43) — open)*
- **Resilience layer** — automatic retry + 60-second TTL cache on the TradingView screener provider, eliminating transient `"Expecting value"` errors on `combined_analysis` and `multi_timeframe_analysis`. *(PR [#32](https://github.com/atilaahmettaner/tradingview-mcp/pull/32) — merged)*
- **Financial news service rebuild** — replaces deprecated Reuters RSS endpoints with Yahoo Finance, MarketWatch, and CNBC. Fixes the long-standing `count: 0` bug on `financial_news`. *(PR [#33](https://github.com/atilaahmettaner/tradingview-mcp/pull/33) — merged)*
- **TA throttle** — caps concurrent `tradingview_ta` calls (default 4) + min 0.8s spacing between starts. Prevents parallel bursts of `combined_analysis` / `multi_timeframe_analysis` from hitting TradingView's empty-body rate-limit cliff. Tunable via env vars. *(PR [#34](https://github.com/atilaahmettaner/tradingview-mcp/pull/34) — merged)*
- **Walk-forward backtesting** (`walk_forward_backtest_strategy`) — train/test split with overfitting verdict (ROBUST / MODERATE / WEAK / OVERFITTED).
- **Hourly (1h) timeframe** support across `backtest_strategy`, `compare_strategies`, and `walk_forward_backtest_strategy`.
- **Full trade log + equity curve** outputs (`include_trade_log=True`, `include_equity_curve=True`).

---

## 🏗️ Architecture

![tradingview-mcp Architecture](assets/architecture.png)

---

## ✨ Why tradingview-mcp?

| Feature | `tradingview-mcp` | Traditional Setups | Bloomberg Terminal |
|---------|-------------------|--------------------|--------------------|
| **Setup Time** | 5 minutes | Hours (Docker, Conda...) | Weeks (Contracts) |
| **Cost** | Free & Open Source | Variable | $30k+/year |
| **Backtesting** | ✅ 9 strategies + Walk-forward + Sharpe | ❌ Manual scripting | ✅ Proprietary |
| **Live Sentiment** | ✅ Reddit + RSS news | ❌ Separate setup | ✅ Terminal |
| **Market Data** | ✅ Live / Real-Time | Historical / Delayed | Live |
| **API Keys** | **None required** | Multiple (OpenAI, etc.) | N/A |

---

## 🚀 Quick Start (5 Minutes)

### Install via pip
```bash
pip install tradingview-mcp-server
```

### Claude Desktop Config (`claude_desktop_config.json`)

> **Note:** On macOS, GUI apps like Claude Desktop may not have `~/.local/bin` in their PATH. Use the full path to `uvx` to avoid "command not found" errors.

```json
{
  "mcpServers": {
    "tradingview": {
      "command": "/Users/YOUR_USERNAME/.local/bin/uvx",
      "args": ["--from", "tradingview-mcp-server", "tradingview-mcp"]
    }
  }
}
```

On Linux, replace `/Users/YOUR_USERNAME` with `/home/YOUR_USERNAME`. On Windows, use `%USERPROFILE%\.local\bin\uvx.exe`.

### Codex Plugin Config

This repository also includes mcp-only Codex plugin metadata:

- `.codex-plugin/plugin.json`
- `.codex-mcp.json`

The plugin uses the same PyPI package entrypoint:

```json
{
  "mcpServers": {
    "tradingview": {
      "command": "uvx",
      "args": ["--from", "tradingview-mcp-server", "tradingview-mcp"]
    }
  }
}
```

After installing or enabling the Codex plugin, restart Codex so the MCP server is loaded in the next session. Depending on your Codex version, `codex mcp list` may show registered MCP servers, but tool availability should be verified in a fresh Codex session.

### Or run from source
```bash
git clone https://github.com/atilaahmettaner/tradingview-mcp
cd tradingview-mcp
uv run tradingview-mcp
```

---

## 🛠️ Troubleshooting

### 🪟 Windows: `MCP error -32001: Request timed out` on first launch

Symptom — you see this in the Claude Desktop logs shortly after adding the config:

```
[tradingview] Server started and connected successfully
[tradingview] Message from client: initialize ...
[60 seconds later]
[tradingview] notifications/cancelled — reason: "MCP error -32001: Request timed out"
```

**Why it happens:** on Windows with Python 3.14, `uvx` downloads `tradingview-mcp-server`, creates a fresh virtualenv, and installs dependencies the first time it runs. Because `pandas` has no prebuilt wheel for Python 3.14 yet, pip falls back to a source build — which typically exceeds Claude Desktop's 60-second MCP initialization timeout.

**Fix — pin to Python 3.13 (has prebuilt pandas wheels):**

```json
{
  "mcpServers": {
    "tradingview": {
      "command": "uvx",
      "args": ["--python", "3.13", "--from", "tradingview-mcp-server", "tradingview-mcp"]
    }
  }
}
```

On macOS use the full path to `uvx` (see the note in Quick Start). On Windows `uvx` is typically `%USERPROFILE%\.local\bin\uvx.exe`.

**Alternative — pre-install once, then let Claude Desktop reuse the cache:**

```bash
# Run in a terminal before launching Claude Desktop
uv tool install --python 3.13 tradingview-mcp-server
```

After the install finishes, start Claude Desktop with the normal config and the server will come up instantly (cache is already warm).

> _Credit: [@wyh4444](https://github.com/wyh4444) for the original report in [#24](https://github.com/atilaahmettaner/tradingview-mcp/issues/24)._

---

## ⚠️ Error Envelope Format

Tools that have adopted the structured error format return either their normal payload **or** an error envelope:

```json
{"error": {"code": "ALL_BATCHES_FAILED", "message": "All 5 batches failed; first error: JSONDecodeError(...)", "batches_attempted": 5, "batches_failed": 5, "first_error": "..."}}
```

**Why:** the previous `[]` / `{"error": "Analysis failed: ..."}` strings made it impossible to distinguish "no matches today" from "upstream rate-limit cliff." The new envelope is programmatically branchable by `code`.

**Currently adopted by:** `top_gainers`, `top_losers`, `rating_filter`, `volume_breakout_scanner`, `smart_volume_scanner`. More tools will follow in subsequent PRs.

**Detecting an error:**

```python
result = volume_breakout_scanner(exchange="KUCOIN")
if isinstance(result, dict) and "error" in result:
    code = result["error"]["code"]
    if code == "ALL_BATCHES_FAILED":
        # Wait + retry, raise alert, fall back to single-batch call, etc.
        ...
else:
    for row in result:
        ...
```

Stable codes are defined in [`core/errors.py`](src/tradingview_mcp/core/errors.py).

---

## ⚙️ Caching & throttle env vars

All env vars are optional — sensible defaults apply when unset. Set any cache TTL to `0` to disable that tool's cache at runtime.

**Per-tool TTL cache** (`@cached` decorator, in seconds):

| Env var | Default | Tool |
| --- | --- | --- |
| `CACHE_TTL_YAHOO_PRICE` | 30 | `yahoo_price` |
| `CACHE_TTL_EXTENDED_HOURS` | 30 | `stock_extended_hours` |
| `CACHE_TTL_OPTIONS_CHAIN` | 60 | `stock_options_chain` |
| `CACHE_TTL_OPTIONS_UNUSUAL` | 60 | `stock_options_unusual_activity` |
| `CACHE_TTL_NEWS` | 300 | `financial_news` |
| `CACHE_TTL_SENTIMENT` | 300 | `analyze_sentiment` |

Error responses (`{"error": ...}` envelopes) are **not** cached, so transient upstream failures don't get memoized for the TTL window.

**Screener resilience layer** (shared by `combined_analysis`, `multi_timeframe_analysis`, EGX/scanner tools):

| Env var | Default | Purpose |
| --- | --- | --- |
| `TRADINGVIEW_MCP_CACHE_TTL` | 60 | TTL for the screener provider's shared cache (seconds) |
| `TRADINGVIEW_MCP_RETRY_DELAYS` | `0.5,1.5,4.0` | Comma-separated backoff between retries on transient errors |

**TA throttle** (caps parallel `tradingview_ta` calls):

| Env var | Default | Purpose |
| --- | --- | --- |
| `TRADINGVIEW_MCP_MAX_INFLIGHT` | 4 | Max concurrent TA calls |
| `TRADINGVIEW_MCP_MIN_INTERVAL_S` | 0.8 | Min seconds between TA call starts |

Set in `claude_desktop_config.json` via the `env` key:

```json
{
  "mcpServers": {
    "tradingview": {
      "command": "uvx",
      "args": ["--python", "3.13", "--from", "tradingview-mcp-server", "tradingview-mcp"],
      "env": {
        "CACHE_TTL_YAHOO_PRICE": "60",
        "CACHE_TTL_NEWS": "600"
      }
    }
  }
}
```

---

## 📱 Use via Telegram, WhatsApp & More (OpenClaw)

Connect this server to **Telegram, WhatsApp, Discord** and 20+ messaging platforms using [OpenClaw](https://openclaw.ai) — a self-hosted AI gateway. **Tested & verified on Hetzner VPS (Ubuntu 24.04).**

### How It Works

> OpenClaw routes Telegram messages to an AI agent. The agent uses `trading.py` — a thin Python wrapper — to call `tradingview-mcp` functions and return formatted results. **No MCP protocol needed between OpenClaw and the server; it's a direct Python import.**

```
Telegram → OpenClaw agent (AI model) → trading.py (bash) → tradingview-mcp → Yahoo Finance
```

### Quick Setup

```bash
# 1. Install UV and tradingview-mcp
curl -LsSf https://astral.sh/uv/install.sh | sh && source ~/.bashrc
uv tool install tradingview-mcp-server

# 2. Configure OpenClaw channels
cat > ~/.openclaw/openclaw.json << 'EOF'
{
  channels: {
    telegram: {
      botToken: "YOUR_BOT_TOKEN_HERE",
    },
  },
}
EOF

# 3. Configure gateway + agent
openclaw config set gateway.mode local
openclaw config set acp.defaultAgent main

# 4. Set your AI model (choose ONE option below)
openclaw configure --section model

# 5. Install the skill + tool wrapper
mkdir -p ~/.agents/skills/tradingview-mcp ~/.openclaw/tools
curl -fsSL https://raw.githubusercontent.com/atilaahmettaner/tradingview-mcp/main/openclaw/SKILL.md \
  -o ~/.agents/skills/tradingview-mcp/SKILL.md
curl -fsSL https://raw.githubusercontent.com/atilaahmettaner/tradingview-mcp/main/openclaw/trading.py \
  -o ~/.openclaw/tools/trading.py && chmod +x ~/.openclaw/tools/trading.py

# 6. Start the gateway
openclaw gateway install
systemctl --user start openclaw-gateway.service
```

### Choose Your AI Model

OpenRouter is **not required** — use whichever provider you have a key for:

| Provider | Model ID for OpenClaw | Get Key |
|----------|----------------------|---------|
| **OpenRouter** (aggregator — access to all models) | `openrouter/google/gemini-3-flash-preview` | [openrouter.ai/keys](https://openrouter.ai/keys) |
| **Anthropic** (Claude direct) | `anthropic/claude-sonnet-4-5` | [console.anthropic.com](https://console.anthropic.com) |
| **Google** (Gemini direct) | `google/gemini-2.5-flash` | [aistudio.google.com](https://aistudio.google.com) |
| **OpenAI** (GPT direct) | `openai/gpt-4o-mini` | [platform.openai.com](https://platform.openai.com) |

```bash
# Examples — set your chosen model:
openclaw config set agents.defaults.model "openrouter/google/gemini-3-flash-preview"  # via OpenRouter
openclaw config set agents.defaults.model "anthropic/claude-sonnet-4-5"               # Anthropic direct
openclaw config set agents.defaults.model "google/gemini-2.5-flash"                   # Google direct
```

> ⚠️ **Important:** Prefix must match your provider. `google/...` needs a Google API key. `openrouter/...` needs an OpenRouter key.

### ⚠️ Common Mistakes

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Unrecognized keys: mcpServers` | `mcpServers` not supported in this version | Remove from config, use bash wrapper |
| `No API key for provider "google"` | Used `google/model` but only have OpenRouter key | Use `openrouter/google/model` instead |
| `which agent?` loop | `acp.defaultAgent` not set | `openclaw config set acp.defaultAgent main` |
| Gateway won't start | `gateway.mode` missing | `openclaw config set gateway.mode local` |

### Test Your Bot

Once running, send your Telegram bot:
```
market snapshot
backtest RSI strategy for AAPL, 1 year
compare all strategies for BTC-USD
```

👉 **[Full OpenClaw Setup Guide →](OPENCLAW.md)**

---





Unlike basic screeners, this framework deploys **specialized AI agents** that debate findings in real-time:

1. **🛠️ Technical Analyst** — Bollinger Bands (±3 proprietary rating), RSI, MACD
2. **🌊 Sentiment & Momentum Analyst** — Reddit community sentiment + price momentum
3. **🛡️ Risk Manager** — Volatility, drawdown risk, mean-reversion signals

*Output: `STRONG BUY` / `BUY` / `HOLD` / `SELL` / `STRONG SELL` with confidence score*

---

## 🔧 All 30+ MCP Tools

### 📊 Backtesting Engine

| Tool | Description |
|------|-------------|
| `backtest_strategy` | Backtest 1 of 9 strategies with institutional metrics (Sharpe, Calmar, Expectancy). Supports `1d` and `1h` timeframes; optional full trade log + equity curve. |
| `compare_strategies` | Run all 9 strategies on the same symbol and rank by performance. |
| `walk_forward_backtest_strategy` | Train/test split walk-forward validation with overfitting verdict (ROBUST / MODERATE / WEAK / OVERFITTED). |

**9 Strategies to Test:**
- `rsi` — RSI oversold/overbought mean reversion
- `bollinger` — Bollinger Band mean reversion
- `macd` — MACD golden/death cross
- `ema_cross` — EMA 20/50 Golden/Death Cross
- `supertrend` — ATR-based Supertrend trend following 🔥
- `donchian` — Donchian Channel breakout (Turtle Trader style)
- `rsi_pullback` — Dip-buy in confirmed uptrend (SMA50>SMA200 + RSI<40 entry) 🆕
- `keltner_breakout` — ATR-normalized breakout (EMA20 + 2·ATR upper band) 🆕
- `triple_ema` — EMA 20/50 cross gated by SMA200 trend filter 🆕

> 🆕 strategies require `period='1y'` or `'2y'` so the SMA200 trend filter can complete its warmup.

**Metrics you get:** Win Rate, Total Return, Sharpe Ratio, Calmar Ratio, Max Drawdown, Profit Factor, Expectancy, Best/Worst Trade, vs Buy-and-Hold, with **realistic commission + slippage simulation**.

```
Example prompt: "Compare all 9 strategies on MSFT for 2 years"
→ #1 triple_ema:        +15.1% | Sharpe:  0.0 | WR: 100%
→ #2 keltner_breakout:  +14.3% | Sharpe:  4.7 | WR:  40%
→ #3 bollinger:         +12.2% | Sharpe:  4.1 | WR:  64%
→ Buy & Hold:            -2.1%
```

---

### 💰 Yahoo Finance — Real-Time Prices *(New in v0.6.0)*

| Tool | Description |
|------|-------------|
| `yahoo_price` | Real-time quote: price, change %, 52w high/low, market state |
| `market_snapshot` | Global overview: S&P500, NASDAQ, VIX, BTC, ETH, EUR/USD, SPY, GLD |

**Supports:** Stocks (AAPL, TSLA, NVDA), Crypto (BTC-USD, ETH-USD, SOL-USD), ETFs (SPY, QQQ, GLD), Indices (^GSPC, ^DJI, ^IXIC, ^VIX), FX (EURUSD=X), Turkish (THYAO.IS, SASA.IS)

---

### 🧠 AI Sentiment & Intelligence

| Tool | Description |
|------|-------------|
| `market_sentiment` | Reddit sentiment across finance communities (bullish/bearish score, top posts) |
| `financial_news` | Live RSS headlines from Yahoo Finance, MarketWatch, CNBC, CoinDesk, CoinTelegraph |
| `combined_analysis` | **Power Tool**: TradingView technicals + Reddit sentiment + live news → confluence decision. Now backed by retry + 60s cache for resilience against transient screener errors. |

---

### 📈 Technical Analysis Core

| Tool | Description |
|------|-------------|
| `get_technical_analysis` | Full TA: RSI, MACD, Bollinger, 23 indicators with BUY/SELL/HOLD |
| `get_multiple_analysis` | Bulk TA for multiple symbols at once |
| `get_bollinger_band_analysis` | Proprietary ±3 BB rating system |
| `get_stock_decision` | 3-layer decision engine (ranking + trade setup + quality score) |
| `screen_stocks` | Multi-exchange screener with 20+ filter criteria |
| `scan_by_signal` | Scan by signal type (oversold, trending, breakout...) |
| `get_candlestick_patterns` | 15 candlestick pattern detector |
| `get_multi_timeframe_analysis` | Weekly→Daily→4H→1H→15m alignment analysis |

---

### 🌍 Multi-Exchange Support

| Exchange | Tools |
|----------|-------|
| **Binance** | Crypto screener, all pairs |
| **KuCoin / Bybit+** | Crypto screener |
| **NASDAQ / NYSE** | US stocks (AAPL, TSLA, NVDA...) |
| **EGX (Egypt)** | `egx_market_overview`, `egx_stock_screener`, `egx_trade_plan`, `egx_fibonacci_retracement` |
| **Turkish (BIST)** | Via TradingView screener |

---

## 💬 Example AI Conversations

```
You: "Give me a full market snapshot right now"
AI: [market_snapshot] → S&P500 -3.4%, BTC +0.1%, VIX 31 (+13%), EUR/USD 1.15

You: "What is Reddit saying about NVDA?"
AI: [market_sentiment] → Strongly Bullish (0.41) | 23 posts | 18 bullish

You: "Backtest RSI strategy on BTC-USD for 2 years"
AI: [backtest_strategy] → +31.5% return | 100% win rate | 2 trades | B&H: -5%

You: "Which of the 9 strategies worked best on MSFT in the last 2 years?"
AI: [compare_strategies] → triple_ema #1 (+15.1%, WR 100%), keltner_breakout #2 (+14.3%), macd last (-23.4%)

You: "Run walk-forward backtest on supertrend for SPY"
AI: [walk_forward_backtest_strategy] → Verdict: ROBUST (avg robustness 0.92) | OOS return +8.5%

You: "Analyze TSLA with all signals: technical + sentiment + news"
AI: [combined_analysis] → BUY (Technical STRONG BUY + Bullish Reddit + Positive news)
```

---

## 💖 Support the Project

This framework is **free and open source**, built in spare time. If it saves you hours of research or helps you make better decisions, please consider sponsoring:

| Tier | Monthly | What You Get |
|------|---------|--------------|
| ☕ Coffee | $5 | Heartfelt gratitude + name in README |
| 🚀 Supporter | $15 | Above + priority bug fixes |
| 💎 Pro | $30 | Above + priority feature requests |

<a href="https://github.com/sponsors/atilaahmettaner">
  <img src="https://img.shields.io/badge/Become_a_Sponsor-pink?style=for-the-badge&logo=github-sponsors" alt="Sponsor"/>
</a>

Every sponsor directly funds new features like Walk-Forward Backtesting, Twitter/X sentiment, and managed cloud hosting.

---

## 📋 Roadmap

- [x] TradingView technical analysis (30+ indicators)
- [x] Multi-exchange screener (Binance, KuCoin, MEXC, EGX, US stocks)
- [x] Reddit sentiment analysis
- [x] Live financial news (Yahoo / MarketWatch / CNBC / CoinDesk / CoinTelegraph)
- [x] Yahoo Finance real-time prices
- [x] Backtesting engine (9 strategies + Sharpe / Calmar / Expectancy)
- [x] Walk-forward backtesting (overfitting detection)
- [x] Resilience layer (retry + TTL cache) on screener provider
- [x] Per-tool TTL cache on Yahoo / news / sentiment / options (env-tunable, error-aware)
- [x] Hourly (1h) backtesting timeframe
- [ ] Twitter/X market sentiment
- [ ] Paper trading simulation
- [ ] Managed cloud hosting (no local setup)

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

*Disclaimer: This tool is for educational and research purposes only. It does not constitute financial advice. Always do your own research before making investment decisions.*
