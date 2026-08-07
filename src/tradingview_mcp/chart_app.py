"""price_chart — interactive candlestick chart rendered inside the
conversation (MCP Apps extension).

Open-source edition: daily and hourly interval. The hosted version at
pro.cryptosieve.com additionally serves the 15-minute intraday interval and
a Bollinger Band overlay — that split is intentional (open-core), keep it.

Candle data reuses the same Yahoo OHLCV path the backtest tools call, so
what the chart shows always agrees with backtest numbers. Hosts without the
Apps extension get a readable text summary instead of a dead iframe.

Wire-format note: the Apps fields ride on the pinned mcp 1.x SDK via
``apps_shim.enable_apps`` — see that module before touching registration.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Any, Callable

from mcp.types import ToolAnnotations

from .apps_shim import enable_apps
from .core.services.backtest_service import _fetch_ohlcv

CHART_URI = "ui://tradingview/price-chart.html"

_PERIODS = {"1mo", "3mo", "6mo", "1y", "2y"}
_INTERVALS = {"1d", "1h"}

# Yahoo occasionally ignores the range param and serves a single latest bar.
# Anything below these floors is a truncated series, not a market reality —
# retry instead of charting one candle.
_EXPECTED_MIN_BARS = {"1mo": 15, "3mo": 40, "6mo": 80, "1y": 150, "2y": 300}

# Yahoo wants BTC-USD / AAPL / THYAO.IS. MCP users habitually type
# EXCHANGE:SYMBOL or exchange-style pairs (BTCUSDT) — accept those too.
_QUOTE_SUFFIXES = ("USDT", "USDC", "USD")

# Yahoo ticker charset. The symbol is interpolated into the Yahoo URL path
# downstream, so anything outside this set is either a typo or
# query-smuggling (?range=...#) — reject both before it reaches the wire.
_SYMBOL_RE = re.compile(r"^[A-Z0-9.\-=^]{1,20}$")


def _to_yahoo(symbol: str) -> str:
    s = symbol.strip().upper()
    if ":" in s:
        s = s.split(":", 1)[1]
    if "-" not in s and "." not in s:
        for suffix in _QUOTE_SUFFIXES:
            if s.endswith(suffix) and len(s) > len(suffix):
                s = f"{s[:-len(suffix)]}-USD"
                break
    if not _SYMBOL_RE.fullmatch(s):
        raise ValueError(
            f"Invalid symbol {symbol!r} — expected a Yahoo Finance ticker "
            "like AAPL, BTC-USD, THYAO.IS, GC=F or ^GSPC."
        )
    return s


def _chart_time(date_str: str, interval: str) -> Any:
    # lightweight-charts accepts 'YYYY-MM-DD' strings for daily bars but
    # needs epoch seconds for intraday.
    if interval == "1d":
        return date_str
    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


async def _fetch_robust(fetch: Callable[[], list[dict]], min_bars: int) -> list[dict]:
    last: list[dict] = []
    for attempt in range(3):
        # The fetcher is blocking urllib — keep it off the event loop.
        raw = await asyncio.to_thread(fetch)
        if len(raw) >= min_bars:
            return raw
        last = raw
        await asyncio.sleep(0.8 * (attempt + 1))
    return last


_CHART_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  html, body { margin: 0; padding: 0; background: transparent; }
  #hdr { display: flex; gap: 12px; align-items: baseline; padding: 8px 12px 4px;
         font-family: system-ui, -apple-system, sans-serif; }
  #sym { font-weight: 600; font-size: 15px; }
  #last { font-size: 14px; opacity: .85; }
  #chg { font-size: 13px; }
  #chg.up { color: #26a69a; }
  #chg.down { color: #ef5350; }
  #chart { height: 360px; }
</style>
</head>
<body>
<div id="hdr"><span id="sym"></span><span id="last"></span><span id="chg"></span></div>
<div id="chart"></div>
<script type="module">
// 1.0.1 matches the app-bridge generation current hosts ship; the 0.x line
// speaks an older bridge protocol and tool results never arrive.
import { App } from "https://unpkg.com/@modelcontextprotocol/ext-apps@1.0.1/app-with-deps";
// standalone build: the plain production.mjs has a bare `fancy-canvas`
// import browsers can't resolve without an import map — it kills the whole
// module script silently. Standalone bundles its deps.
import { createChart, CandlestickSeries } from "https://unpkg.com/lightweight-charts@5.2.0/dist/lightweight-charts.standalone.production.mjs";

const chart = createChart(document.getElementById("chart"), {
  autoSize: true,
  layout: { background: { color: "transparent" }, textColor: "#9aa0ac" },
  grid: { vertLines: { color: "rgba(128,128,128,.12)" },
          horzLines: { color: "rgba(128,128,128,.12)" } },
  timeScale: { borderVisible: false },
  rightPriceScale: { borderVisible: false },
});
const series = chart.addSeries(CandlestickSeries, {
  upColor: "#26a69a", downColor: "#ef5350", borderVisible: false,
  wickUpColor: "#26a69a", wickDownColor: "#ef5350",
});

function render(d) {
  if (!d || !Array.isArray(d.candles) || !d.candles.length) return;
  series.setData(d.candles);
  // The host reveals/sizes the iframe after the result arrives; fitting
  // immediately computes against a 0-width canvas and squeezes the candles.
  requestAnimationFrame(() => chart.timeScale().fitContent());
  new ResizeObserver(() => chart.timeScale().fitContent())
    .observe(document.getElementById("chart"));
  document.getElementById("sym").textContent = d.symbol + " · " + d.interval;
  document.getElementById("last").textContent = String(d.last_close);
  const chg = document.getElementById("chg");
  chg.textContent = (d.change_pct >= 0 ? "+" : "") + d.change_pct + "%";
  chg.className = d.change_pct >= 0 ? "up" : "down";
}

const app = new App({ name: "price-chart", version: "0.1.0" });
app.ontoolresult = (r) => {
  // The bridge may deliver the CallToolResult directly or wrapped in
  // {toolResult: ...} (both shapes exist in the ext-apps notification schema).
  const res = (r && r.toolResult) || r || {};
  let d = res.structuredContent;
  if (!d && Array.isArray(res.content)) {
    const t = res.content.find((c) => c.type === "text");
    if (t) { try { d = JSON.parse(t.text); } catch (e) {} }
  }
  render(d);
};
await app.connect();
</script>
</body>
</html>
"""


def register_chart_app(mcp: Any) -> None:
    @mcp.resource(CHART_URI, mime_type="text/html;profile=mcp-app")
    def price_chart_view() -> str:
        return _CHART_HTML

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Interactive Price Chart",
            readOnlyHint=True,
            destructiveHint=False,
            openWorldHint=True,
        )
    )
    async def price_chart(
        symbol: str,
        period: str = "6mo",
        interval: str = "1d",
    ) -> dict:
        """Render an interactive candlestick chart for a symbol inside the
        conversation. Accepts crypto pairs (BTCUSDT, BTC-USD), stocks (AAPL,
        NVDA) or any Yahoo Finance symbol. period: 1mo|3mo|6mo|1y|2y,
        interval: 1d|1h. Clients without interactive app support can read
        the `summary` field of the result. (The hosted version at
        pro.cryptosieve.com adds a 15-minute interval and Bollinger Band
        overlays.)"""
        if interval not in _INTERVALS:
            return {"error": f"interval must be one of {sorted(_INTERVALS)}"}
        if period not in _PERIODS:
            return {"error": f"period must be one of {sorted(_PERIODS)}"}
        try:
            yahoo_symbol = _to_yahoo(symbol)
        except ValueError as exc:
            return {"error": str(exc)}
        try:
            raw = await _fetch_robust(
                lambda: _fetch_ohlcv(yahoo_symbol, period, interval),
                _EXPECTED_MIN_BARS.get(period, 2),
            )
        except Exception as exc:
            return {"error": f"Failed to fetch data for '{yahoo_symbol}': {exc}"}
        if len(raw) < 2:
            return {
                "error": (
                    f"Data source returned a truncated series for "
                    f"'{yahoo_symbol}' ({len(raw)} bar). Try again shortly."
                )
            }

        candles = [
            {
                "time": _chart_time(c["date"], interval),
                "open": c["open"],
                "high": c["high"],
                "low": c["low"],
                "close": c["close"],
            }
            for c in raw
        ]
        first_close, last_close = candles[0]["close"], candles[-1]["close"]
        change_pct = round((last_close - first_close) / first_close * 100, 2)
        lo = min(c["low"] for c in candles)
        hi = max(c["high"] for c in candles)
        return {
            "symbol": yahoo_symbol,
            "period": period,
            "interval": interval,
            "last_close": last_close,
            "change_pct": change_pct,
            "candles": candles,
            "summary": (
                f"{yahoo_symbol} {period}/{interval}: close {last_close} "
                f"({change_pct:+}% over period), range {lo}–{hi}, "
                f"{len(candles)} bars."
            ),
        }

    enable_apps(
        mcp,
        tool_ui={"price_chart": CHART_URI},
        resource_meta={
            CHART_URI: {"ui": {"csp": {"resourceDomains": ["https://unpkg.com"]}}}
        },
    )
