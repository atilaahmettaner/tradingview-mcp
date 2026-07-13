"""
Stock Screener Service — share-type (common/preferred) stock screening and
direct multi-symbol price lookups via tradingview_screener.

The discriminator mirrors TradingView's own symbol-search filter and was
verified against the live scanner (2026-07-13, tradingview-screener==3.0.0,
the version pinned in pyproject.toml): a "Common stock" / "Preferred stock"
row in the UI corresponds to ``col('type') == 'stock'`` plus
``col('typespecs').has(['common'])`` / ``(['preferred'])``. Measured then:
market 'america' returned 10,974 common / 676 preferred rows; 'korea' 2,637
common (KRX, prices in KRW).

IMPORTANT: do NOT add an ``is_primary`` filter to the preferred query —
preferred shares are almost never the primary listing, so the scan silently
returns 0 rows (america preferred: 676 without the filter, 0 with it). See
also futures_service._futures_query() for why bumping tradingview-screener
past 3.0.0 would inject exactly that kind of preset by default.
"""
from __future__ import annotations

from typing import Any

try:
    from tradingview_screener import Query, col
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

STOCK_TYPES = ("common", "preferred")

# Not exhaustive — any market name tradingview_screener accepts works. This
# list only feeds error messages so a caller who typos a country sees
# known-good options instead of a bare upstream error.
EXAMPLE_MARKETS = (
    "america", "korea", "germany", "brazil", "japan", "uk",
    "india", "turkey", "canada", "australia", "france", "hongkong",
)

_SCREEN_COLUMNS = (
    "name", "description", "exchange", "close", "currency",
    "change", "dividends_yield_current", "market_cap_basic",
)

_PRICE_COLUMNS = ("name", "description", "exchange", "close", "currency", "change")

MAX_SCREEN_LIMIT = 100
MAX_PRICE_TICKERS = 50


def _clean(value: Any) -> Any:
    """NaN -> None so rows serialize to JSON cleanly."""
    try:
        if value != value:  # noqa: PLR0124 — NaN is the only x != x
            return None
    except Exception:
        pass
    return value


def _require_available() -> None:
    if not _AVAILABLE:
        raise RuntimeError("tradingview_screener not installed")


def screen_stocks(
    country: str = "america",
    stock_type: str = "common",
    limit: int = 50,
) -> dict[str, Any]:
    """Screen stocks of one share type for a country market.

    Returns an envelope: total_matches is the market-wide count, rows are the
    top-N by market cap.
    """
    _require_available()
    stock_type = (stock_type or "common").strip().lower()
    if stock_type not in STOCK_TYPES:
        raise ValueError(
            f"stock_type must be one of {list(STOCK_TYPES)}, got {stock_type!r}"
        )
    country = (country or "america").strip().lower()
    limit = max(1, min(int(limit), MAX_SCREEN_LIMIT))

    query = (
        Query()
        .set_markets(country)
        .select(*_SCREEN_COLUMNS)
        .where(col("type") == "stock", col("typespecs").has([stock_type]))
        .order_by("market_cap_basic", ascending=False)
        .limit(limit)
    )
    total, df = query.get_scanner_data()
    rows = [
        {
            "ticker": _clean(r.get("ticker")),
            "symbol": _clean(r.get("name")),
            "description": _clean(r.get("description")),
            "exchange": _clean(r.get("exchange")),
            "price": _clean(r.get("close")),
            "currency": _clean(r.get("currency")),
            "change_percent": _clean(r.get("change")),
            "dividend_yield": _clean(r.get("dividends_yield_current")),
            "market_cap": _clean(r.get("market_cap_basic")),
        }
        for r in df.to_dict("records")
    ]
    return {
        "country": country,
        "stock_type": stock_type,
        "total_matches": total,
        "returned": len(rows),
        "rows": rows,
    }


def fetch_stock_prices(tickers: str) -> dict[str, Any]:
    """Current price + daily % change for specific symbols.

    ``tickers`` is a comma-separated list in EXCHANGE:SYMBOL form, e.g.
    ``"NASDAQ:NVDA, KRX:005930"`` — the exchange prefix is required because
    the scanner's direct-ticker lookup is exchange-scoped.
    """
    _require_available()
    parsed = [t.strip().upper() for t in (tickers or "").split(",") if t.strip()]
    if not parsed:
        raise ValueError(
            "tickers required — comma-separated EXCHANGE:SYMBOL, "
            "e.g. 'NASDAQ:NVDA, KRX:005930'"
        )
    if len(parsed) > MAX_PRICE_TICKERS:
        raise ValueError(f"max {MAX_PRICE_TICKERS} tickers per call, got {len(parsed)}")
    malformed = [t for t in parsed if ":" not in t]
    if malformed:
        raise ValueError(
            f"tickers must be EXCHANGE:SYMBOL (e.g. NASDAQ:NVDA, KRX:005930); "
            f"invalid: {malformed}"
        )

    query = Query().set_tickers(*parsed).select(*_PRICE_COLUMNS)
    _total, df = query.get_scanner_data()
    found: dict[str, dict[str, Any]] = {}
    for r in df.to_dict("records"):
        row = {
            "ticker": _clean(r.get("ticker")),
            "symbol": _clean(r.get("name")),
            "description": _clean(r.get("description")),
            "exchange": _clean(r.get("exchange")),
            "price": _clean(r.get("close")),
            "currency": _clean(r.get("currency")),
            "change_percent": _clean(r.get("change")),
        }
        if row["ticker"]:
            found[str(row["ticker"]).upper()] = row
    missing = [t for t in parsed if t not in found]
    return {
        "requested": len(parsed),
        "returned": len(found),
        "rows": list(found.values()),
        # Surface misses explicitly — a silent drop reads as "price service
        # is broken" to the caller, a named miss reads as "typo in my list".
        "not_found": missing,
    }
