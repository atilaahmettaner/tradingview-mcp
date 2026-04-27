## Summary

Fixes two confirmed bugs where the `exchange` parameter was ignored or incorrectly resolved when querying US ETFs (GDX, GLD, XLE) and other non-crypto assets.

Closes #_ (relate to PR #23 which added TWSE/TPEX — same category of exchange-routing bugs)

---

## Bug 1: `multi_timeframe_analysis` hardcoded `KUCOIN:` prefix (high severity)

**Symptom**: Calling `multi_timeframe_analysis(symbol="GDX", exchange="AMEX")` returned data for `KUCOIN:GDX` with all timeframes showing `"No data for {tf}"`.

**Root cause**: `sanitize_exchange("AMEX", "KUCOIN")` returned `"KUCOIN"` (the fallback default) because `"amex"` was not in `EXCHANGE_SCREENER`. The subsequent symbol construction `f"{exchange.upper()}:{symbol.upper()}"` then produced `KUCOIN:GDX`.

**Fix** (`src/tradingview_mcp/core/utils/validators.py`):
- Added `"amex"`, `"nysearca"`, `"pcx"` to both `EXCHANGE_SCREENER` (→ `"america"` screener) and `STOCK_EXCHANGES`
- Added `get_tv_exchange_prefix(exchange)` helper that returns the correct TradingView symbol prefix (e.g. `"AMEX"` for `"nysearca"`)
- Updated `multi_timeframe_analysis` in `server.py` to use `get_tv_exchange_prefix(exchange)` instead of `exchange.upper()`

---

## Bug 2: `combined_analysis` / `coin_analysis` returned "No data found" for AMEX-listed ETFs (medium severity)

**Symptom**: `combined_analysis(symbol="GDX", exchange="NYSE", timeframe="1D")` returned `error: "No data found for GDX on nyse"`.

**Root cause**: TradingView lists NYSE Arca ETFs (GDX, GLD, XLE, SPY, QQQ, etc.) under the `AMEX:` exchange prefix, **not** `NYSE:`. `analyze_coin` built the symbol as `NYSE:GDX`, which returns no data.

**Fix** (`src/tradingview_mcp/core/services/screener_service.py`):
- `analyze_coin` now uses `get_tv_exchange_prefix(exchange)` for symbol construction
- Users passing `exchange="NYSE"` get `NYSE:GDX` (for actual NYSE stocks), while ETF users should now pass `exchange="AMEX"`, `"NYSEARCA"`, or `"PCX"` to get `AMEX:GDX`

---

## New: AMEX / NYSEARCA / PCX exchange aliases

TradingView uses `AMEX` as its canonical prefix for all NYSE Arca (formerly American Stock Exchange / Pacific Exchange) listings. This PR adds three accepted aliases that all resolve to `AMEX:`:

| User input | Screener | Symbol prefix |
|---|---|---|
| `AMEX` | `america` | `AMEX:` |
| `NYSEARCA` | `america` | `AMEX:` |
| `PCX` | `america` | `AMEX:` |

Examples that now work:
```
multi_timeframe_analysis(symbol="GDX", exchange="AMEX")   → AMEX:GDX ✓
multi_timeframe_analysis(symbol="GLD", exchange="NYSEARCA") → AMEX:GLD ✓
combined_analysis(symbol="XLE", exchange="PCX", timeframe="1D") → AMEX:XLE ✓
coin_analysis(symbol="SPY", exchange="AMEX", timeframe="1D")   → AMEX:SPY ✓
```

---

## TWSE / TPEX (Taiwan) — no changes needed

TWSE and TPEX were already present in `EXCHANGE_SCREENER` (added in PR #23). Taiwan stocks like 2330, 0050, 0056 already work correctly. The `get_tv_exchange_prefix` function now makes this routing explicit and testable.

---

## Tests

Added `tests/unit/test_exchange_fixes.py` with **32 tests** covering:
- `sanitize_exchange` accepts `AMEX`, `NYSEARCA`, `PCX`
- `EXCHANGE_SCREENER` and `STOCK_EXCHANGES` contain all three new aliases
- `get_tv_exchange_prefix` maps all aliases to `"AMEX"` and handles crypto fallback
- End-to-end symbol construction: `GDX`/`GLD`/`XLE` with any alias → `AMEX:<sym>`
- Regression: `NYSE`, `NASDAQ`, `TWSE`, `TPEX`, `KUCOIN`, `BINANCE` unchanged

```
73 passed in 0.17s  (69 new + 4 pre-existing)
```

---

## Files changed

| File | Change |
|---|---|
| `src/tradingview_mcp/core/utils/validators.py` | Add AMEX/NYSEARCA/PCX to maps; add `get_tv_exchange_prefix()` |
| `src/tradingview_mcp/core/services/screener_service.py` | `analyze_coin`: use `get_tv_exchange_prefix` for symbol |
| `src/tradingview_mcp/server.py` | `multi_timeframe_analysis`: use `get_tv_exchange_prefix`; update docstrings |
| `tests/unit/test_exchange_fixes.py` | 32 new unit tests |
| `tests/unit/test_exchange_aliases.py` | 37 additional unit tests (TWSE/TPEX symbol construction, pre-qualified symbol guard) |
| `pyproject.toml` / `uv.lock` | Add `pytest` as dev dependency |
