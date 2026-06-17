# Docker MCP User Guide — TradingView MCP Server

This guide walks you through running **tradingview-mcp** in Docker and calling its tools over HTTP. No Python or `uv` install is required on your machine — only Docker.

---

## What you get

The Docker container runs the MCP server in **streamable-http** mode and exposes **30+ tools**, including:

| Category | Example tools |
|----------|---------------|
| Market screening | `top_gainers`, `top_losers`, `bollinger_scan`, `rating_filter` |
| Analysis | `coin_analysis`, `multi_timeframe_analysis`, `combined_analysis` |
| Volume / patterns | `volume_breakout_scanner`, `consecutive_candles_scan` |
| EGX (Egypt) | `egx_market_overview`, `egx_trade_plan`, `egx_stock_screener` |
| Yahoo Finance | `yahoo_price`, `market_snapshot`, `stock_extended_hours` |
| Backtesting | `backtest_strategy`, `compare_strategies` |

---

## Prerequisites

- **Docker Desktop** (Windows / macOS) or **Docker Engine** (Linux)
- **Docker Compose** (included with Docker Desktop)
- Internet access (for market data)

Verify Docker is installed:

```powershell
docker --version
docker compose version
```

---

## Step 1 — Get the project

Clone the repository (or use a folder you already have):

```powershell
git clone https://github.com/atilaahmettaner/tradingview-mcp.git
cd tradingview-mcp
```

---

## Step 2 — Start the MCP service

From the project root, start the container in the background:

```powershell
docker compose up -d
```

**What this does:**

| Setting | Value |
|---------|-------|
| Container name | `tradingview-mcp` |
| Image | `atilaahmet/tradingview-mcp:latest` (built locally if missing) |
| Host port | `8080` |
| Container port | `8000` |
| MCP endpoint | `http://127.0.0.1:8080/mcp` |
| Health check | `http://127.0.0.1:8080/health` |

Wait a few seconds for the first startup, then confirm the container is running:

```powershell
docker compose ps
docker logs tradingview-mcp --tail 20
```

Expected: container status **Up** and logs showing the HTTP server listening on port 8000.

---

## Step 3 — Verify the service is healthy

**PowerShell:**

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8080/health" -UseBasicParsing
```

**curl (Git Bash / WSL / macOS / Linux):**

```bash
curl http://127.0.0.1:8080/health
```

If you get a successful HTTP response, the server is ready.

---

## Step 4 — Understand the MCP call flow

Every tool call over HTTP follows the same **4-step** JSON-RPC sequence:

```
┌─────────────┐     POST /mcp      ┌──────────────────┐
│ Your client │ ── initialize ──► │ tradingview-mcp  │
│             │ ◄─ mcp-session-id │ (Docker :8080)   │
│             │ ── initialized ─► │                  │
│             │ ── tools/call ──► │                  │
│             │ ◄─ SSE data: ...  │                  │
└─────────────┘                   └──────────────────┘
```

| Step | Method | Purpose |
|------|--------|---------|
| 1 | `initialize` | Start a session; server returns `mcp-session-id` header |
| 2 | `notifications/initialized` | Tell the server the client is ready |
| 3 | `tools/call` (or `tools/list`) | Run a tool or list available tools |
| 4 | Parse response | Result arrives as SSE lines starting with `data:` |

**Required headers for every request:**

```
Content-Type: application/json
Accept: application/json, text/event-stream
Mcp-Session-Id: <from step 1>   # required after initialize
```

---

## Step 5 — Quick test with the included script

The repo includes `call-yahoo-price.ps1` for a one-tool smoke test.

**Windows (execution policy blocked by default):**

```powershell
powershell -ExecutionPolicy Bypass -File .\call-yahoo-price.ps1 -Symbol AAPL
powershell -ExecutionPolicy Bypass -File .\call-yahoo-price.ps1 -Symbol BTC-USD
powershell -ExecutionPolicy Bypass -File .\call-yahoo-price.ps1 -Symbol TSLA
```

**Sample output:**

```
symbol         : AAPL
price          : 291.07
previous_close : 290.55
change         : 0.52
change_pct     : 0.18
currency       : USD
exchange       : NMS
source         : Yahoo Finance
```

**Optional — allow scripts permanently (current user only):**

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

After that, `.\call-yahoo-price.ps1 -Symbol AAPL` works without the bypass flag.

---

## Step 6 — Call any tool from PowerShell

Use this reusable pattern. Change `name` and `arguments` for each tool.

### Example A — `yahoo_price` (stock quote)

```powershell
$MCP_URL = "http://127.0.0.1:8080/mcp"
$headers = @{
  "Content-Type" = "application/json"
  "Accept"       = "application/json, text/event-stream"
}

# 1. Initialize
$initBody = @{
  jsonrpc = "2.0"; id = 1; method = "initialize"
  params = @{
    protocolVersion = "2025-03-26"
    capabilities    = @{}
    clientInfo      = @{ name = "ps-client"; version = "1.0" }
  }
} | ConvertTo-Json -Depth 5

$r = Invoke-WebRequest -Uri $MCP_URL -Method POST -Headers $headers -Body $initBody -UseBasicParsing
$headers["Mcp-Session-Id"] = $r.Headers["mcp-session-id"]

# 2. Ready
Invoke-WebRequest -Uri $MCP_URL -Method POST -Headers $headers `
  -Body '{"jsonrpc":"2.0","method":"notifications/initialized"}' -UseBasicParsing | Out-Null

# 3. Call tool
$callBody = @{
  jsonrpc = "2.0"; id = 2; method = "tools/call"
  params = @{
    name      = "yahoo_price"
    arguments = @{ symbol = "AAPL" }
  }
} | ConvertTo-Json -Depth 5

$result = Invoke-WebRequest -Uri $MCP_URL -Method POST -Headers $headers -Body $callBody -UseBasicParsing

# 4. Parse SSE response
$line = ($result.Content -split "`n" | Where-Object { $_ -like "data:*" }) -replace "^data: ", ""
$json = $line | ConvertFrom-Json
$json.result.content[0].text | ConvertFrom-Json | Format-List
```

### Example B — `top_gainers` (crypto screener)

Change only step 3:

```powershell
$callBody = @{
  jsonrpc = "2.0"; id = 2; method = "tools/call"
  params = @{
    name      = "top_gainers"
    arguments = @{
      exchange  = "BINANCE"
      timeframe = "1D"
      limit     = 5
    }
  }
} | ConvertTo-Json -Depth 5
```

### Example C — `coin_analysis` (technical analysis)

```powershell
$callBody = @{
  jsonrpc = "2.0"; id = 2; method = "tools/call"
  params = @{
    name      = "coin_analysis"
    arguments = @{
      symbol    = "BTCUSDT"
      exchange  = "KUCOIN"
      timeframe = "1D"
    }
  }
} | ConvertTo-Json -Depth 5
```

### Example D — `market_snapshot` (no arguments)

```powershell
$callBody = @{
  jsonrpc = "2.0"; id = 2; method = "tools/call"
  params = @{
    name      = "market_snapshot"
    arguments = @{}
  }
} | ConvertTo-Json -Depth 5
```

### Example E — `backtest_strategy`

```powershell
$callBody = @{
  jsonrpc = "2.0"; id = 2; method = "tools/call"
  params = @{
    name      = "backtest_strategy"
    arguments = @{
      symbol   = "AAPL"
      strategy = "rsi"
      period   = "1y"
    }
  }
} | ConvertTo-Json -Depth 5
```

### Example F — `egx_market_overview`

```powershell
$callBody = @{
  jsonrpc = "2.0"; id = 2; method = "tools/call"
  params = @{
    name      = "egx_market_overview"
    arguments = @{
      timeframe = "1D"
      limit     = 10
    }
  }
} | ConvertTo-Json -Depth 5
```

---

## Step 7 — List all available tools

After initialize (steps 1–2), send:

```powershell
$listBody = '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
$result = Invoke-WebRequest -Uri $MCP_URL -Method POST -Headers $headers -Body $listBody -UseBasicParsing
$line = ($result.Content -split "`n" | Where-Object { $_ -like "data:*" }) -replace "^data: ", ""
($line | ConvertFrom-Json).result.tools | Select-Object name, description | Format-Table -Wrap
```

---

## Step 8 — Call tools with curl (bash / WSL)

Save session handling in a small shell script, or run step by step:

```bash
MCP_URL="http://127.0.0.1:8080/mcp"

# 1. Initialize and capture session ID
SESSION=$(curl -s -D - -X POST "$MCP_URL" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"1.0"}}}' \
  | grep -i mcp-session-id | awk '{print $2}' | tr -d '\r')

# 2. Initialized notification
curl -s -X POST "$MCP_URL" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: $SESSION" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}' > /dev/null

# 3. Call yahoo_price
curl -s -X POST "$MCP_URL" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: $SESSION" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"yahoo_price","arguments":{"symbol":"AAPL"}}}'
```

---

## Step 9 — Connect Cursor IDE to the Docker service

Instead of calling HTTP manually, point Cursor at the running container.

1. Open or create MCP config:
   - **Project:** `.cursor/mcp.json` in this repo
   - **Global:** `%USERPROFILE%\.cursor\mcp.json` (Windows) or `~/.cursor/mcp.json` (macOS/Linux)

2. Add the tradingview server:

```json
{
  "mcpServers": {
    "tradingview": {
      "url": "http://127.0.0.1:8080/mcp"
    }
  }
}
```

3. **Restart Cursor completely** (quit and reopen).

4. In chat, ask naturally, for example:
   - "Show top 5 gainers on Binance today"
   - "Analyze BTCUSDT on KuCoin"
   - "Get AAPL price from Yahoo Finance"

Cursor handles the MCP session automatically.

---

## Step 10 — Manage the Docker service

| Task | Command |
|------|---------|
| Start | `docker compose up -d` |
| Stop | `docker compose down` |
| Restart | `docker compose restart` |
| View logs | `docker logs tradingview-mcp -f` |
| Rebuild after code changes | `docker compose up -d --build` |
| Check status | `docker compose ps` |

---

## Tool reference (quick copy-paste)

Use these `name` + `arguments` pairs in `tools/call`:

| Tool | Arguments example |
|------|-------------------|
| `yahoo_price` | `{ "symbol": "AAPL" }` |
| `market_snapshot` | `{}` |
| `bitcoin_market_pulse` | `{}` |
| `top_gainers` | `{ "exchange": "BINANCE", "timeframe": "1D", "limit": 10 }` |
| `top_losers` | `{ "exchange": "KUCOIN", "timeframe": "15m", "limit": 10 }` |
| `bollinger_scan` | `{ "exchange": "KUCOIN", "timeframe": "4h", "bbw_threshold": 0.04 }` |
| `coin_analysis` | `{ "symbol": "BTCUSDT", "exchange": "KUCOIN", "timeframe": "1D" }` |
| `multi_timeframe_analysis` | `{ "symbol": "BTCUSDT", "exchange": "KUCOIN" }` |
| `combined_analysis` | `{ "symbol": "AAPL", "exchange": "NASDAQ", "timeframe": "1D" }` |
| `volume_breakout_scanner` | `{ "exchange": "BINANCE", "timeframe": "15m", "limit": 10 }` |
| `market_sentiment` | `{ "symbol": "BTC", "category": "crypto", "limit": 20 }` |
| `financial_news` | `{ "symbol": "AAPL", "category": "stocks", "limit": 10 }` |
| `backtest_strategy` | `{ "symbol": "AAPL", "strategy": "rsi", "period": "1y" }` |
| `compare_strategies` | `{ "symbol": "BTC-USD", "period": "1y" }` |
| `stock_extended_hours` | `{ "symbol": "NVDA" }` |
| `stock_options_chain` | `{ "symbol": "AAPL" }` |
| `egx_market_overview` | `{ "timeframe": "1D", "limit": 10 }` |
| `egx_trade_plan` | `{ "symbol": "COMI", "timeframe": "1D" }` |

**Supported exchanges (screening tools):** `KUCOIN`, `BINANCE`, `BYBIT`, `MEXC`, `EGX`, `BIST`, `NASDAQ`, `NYSE`, `BURSA`, `HKEX`, `SSE`, `SZSE`, `TWSE`, `TPEX`

**Backtest strategies:** `rsi`, `bollinger`, `macd`, `ema_cross`, `supertrend`, `donchian`, `rsi_pullback`, `keltner_breakout`, `triple_ema`

More examples: see [EXAMPLES.md](EXAMPLES.md).

---

## Troubleshooting

### `running scripts is disabled on this system` (PowerShell)

Windows blocks `.ps1` files by default. Use:

```powershell
powershell -ExecutionPolicy Bypass -File .\call-yahoo-price.ps1 -Symbol AAPL
```

Or set policy for your user: `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser`

### `Unable to connect` / connection refused on port 8080

1. Check Docker is running: `docker compose ps`
2. Start the service: `docker compose up -d`
3. Check logs: `docker logs tradingview-mcp`
4. Confirm nothing else uses port 8080

### Empty or error response from a tool

- **First request** can take 10–30 seconds while data is fetched.
- Use valid symbols: crypto `BTCUSDT`, stocks `AAPL`, Yahoo `BTC-USD`, `THYAO.IS`.
- Prefer `KUCOIN` or `BINANCE` for crypto screening reliability.
- Some tools return an error envelope instead of empty data:

```json
{
  "error": {
    "code": "ALL_BATCHES_FAILED",
    "message": "..."
  }
}
```

Wait a moment and retry.

### Cursor does not see tools

1. Confirm Docker is up: `curl http://127.0.0.1:8080/health`
2. Verify `mcp.json` URL is exactly `http://127.0.0.1:8080/mcp`
3. Fully quit and restart Cursor
4. Check **Settings → Tools & MCP** for connection status

### Rebuild after pulling new code

```powershell
git pull
docker compose up -d --build
```

---

## Alternative — run without docker-compose

Pull and run the published image directly:

```powershell
docker run -d --name tradingview-mcp -p 8080:8000 --restart unless-stopped atilaahmet/tradingview-mcp:latest
```

MCP endpoint remains: `http://127.0.0.1:8080/mcp`

---

## Related docs

- [README.md](README.md) — feature overview
- [INSTALLATION.md](INSTALLATION.md) — non-Docker setup (uv / Claude Desktop)
- [EXAMPLES.md](EXAMPLES.md) — natural-language usage examples
- [call-yahoo-price.ps1](call-yahoo-price.ps1) — minimal PowerShell sample script

---

**Happy trading!** Remember: outputs are for research and education only — not financial advice.
