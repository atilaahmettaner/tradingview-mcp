# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

## [0.9.0] - 2026-08-26

### Changed (behavior)
- **Strict input validation**: tools now return `INVALID_EXCHANGE` /
  `INVALID_TIMEFRAME` error envelopes (listing valid values) instead of
  silently substituting the default — `exchange="KRAKEN"` used to return
  KUCOIN data with no warning. Aliases (`1d`→`1D`) and omitted parameters
  still resolve silently.
- **`PARTIAL_DATA` envelopes**: batched scans that abort mid-flight
  (wall-clock budget / consecutive-failure bail) return a `PARTIAL_DATA`
  envelope that still carries the collected rows, instead of a plain list
  indistinguishable from a complete scan.

### Fixed
- **`top_losers` returned gainers**: the service sorted descending and
  truncated to `limit` before the tool re-sorted ascending, so it returned
  the smallest of the top gainers. Sorting now happens before truncation.
- **Volume breakout scanner fabricated breakouts**: symbols missing a
  `volume.SMA20` baseline got a fallback ratio that was always exactly 2.0
  and passed the default gate on price change alone. They are now skipped.
- **Walk-forward robustness inverted for losing strategies**: a strategy
  losing MORE out-of-sample scored a capped 2.0 ("maximally robust") in the
  both-negative branch. Warmup-starved test folds are flagged
  `insufficient_data` and excluded instead of reading as OVERFITTED.
- **Multi-timeframe alignment misattribution**: a failed timeframe shifted
  every later score onto the wrong timeframe key in `scores_by_tf`.
- **`fetch_multi_timeframe_patterns` ignored its `symbols` argument**
  (whole-exchange scan) while caching on it.
- **Backtest metrics**: drawdown/Calmar/Sharpe now come from a per-bar
  mark-to-market equity series (intra-trade dips count); open positions at
  data end are force-closed and flagged `forced_exit`; the buy-and-hold
  benchmark pays the same round-trip costs as the strategy;
  `compare_strategies` validates `period`.
- **Thread safety**: the Yahoo options session handshake is lock-guarded;
  the screener cache is bounded (256 entries); cached indicator dicts are
  copied before ATR backfill; the resilience layer's stale-while-error
  cache is actually populated on success for `cache_key` callers.
- **Timeouts everywhere**: all `get_scanner_data` calls pass explicit
  timeouts (`requests` has no default).
- **Docker HEALTHCHECK**: the server now serves `GET /health` under the
  streamable-http transport, so containers stop cycling to `unhealthy`.
- Marketaux sentiment: whole-word keyword scoring and exact entity-symbol
  matching; multi-agent analysis no longer crashes on explicit-null
  indicators; proxy credentials are URL-encoded.

### Removed
- Dead code (~800 lines): the unwired paper-trading `portfolio.py`, the
  RSS `news_service.py` and Reddit `sentiment_service.py` (both replaced by
  Marketaux in 0.6), unused fetchers in `screener_provider.py` /
  `screener_service.py`, and the stray `PR_BODY.md`.

### Infrastructure
- **CI now runs the test suite** (Python 3.10–3.13 matrix) on every
  push/PR, and the Docker image publish is gated on it.
- `pandas` declared as a direct dependency (server.py imports it at module
  top; it previously arrived only via the tradingview-screener pin).
- `docker-compose.yml` points at the GHCR image CI actually builds.
- Real `SECURITY.md` (GitHub Security Advisories; 0.9.x supported).

## [0.8.1] - 2026-08-02

### Fixed
- Raised the `mcp` lower bound to `>=1.14.0` (still `<2`): with
  `from __future__ import annotations`, `Tool.from_function` in <=1.13.x
  dies at import time on string annotations, so the server never started
  on those SDK versions.

### Added
- Official MCP Registry manifest (`server.json`) + OIDC publish workflow.

## [0.8.0] - 2026-07-29

### Fixed
- **CRITICAL — pinned `mcp[cli]>=1.12.0,<2`**: `mcp` 2.0.0 (released 2026-07-28
  alongside the MCP 2026-07-28 stateless spec) removes the `mcp.server.fastmcp`
  module this server imports. 0.7.1's published metadata carries the open
  `>=1.12.0` range, so every fresh `pip install` / `uvx` since 2026-07-28
  resolved mcp 2.0.0 and died on startup with
  `ModuleNotFoundError: No module named 'mcp.server.fastmcp'`. Upgrade to
  0.8.0 to get a working install. Migrating to the 2.x SDK
  (FastMCP → MCPServer) will be a deliberate follow-up release.
- **`volume_confirmation_analysis` bare-symbol failures**: bare crypto symbols
  (no exchange prefix) failed ~99% of the time; symbols are now resolved
  before analysis.
- **Donchian breakout off-by-one**: the breakout strategy read a window that
  included the current bar, inflating backtest results; window is now strictly
  historical (regression-tested).
- **Backtest input validation**: initial capital and cost parameters are now
  validated instead of silently producing nonsense results.
- **`coin_analysis` ATR null bug**: `tradingview_ta` omits the `ATR` column from
  its analysis payload, which left `indicators["ATR"]` (and every downstream
  consumer — stop-loss sizing, trade-quality score, volatility metrics) at
  `None` on every call. `analyze_coin` now falls back to a direct
  `scanner.tradingview.com/<market>/scan` request via the new
  `fetch_atr_for_ticker()` helper in `screener_provider.py`. The lookup is
  best-effort (silent `None` on any network / parse failure) and only fires
  when `tradingview_ta` returned no ATR, so it does not regress healthy
  payloads. Timeframe → resolution mapping is shared with the existing
  screener column logic (`5m→5`, `15m→15`, `1h→60`, `4h→240`, `1D/1W/1M`
  unchanged); unknown timeframes degrade to the unsuffixed `ATR` column.

### Added
- **Markets**: Taiwan (TWSE, TPEX), Saudi Arabia (TADAWUL), US futures across
  CME/COMEX/NYMEX/CBOT (equity index, energy, metals, agriculture, rates, FX,
  crypto futures), AMEX/NYSEARCA aliases, auto-venue fallback for unlisted
  symbols, precious-metal futures resolution via TVC.
- **Tools**: `stock_screener` + `stock_prices` (bulk fetches up to 1,000 rows,
  `exclude_otc`, server-side sorting, daily OHLC), `stock_options_chain` +
  `stock_options_unusual_activity`, `stock_extended_hours`,
  `bitcoin_market_pulse`.
- **Directory-grade tool metadata**: every tool now ships `title`,
  `readOnlyHint`, and an explicit `destructiveHint=False` annotation.
- **Multi-arch Docker image CI**: GHCR images built for linux/amd64 +
  linux/arm64 on every push to main and on version tags.

### Changed
- **Every tool now runs off the event loop** (blanket async offload) — a slow
  upstream call can no longer block the MCP server's event loop.
- **Structured error envelopes everywhere**: screener/scanner failures return
  machine-readable envelopes with retryability signals and symbol
  suggestions instead of bare strings; note that tool return types are now
  `list[dict] | dict` (consumers that assumed a bare list should handle the
  envelope shape).
- **News pipeline**: RSS/Reddit scraping replaced with the licensed Marketaux
  API. Set `MARKETAUX_API_TOKEN` (see `.env.example`) to enable
  `financial_news` and news-driven sentiment; without a token the news tools
  return empty results while everything else works normally.
- **Reliability**: bounded HTTP timeouts with stale-while-error fallback,
  retry + 60s TTL response cache, `tradingview_ta` request throttling,
  fast-fail on upstream outages.
- Python support capped below 3.14 (`requires-python >=3.10,<3.14`) until the
  dependency stack publishes 3.14 wheels.
- `requests` is now an explicit dependency in `pyproject.toml`. It was already
  pulled in transitively by `tradingview-screener` / `tradingview-ta`, but the
  new ATR injection path uses it directly, so it is no longer safe to rely on
  the transitive resolution.

## [0.7.1] - 2026-04-14

### Added
- **MEXC Exchange Support** (`exchange="MEXC"`):
  - 420 MEXC trading pairs added — including many unique pairs not available on Binance, KuCoin, or Bybit
  - Fully supported in all tools: `top_gainers`, `top_losers`, `bollinger_scan`, `coin_analysis`, `multi_agent_analysis`, `volume_breakout_scanner`, `consecutive_candles_scan`, `advanced_candle_pattern`, and more
  - MEXC correctly categorized as a crypto screener market

---

## [0.7.0] - 2026-03-29

### Added
- **Walk-Forward Backtesting** (`walk_forward_backtest_strategy`):
  - Splits data into N folds (train/test) to validate strategy on unseen forward data
  - Per-fold in-sample vs out-of-sample return comparison
  - **Robustness score** (test/train ratio): ROBUST ≥ 0.8 | MODERATE ≥ 0.5 | WEAK ≥ 0.2 | OVERFITTED < 0.2
  - Aggregate out-of-sample metrics: Sharpe, win rate, max drawdown, total return
  - Supports 2–10 splits, configurable train ratio, both 1d and 1h intervals
- **Full Trade Log** (`include_trade_log=True`):
  - Per-trade breakdown: entry/exit date & price, holding days, gross/net return %, cost %
  - Running capital and cumulative return at each trade
- **Equity Curve** (`include_equity_curve=True`):
  - Capital value + drawdown % at each trade exit — ready for charting
- **1h (Hourly) Timeframe** (`interval="1h"`):
  - All strategies and compare now support intraday hourly data
  - Sharpe ratio annualization corrected for 1h bars (252 × 6 trading hours)
  - Works on `backtest_strategy`, `compare_strategies`, and `walk_forward_backtest_strategy`

### Changed
- `backtest_strategy` tool: added `interval`, `include_trade_log`, `include_equity_curve` params
- `compare_strategies` tool: added `interval` param; now documents all 6 strategies (was 4)
- `run_backtest()` now returns last 5 trades always (`recent_trades`) for quick inspection
- Sharpe ratio calculation now uses interval-aware annualization factor

---

## [0.6.0] - 2026-03-29

### Added
- **Backtesting Engine v2** (`backtest_strategy`, `compare_strategies`):
  - 6 trading strategies: RSI, Bollinger Band, MACD, EMA Cross, **Supertrend** (🔥 trending 2025), **Donchian Channel** (Turtle Trader classic)
  - Institutional-grade metrics: Sharpe Ratio, Calmar Ratio, Expectancy, Profit Factor, Max Drawdown
  - Transaction cost simulation: per-trade commission + slippage
  - Buy-and-hold benchmark comparison
  - Single OHLCV fetch for `compare_strategies` (all 6 strategies in ~0.3s)
- **Yahoo Finance Integration** (`yahoo_price`, `market_snapshot`):
  - Real-time quotes for stocks, crypto, ETFs, indices (S&P500, NASDAQ, VIX), FX
  - Global market snapshot with 14 instruments across 4 asset classes
  - Turkish stocks supported (THYAO.IS, SASA.IS...)
- **Webshare Rotating Proxy Manager**:
  - 250 sticky sessions for rate-limit bypass
  - Direct-first + proxy-fallback architecture for reliability
  - Zero-config for users (optional env-based configuration)
- **Technical Indicators (pure Python, zero deps)**:
  - ATR (Average True Range)
  - Supertrend
  - Donchian Channel

### Changed
- `compare_strategies` now fetches OHLCV once and runs all strategies on cached data (5x faster)
- Yahoo Finance data fetching uses direct connection first, proxy fallback only on failure

## [0.5.0] - 2026-03-29

### Added
- **Real-Time Market Sentiment (Agent-Reach Integration)**: Integrated Reddit JSON API to track symbol sentiment across finance communities (`market_sentiment`).
- **Live Financial News RSS**: Added `fetch_news` service via `feedparser` to track real-time headlines across Reuters, CoinDesk, and CoinTelegraph (`financial_news`).
- **Combined Analysis Power Tool**: The new `combined_analysis` tool merges TradingView technicals, Reddit sentiment, and live news into a single confluence analysis (signals agree/conflict, confidence score, full recommendation).
- Added `feedparser` dependency to `pyproject.toml`.

## [0.4.0] - 2026-03-29

### Added
- **EGX (Egyptian Exchange) Full Support**: Complete trading infrastructure for the Egyptian Stock Market.
  - `egx_market_overview`: Top gainers, losers, most active stocks, and market breadth stats (advancing/declining/unchanged).
  - `egx_sector_scan`: Scan across 18 EGX sectors (banks, real_estate, healthcare_and_pharma, technology, etc.).
  - `egx_stock_screener`: Cross-sectional ranking with auto trade plan generation.
  - `egx_trade_plan`: Single-stock detailed trade setup (entry, stop-loss, targets, R:R).
  - `egx_fibonacci_retracement`: Fibonacci retracement + extension levels with golden pocket detection.
  - 6 EGX indices: EGX30, EGX70, EGX100, SHARIAH33, EGX35LV, TAMAYUZ (200+ symbols).
- **3-Layer Stock Decision Engine**:
  - Layer A: 100-point stock ranking model (trend, momentum, risk, fundamentals).
  - Layer B: Trade setup engine (entry points, stop-loss, targets, support/resistance, R:R).
  - Layer C: Trade quality scoring (structure, risk/reward, volume, liquidity).
- **Liquidity-Aware Scoring**: Hard grade caps prevent illiquid stocks from ever receiving "Strong" or "Elite" grades.
- **23 Technical Indicators**: Expanded from 5 → 23: CCI, Williams %R, Awesome Oscillator, Momentum, Parabolic SAR, Ichimoku, Stoch RSI, ADX +DI/-DI, Hull MA, VWMA, Ultimate Oscillator, full EMA/SMA suites.
- **Multi-Timeframe Alignment**: Weekly→Daily→4H→1H→15m bias analysis with timeframe-specific advice.

### Fixed
- Hardcoded `"crypto"` market type in `_fetch_multi_changes`, `_fetch_multi_timeframe_patterns`, and `screener_provider` — now dynamically resolved per exchange (egypt, turkey, america, etc.).
- `volume_confirmation_analysis` was appending `"USDT"` to stock symbols — now exchange-aware with proper `EGX:SYMBOL` formatting.

### Changed
- MCP server name updated to "TradingView Multi-Market Screener".
- All tool descriptions updated to reference both crypto and stock exchanges.
- Added `is_stock_exchange()`, `get_market_type()`, and `STOCK_EXCHANGES` helpers to `validators.py`.

## [0.3.0] - 2026-03-24

### Added
- **Docker Support**: Official Dockerfile and docker-compose.yml for easy 1-click self-hosting.
- **PyPI Release**: Added proper metadata and structuring for PyPI distribution (`pip install tradingview-mcp`).

## [0.2.0] - 2026-03-24

### Added
- **Multi-Agent Trading Framework**: Introduced `multi_agent_analysis` MCP tool.
  - **Technical Analyst Agent**: Analyzes RSI, MACD, and Bollinger Bands.
  - **Sentiment Analyst Agent**: Calculates momentum and produces a sentiment score.
  - **Risk Manager Agent**: Evaluates volatility (BBW) and mean reversion risk.
- **Debate System**: Agents combine their scores to provide a single, logical Framework Decision (Strong Buy, Buy, Hold, Sell, Strong Sell) with confidence levels.

### Changed
- Repositioned the project from a "screener" to an "AI Trading Intelligence Framework".
- Updated `README.md` to reflect the new architecture.

## [0.1.0] - Initial Release
- Basic MCP Server setup.
- Bollinger Band squeeze detection.
- Consecutive candle pattern detection.
- Real-time market screening (gainers, losers).
