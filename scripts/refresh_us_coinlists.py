#!/usr/bin/env python3
"""Regenerate the US stock-exchange coinlists from TradingView's scanner.

The coinlist files are the offline symbol universe behind three things: error
suggestions (``listed_on``), venue auto-fallback (``pick_fallback_exchange``)
and the exchange-level scan tools. They were generated once and never
refreshed, so they drifted: listings that moved venue (WMT went NYSE -> NASDAQ
in December 2025), delisted, or listed since. See #96.

This rebuilds each file as exactly the set of tickers the scanner serves for
that venue, so every entry is one the tools can actually answer for.

    uv run python scripts/refresh_us_coinlists.py           # rewrite the files
    uv run python scripts/refresh_us_coinlists.py --check   # report drift only; exit 1 if stale
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tradingview_screener import Query, col

COINLIST_DIR = Path(__file__).resolve().parents[1] / "src" / "tradingview_mcp" / "coinlist"

# Venue as the scanner names it -> coinlist file.
EXCHANGES = {"NASDAQ": "nasdaq.txt", "NYSE": "nyse.txt"}

# In tradingview-screener, ``.limit(n)`` sets the END index of the result
# range, not a page size (``.offset()`` sets the start), so ``.offset(3000)
# .limit(3000)`` asks for an empty range. One request with a generous end
# index returns a whole venue; NASDAQ is ~5k rows.
RANGE_END = 20_000

# Refuse to write a list that shrank by more than this versus the current
# file. A scanner hiccup returning partial data must never silently gut a
# coinlist that the error paths and scans depend on.
MIN_KEEP_RATIO = 0.6


def fetch_live(exchange: str) -> set[str]:
    """Every ticker the scanner serves for ``exchange``, as ``EXCHANGE:SYMBOL``."""
    total, df = (
        Query()
        .set_markets("america")
        .select("name")
        .where(col("exchange") == exchange)
        .limit(RANGE_END)
        .get_scanner_data(timeout=60)
    )
    if len(df) < total:
        raise RuntimeError(
            f"{exchange}: scanner returned {len(df)} of {total} rows; raise RANGE_END"
        )
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

    current = {ex: read_current(COINLIST_DIR / fn) for ex, fn in EXCHANGES.items()}
    live = {ex: fetch_live(ex) for ex in EXCHANGES}
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

    for ex, fn in EXCHANGES.items():
        (COINLIST_DIR / fn).write_text("\n".join(sorted(live[ex])) + "\n", encoding="utf-8")
    print("written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
