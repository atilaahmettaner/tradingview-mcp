"""
Futures Service — TradingView futures market data via tradingview_screener.

Covers CME, COMEX, NYMEX, CBOT, and optionally ICE/EUREX.
"""
from __future__ import annotations

from typing import Any

try:
    from tradingview_screener import futures as _futures_query
    from tradingview_screener.column import Column
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

# Exchanges grouped by category for filtering
US_FUTURES_EXCHANGES = ["CME", "COMEX", "NYMEX", "CBOT"]
ALL_FUTURES_EXCHANGES = ["CME", "COMEX", "NYMEX", "CBOT", "ICEEUR", "ICESG", "EUREX"]

# Well-known front-month continuous contract symbols
FUTURES_WATCHLIST: dict[str, list[str]] = {
    "equity_index": [
        "CME:ES1!", "CME:NQ1!", "CME:RTY1!", "CME:YM1!",
        "CME:EMD1!", "CME:NKD1!",
    ],
    "energy": [
        "NYMEX:CL1!", "NYMEX:NG1!", "NYMEX:HO1!", "NYMEX:RB1!",
        "NYMEX:MCL1!", "ICEEUR:BRN1!",
    ],
    "metals": [
        "COMEX:GC1!", "COMEX:SI1!", "COMEX:HG1!", "COMEX:PL1!",
        "NYMEX:PA1!",
    ],
    "agriculture": [
        "CBOT:ZC1!", "CBOT:ZW1!", "CBOT:ZS1!", "CBOT:ZL1!",
        "CBOT:ZM1!", "CBOT:LE1!", "CBOT:HE1!",
    ],
    "rates": [
        "CBOT:ZN1!", "CBOT:ZF1!", "CBOT:ZT1!", "CBOT:ZB1!",
        "CBOT:TN1!", "CBOT:UB1!", "CME:SR31!",
    ],
    "forex": [
        "CME:6E1!", "CME:6B1!", "CME:6J1!", "CME:6A1!",
        "CME:6C1!", "CME:6S1!",
    ],
    "crypto_futures": [
        "CME:BTC1!", "CME:MBT1!", "CME:ETH1!", "CME:MET1!",
    ],
}

_SCREENER_COLS = [
    "name", "description", "close", "open", "high", "low",
    "volume", "change", "change_abs", "currency", "exchange",
]


def _build_query(exchanges: list[str], volume_min: int = 0, limit: int = 50):
    if not _AVAILABLE:
        raise RuntimeError("tradingview_screener not installed")
    q = _futures_query()
    q = q.select(*_SCREENER_COLS)
    filters = [{"left": "exchange", "operation": "in_range", "right": exchanges}]
    if volume_min > 0:
        filters.append({"left": "volume", "operation": "greater", "right": volume_min})
    q.query["filter"] = filters
    q.query["range"] = [0, limit]
    return q


def get_futures_overview(
    category: str = "all",
    exchanges: str = "us",
    limit: int = 30,
    volume_min: int = 0,
) -> dict[str, Any]:
    """
    Top futures contracts sorted by volume.

    Args:
        category: all | equity_index | energy | metals | agriculture | rates | forex | crypto_futures
        exchanges: us (CME/COMEX/NYMEX/CBOT) | global (adds ICE/EUREX)
        limit: max rows
        volume_min: minimum volume filter
    """
    ex_list = ALL_FUTURES_EXCHANGES if exchanges.lower() == "global" else US_FUTURES_EXCHANGES
    q = _build_query(ex_list, volume_min=volume_min, limit=limit)
    q.query["sort"] = {"sortBy": "volume", "sortOrder": "desc"}
    count, df = q.get_scanner_data()

    rows = df.to_dict(orient="records")

    # Filter by category watchlist if requested
    if category != "all" and category in FUTURES_WATCHLIST:
        watchlist_names = {s.split(":")[-1] for s in FUTURES_WATCHLIST[category]}
        rows = [r for r in rows if r.get("name") in watchlist_names] or rows

    return {
        "category": category,
        "exchanges": ex_list,
        "total_available": count,
        "returned": len(rows),
        "contracts": rows,
    }


def get_futures_movers(
    direction: str = "gainers",
    exchanges: str = "us",
    limit: int = 20,
    volume_min: int = 10,
) -> dict[str, Any]:
    """Top futures gainers or losers by % change."""
    ex_list = ALL_FUTURES_EXCHANGES if exchanges.lower() == "global" else US_FUTURES_EXCHANGES
    q = _build_query(ex_list, volume_min=volume_min, limit=limit)
    sort_order = "desc" if direction == "gainers" else "asc"
    q.query["sort"] = {"sortBy": "change", "sortOrder": sort_order}
    count, df = q.get_scanner_data()
    return {
        "direction": direction,
        "total_available": count,
        "contracts": df.to_dict(orient="records"),
    }


def get_futures_category_snapshot(category: str) -> dict[str, Any]:
    """
    Get quote for all well-known contracts in a specific category.

    Args:
        category: equity_index | energy | metals | agriculture | rates | forex | crypto_futures
    """
    if not _AVAILABLE:
        raise RuntimeError("tradingview_screener not installed")

    symbols = FUTURES_WATCHLIST.get(category)
    if not symbols:
        valid = list(FUTURES_WATCHLIST.keys())
        return {"error": f"Unknown category '{category}'. Valid: {valid}"}

    q = _futures_query()
    q = q.select(*_SCREENER_COLS)
    # Filter by specific ticker symbols
    ticker_list = symbols
    q.query["symbols"] = {"tickers": ticker_list}
    q.query.pop("filter", None)
    q.query["range"] = [0, len(ticker_list)]

    try:
        count, df = q.get_scanner_data()
        return {
            "category": category,
            "contracts": df.to_dict(orient="records"),
        }
    except Exception as exc:
        # Fallback: use volume scan filtered to category names
        return get_futures_overview(category=category, limit=50, volume_min=0)


def get_futures_watchlist() -> dict[str, Any]:
    """Return the full categorized futures watchlist with all front-month symbols."""
    return {
        "description": "Well-known continuous front-month futures contracts by category",
        "categories": FUTURES_WATCHLIST,
        "total_symbols": sum(len(v) for v in FUTURES_WATCHLIST.values()),
    }
