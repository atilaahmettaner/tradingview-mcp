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
    "name", "description", "exchange", "open", "high", "low", "close",
    "currency", "change", "dividends_yield_current", "market_cap_basic",
)

_PRICE_COLUMNS = (
    "name", "description", "exchange", "open", "high", "low", "close",
    "currency", "change",
)

MAX_SCREEN_LIMIT = 2000
MAX_PRICE_TICKERS = 2000


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
    exclude_otc: bool = True,
    compact: bool = False,
) -> dict[str, Any]:
    """Screen stocks of one share type for a country market.

    Returns an envelope: total_matches is the market-wide count, rows are the
    top-N by market cap.

    exclude_otc (default True): TradingView's 'america' market means "trades
    on a US venue", not "is a US company" — without this filter ~1/3 of the
    top-100 is OTC foreign listings (Tencent, Roche, Nestlé...). Field-tested
    on day one: a user asking for "the biggest 100 US stocks" got 29 OTC rows.
    Pass exclude_otc=False to include them.

    compact (default False): True trims rows to ticker/symbol/price/currency/
    change_percent — for price-feed consumers pulling 1,000+ rows where the
    full envelope is mostly dead weight.

    Deliberately NOT deduplicated across share classes (GOOG/GOOGL, BRK.A/
    BRK.B): those are distinct instruments with distinct real prices, and
    which one is "canonical" is a consumer-side decision, not a data-layer one.

    change_percent can be null (fresh listings before their first full
    session, e.g. SKHY on IPO day). Deliberately NOT defaulted to 0 — "no
    change data" and "0% change" are different facts; null-check downstream.
    """
    _require_available()
    stock_type = (stock_type or "common").strip().lower()
    if stock_type not in STOCK_TYPES:
        raise ValueError(
            f"stock_type must be one of {list(STOCK_TYPES)}, got {stock_type!r}"
        )
    country = (country or "america").strip().lower()
    limit = max(1, min(int(limit), MAX_SCREEN_LIMIT))

    filters = [col("type") == "stock", col("typespecs").has([stock_type])]
    if exclude_otc:
        filters.append(col("exchange") != "OTC")
    query = (
        Query()
        .set_markets(country)
        .select(*_SCREEN_COLUMNS)
        .where(*filters)
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
            "open": _clean(r.get("open")),
            "high": _clean(r.get("high")),
            "low": _clean(r.get("low")),
            "currency": _clean(r.get("currency")),
            "change_percent": _clean(r.get("change")),
            "dividend_yield": _clean(r.get("dividends_yield_current")),
            "market_cap": _clean(r.get("market_cap_basic")),
        }
        for r in df.to_dict("records")
    ]
    if compact:
        keep = ("ticker", "symbol", "price", "currency", "change_percent")
        rows = [{k: r[k] for k in keep} for r in rows]
    return {
        "country": country,
        "stock_type": stock_type,
        "exclude_otc": exclude_otc,
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

    # .limit() is load-bearing: the scanner's default page size is 50, so
    # without it a 1,000-ticker request silently returns only 50 rows
    # (measured live 2026-07-14). With it, 1,000 prices come back in one
    # HTTP request in ~0.5s.
    query = Query().set_tickers(*parsed).select(*_PRICE_COLUMNS).limit(len(parsed))
    _total, df = query.get_scanner_data()
    found: dict[str, dict[str, Any]] = {}
    for r in df.to_dict("records"):
        row = {
            "ticker": _clean(r.get("ticker")),
            "symbol": _clean(r.get("name")),
            "description": _clean(r.get("description")),
            "exchange": _clean(r.get("exchange")),
            "price": _clean(r.get("close")),
            "open": _clean(r.get("open")),
            "high": _clean(r.get("high")),
            "low": _clean(r.get("low")),
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
