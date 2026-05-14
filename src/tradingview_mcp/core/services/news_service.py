"""
Financial News Service via RSS feeds.

Uses feedparser (already installed as part of agent-reach dependencies).
No API keys required. Pulls from free, public RSS feeds.

Sources:
  crypto: CoinDesk, Cointelegraph
  stocks: Yahoo Finance, MarketWatch (Top + Real-Time), CNBC
  all:    Combined

Note (2026-05-14): Original Reuters feeds (feeds.reuters.com) are deprecated
since ~2020 — they return zero entries. Replaced with Yahoo Finance,
MarketWatch, and CNBC which return live data. A `User-Agent` header is
required for some publishers (Yahoo, CNBC) to serve the feed correctly.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

# feedparser is bundled with agent-reach (installed globally)
try:
    import feedparser
    _FEEDPARSER_AVAILABLE = True
except ImportError:
    _FEEDPARSER_AVAILABLE = False

# ─── Feed Catalog ─────────────────────────────────────────────────────────────

RSS_FEEDS: dict[str, list[dict]] = {
    "crypto": [
        {"url": "https://www.coindesk.com/arc/outboundfeeds/rss/", "name": "CoinDesk"},
        {"url": "https://cointelegraph.com/rss", "name": "CoinTelegraph"},
    ],
    "stocks": [
        {"url": "https://finance.yahoo.com/news/rssindex", "name": "Yahoo Finance"},
        {"url": "https://feeds.content.dowjones.io/public/rss/mw_topstories", "name": "MarketWatch Top Stories"},
        {"url": "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines", "name": "MarketWatch Real-Time"},
        {"url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", "name": "CNBC Top News"},
    ],
    "all": [
        {"url": "https://finance.yahoo.com/news/rssindex", "name": "Yahoo Finance"},
        {"url": "https://feeds.content.dowjones.io/public/rss/mw_topstories", "name": "MarketWatch Top Stories"},
        {"url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", "name": "CNBC Top News"},
        {"url": "https://www.coindesk.com/arc/outboundfeeds/rss/", "name": "CoinDesk"},
        {"url": "https://cointelegraph.com/rss", "name": "CoinTelegraph"},
    ],
}

# Some publishers (Yahoo, CNBC) return empty feeds to the default urllib UA.
# Setting a browser-like UA produces live data.
_FEED_USER_AGENT = "Mozilla/5.0 (compatible; tradingview-mcp/0.7.1; +https://github.com/atilaahmettaner/tradingview-mcp)"
_TIMEOUT = 8


# ─── Public API ───────────────────────────────────────────────────────────────

def fetch_news(
    symbol: Optional[str] = None,
    category: str = "stocks",
    limit: int = 10,
) -> list[dict]:
    """
    Fetch financial news from RSS feeds.

    Args:
        symbol:   Optional ticker filter. If provided, only returns headlines
                  that mention the symbol (case-insensitive). e.g. "AAPL", "BTC"
        category: Feed group — "crypto" | "stocks" | "all"
        limit:    Maximum number of items to return

    Returns:
        List of news items with title, url, published, summary, source.
    """
    if not _FEEDPARSER_AVAILABLE:
        return [{
            "error": "feedparser not installed. Run: pip install feedparser",
            "install": "pip install feedparser"
        }]

    feeds = RSS_FEEDS.get(category, RSS_FEEDS["stocks"])
    results: list[dict] = []

    for feed_info in feeds:
        if len(results) >= limit:
            break
        try:
            feed = feedparser.parse(feed_info["url"], agent=_FEED_USER_AGENT)
            source_name = feed.feed.get("title", feed_info["name"])

            for entry in feed.entries:
                if len(results) >= limit:
                    break

                title = entry.get("title", "")
                summary = entry.get("summary", "") or entry.get("description", "")

                # Symbol filter
                if symbol:
                    combined = f"{title} {summary}".upper()
                    if symbol.upper() not in combined:
                        continue

                results.append({
                    "title": title,
                    "url": entry.get("link", ""),
                    "published": entry.get("published", ""),
                    "summary": _clean_html(summary)[:300],
                    "source": source_name,
                })

        except Exception:
            continue

    return results[:limit]


def fetch_news_summary(
    symbol: Optional[str] = None,
    category: str = "stocks",
    limit: int = 10,
) -> dict:
    """
    Fetch news and return structured dict for MCP tool output.
    """
    items = fetch_news(symbol, category, limit)
    return {
        "symbol": symbol,
        "category": category,
        "count": len(items),
        "feedparser_available": _FEEDPARSER_AVAILABLE,
        "items": items,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ─── Utils ────────────────────────────────────────────────────────────────────

def _clean_html(text: str) -> str:
    """Strip basic HTML tags from text."""
    import re
    text = re.sub(r"<[^>]+>", "", text)
    for entity, char in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&nbsp;", " ")):
        text = text.replace(entity, char)
    return text.strip()
