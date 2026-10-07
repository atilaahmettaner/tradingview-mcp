#!/usr/bin/env python3
"""Regenerate the stock-exchange coinlists from TradingView's scanner.

The coinlist files are the offline symbol universe behind three things: error
suggestions (``listed_on``), venue auto-fallback (``pick_fallback_exchange``)
and the exchange-level scan tools. They were generated once and never
refreshed, so they drifted: listings that moved venue (WMT went NYSE -> NASDAQ
in December 2025), delisted, or listed since. See #96.

This rebuilds each file as exactly the set of tickers the scanner serves for
that venue, so every entry is one the tools can actually answer for. Covers
the US venues plus the European, Canadian, Indian and Indonesian ones.

    uv run python scripts/refresh_coinlists.py           # rewrite the files
    uv run python scripts/refresh_coinlists.py --check   # report drift only; exit 1 if stale
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tradingview_screener import Query, col

COINLIST_DIR = Path(__file__).resolve().parents[1] / "src" / "tradingview_mcp" / "coinlist"

STOCKS = ("stock", "dr")

# Coinlist (file stem, upper-cased) -> (scanner market, venue as the scanner
# names it, instrument types to keep; None keeps every type).
#
# The US lists keep every type the scanner serves there, as before. Every
# other venue keeps stocks and depositary receipts only: European listings are
# dominated by ETPs and funds (3,199 of Euronext Paris's 3,811 rows are funds),
# and without the filter "top gainers on LSE" would mostly rank leveraged ETPs.
# The four Euronext venues share the EURONEXT prefix and differ only by market.
VENUES = {
    "NASDAQ": ("america", "NASDAQ", None),
    "NYSE": ("america", "NYSE", None),
    "EPA": ("france", "EURONEXT", STOCKS),
    "AMS": ("netherlands", "EURONEXT", STOCKS),
    "BRU": ("belgium", "EURONEXT", STOCKS),
    "LIS": ("portugal", "EURONEXT", STOCKS),
    "MIL": ("italy", "MIL", STOCKS),
    "LSE": ("uk", "LSE", STOCKS),
    "SIX": ("switzerland", "SIX", STOCKS),
    "BME": ("spain", "BME", STOCKS),
    "TSX": ("canada", "TSX", STOCKS),
    "TSXV": ("canada", "TSXV", STOCKS),
    "XETRA": ("germany", "XETR", STOCKS),
    "FWB": ("germany", "FWB", STOCKS),
    "NSE": ("india", "NSE", STOCKS),
    "BSE": ("india", "BSE", STOCKS),
    "IDX": ("indonesia", "IDX", STOCKS),
}


def coinlist_path(venue: str) -> Path:
    return COINLIST_DIR / f"{venue.lower()}.txt"

# In tradingview-screener, ``.limit(n)`` sets the END index of the result
# range, not a page size (``.offset()`` sets the start), so ``.offset(3000)
# .limit(3000)`` asks for an empty range. One request with a generous end
# index returns a whole venue; NASDAQ is ~5k rows.
RANGE_END = 20_000

# Refuse to write a list that shrank by more than this versus the current
# file. A scanner hiccup returning partial data must never silently gut a
# coinlist that the error paths and scans depend on.
MIN_KEEP_RATIO = 0.6


def fetch_live(market: str, exchange: str, types: tuple[str, ...] | None = None) -> set[str]:
    """Every ticker the scanner serves for ``exchange`` in ``market``, as ``EXCHANGE:SYMBOL``."""
    total, df = (
        Query()
        .set_markets(market)
        .select("name", "type")
        .where(col("exchange") == exchange)
        .limit(RANGE_END)
        .get_scanner_data(timeout=60)
    )
    if len(df) < total:
        raise RuntimeError(
            f"{exchange}: scanner returned {len(df)} of {total} rows; raise RANGE_END"
        )
    if types is not None:
        df = df[df["type"].isin(types)]
    return {f"{exchange}:{name}" for name in df["name"] if isinstance(name, str) and name}


def read_current(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def plan(current: dict[str, set[str]], live: dict[str, set[str]]) -> dict:
    """Pure diff: per-venue added/removed tickers, plus cross-venue moves."""
    venues = {
        ex: {"added": sorted(live[ex] - current[ex]), "removed": sorted(current[ex] - live[ex])}
        for ex in live
    }

    def bare(tickers: list[str]) -> set[str]:
        return {t.split(":", 1)[1] for t in tickers}

    moves = sorted(
        (symbol, src, dst)
        for src in venues
        for dst in venues
        if src != dst
        for symbol in bare(venues[src]["removed"]) & bare(venues[dst]["added"])
    )
    return {"venues": venues, "moves": moves}


def shrink_violations(
    current: dict[str, set[str]], live: dict[str, set[str]], ratio: float = MIN_KEEP_RATIO
) -> list[str]:
    """Venues whose fresh list is suspiciously smaller than the current one."""
    return [ex for ex in live if current[ex] and len(live[ex]) < ratio * len(current[ex])]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report drift without writing; exit 1 if stale")
    args = parser.parse_args()

    current = {venue: read_current(coinlist_path(venue)) for venue in VENUES}
    live = {venue: fetch_live(*spec) for venue, spec in VENUES.items()}
    report = plan(current, live)

    for ex, diff in report["venues"].items():
        print(
            f"{ex:<7} current {len(current[ex]):>5}  live {len(live[ex]):>5}  "
            f"+{len(diff['added'])} added  -{len(diff['removed'])} gone"
        )
    if report["moves"]:
        print(f"moved venue ({len(report['moves'])}):")
        for symbol, src, dst in report["moves"]:
            print(f"  {symbol}: {src} -> {dst}")

    stale = any(d["added"] or d["removed"] for d in report["venues"].values())
    if args.check:
        print("stale" if stale else "up to date")
        return 1 if stale else 0

    bad = shrink_violations(current, live)
    if bad:
        print(f"refusing to write: {', '.join(bad)} shrank below {MIN_KEEP_RATIO:.0%} of the current list")
        return 2

    for venue in VENUES:
        coinlist_path(venue).write_text("\n".join(sorted(live[venue])) + "\n", encoding="utf-8")
    print("written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
