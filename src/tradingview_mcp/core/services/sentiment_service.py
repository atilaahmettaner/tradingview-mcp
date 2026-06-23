"""
Market Sentiment Service via Reddit JSON API.

Uses Agent-Reach architecture (same approach as agent_reach/channels/reddit.py)
but integrated directly into tradingview-mcp as a native service.

Zero external dependencies — pure Python stdlib (urllib, json).
feedparser is optional (used by news_service.py).
"""
from __future__ import annotations

import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from typing import Optional

from tradingview_mcp.core.services.proxy_manager import build_opener_with_proxy, is_proxy_configured
from tradingview_mcp.core.utils.cache import cached

# ─── Constants ────────────────────────────────────────────────────────────────

_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
_TIMEOUT = 10

BULLISH_KEYWORDS = [
    "buy", "bull", "moon", "pump", "long", "call", "up", "gain",
    "strong", "breakout", "bullish", "rally", "surge", "upside",
    "accumulate", "undervalued", "support", "bottom", "recovery",
]

BEARISH_KEYWORDS = [
    "sell", "bear", "dump", "short", "put", "down", "loss", "weak",
    "crash", "drop", "bearish", "tank", "decline", "downside",
    "overvalued", "resistance", "top", "overbought", "bubble",
]

# Subreddit groups by asset class
SUBREDDIT_GROUPS: dict[str, list[str]] = {
    "crypto": ["CryptoCurrency", "Bitcoin", "ethereum", "CryptoMarkets", "altcoin"],
    "stocks": ["stocks", "investing", "wallstreetbets", "StockMarket", "ValueInvesting"],
    "all":    ["wallstreetbets", "stocks", "investing", "CryptoCurrency", "StockMarket"],
}


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _fetch_reddit_posts(subreddit: str, query: str, limit: int = 10) -> list:
    """Fetch posts from a subreddit search. Returns raw Reddit post data list."""
    url = (
        f"https://www.reddit.com/r/{subreddit}/search.json"
        f"?q={urllib.parse.quote(query)}&sort=new&t=week&limit={limit}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        opener = build_opener_with_proxy(_USER_AGENT)
        with opener.open(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["data"]["children"]
    except Exception:
        return []


def _score_text(text: str) -> float:
    """
    Score a text for bullish/bearish sentiment.
    Returns float from -1.0 (fully bearish) to +1.0 (fully bullish).
    0.0 = neutral or no sentiment words found.
    """
    t = text.lower()
    bull = sum(1 for w in BULLISH_KEYWORDS if w in t)
    bear = sum(1 for w in BEARISH_KEYWORDS if w in t)
    total = bull + bear
    if total == 0:
        return 0.0
    return (bull - bear) / total


def _label(score: float) -> str:
    if score > 0.2:
        return "Strongly Bullish"
    elif score > 0.05:
        return "Bullish"
    elif score < -0.2:
        return "Strongly Bearish"
    elif score < -0.05:
        return "Bearish"
    return "Neutral"


# ─── Public API ───────────────────────────────────────────────────────────────

@cached(
    key_fn=lambda symbol, category="all", limit=20: (
        symbol.upper(),
        category,
        int(limit),
    ),
    ttl_env="CACHE_TTL_SENTIMENT",
    default_ttl=300.0,
)
def analyze_sentiment(
    symbol: str,
    category: str = "all",
    limit: int = 20,
) -> dict:
    """
    Analyze Reddit sentiment for a given symbol.

    Args:
        symbol:   Asset ticker/name ("AAPL", "BTC", "ETH", "TSLA", "THYAO")
        category: Subreddit group — "crypto" | "stocks" | "all"
        limit:    Total number of posts to analyze across all subreddits

    Returns:
        dict with sentiment_score (-1 to +1), label, post breakdown, top posts.
    """
    subs = SUBREDDIT_GROUPS.get(category, SUBREDDIT_GROUPS["all"])
    per_sub = max(2, limit // len(subs) + 1)

    all_posts: list[dict] = []
    scores: list[float] = []

    for sub in subs:
        raw = _fetch_reddit_posts(sub, symbol, per_sub)
        for p in raw:
            d = p.get("data", {})
            title = d.get("title", "")
            body = d.get("selftext", "")
            text = f"{title} {body}"
            score = _score_text(text)
            scores.append(score)
            all_posts.append({
                "title": title[:120],
                "upvotes": d.get("score", 0),
                "comments": d.get("num_comments", 0),
                "sentiment": "bullish" if score > 0 else "bearish" if score < 0 else "neutral",
                "url": f"https://reddit.com{d.get('permalink', '')}",
                "subreddit": f"r/{sub}",
            })

    # Aggregate
    avg = sum(scores) / len(scores) if scores else 0.0
    all_posts.sort(key=lambda x: x["upvotes"], reverse=True)

    return {
        "symbol": symbol.upper(),
        "sentiment_score": round(avg, 3),
        "sentiment_label": _label(avg),
        "posts_analyzed": len(scores),
        "bullish_count": sum(1 for s in scores if s > 0),
        "bearish_count": sum(1 for s in scores if s < 0),
        "neutral_count": sum(1 for s in scores if s == 0),
        "top_posts": all_posts[:5],
        "sources": [f"r/{s}" for s in subs],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
