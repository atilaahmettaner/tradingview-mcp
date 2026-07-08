"""
Licensed news + sentiment via the Marketaux API.

Replaces the RSS scrape (news_service.py) and the Reddit scrape
(sentiment_service.py) with a single licensed source. Both public functions
keep the exact names and output shapes of the modules they replace, so
server.py only swaps imports.

Design constraints (free plan: 100 requests/day, 3 articles/request):
  - ONE underlying fetch per symbol serves BOTH news and sentiment —
    articles are the news; their entity sentiment scores are the sentiment.
    combined_analysis therefore costs 1 request, not 2.
  - 4h TTL cache, stale entries retained: on a daily-timeframe product,
    4h-old headlines are fine, and stale beats empty when the budget runs out.
  - Hard daily budget (default 90, env-tunable): once spent, serve stale or a
    shape-compatible "unavailable" payload — never raise into the tool layer.

Env:
  MARKETAUX_API_TOKEN   required for live data (no token -> graceful stub)
  MARKETAUX_DAILY_BUDGET optional, default 90
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Optional

_API_URL = "https://api.marketaux.com/v1/news/all"
_TIMEOUT = 10
_TTL_SECONDS = 4 * 3600
_CACHE_MAX_ENTRIES = 500

# Suffixes used by exchange-style crypto tickers (BTCUSDT -> BTC).
_QUOTE_SUFFIXES = ("USDT", "USDC", "BUSD", "PERP", "USD")
_KNOWN_CRYPTO_BASES = {
    "BTC", "ETH", "SOL", "XRP", "BNB", "ADA", "DOGE", "AVAX", "DOT", "LINK",
    "TRX", "TON", "PEPE", "AAVE", "HYPE", "TAO", "WLD", "SUI", "NEAR", "LTC",
}

_lock = threading.Lock()
_cache: dict[str, tuple[float, list[dict]]] = {}
_budget = {"day": "", "used": 0}


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _budget_left() -> int:
    limit = int(os.environ.get("MARKETAUX_DAILY_BUDGET", "90"))
    if _budget["day"] != _today():
        _budget["day"] = _today()
        _budget["used"] = 0
    return limit - _budget["used"]


def _clean_symbol(symbol: str) -> tuple[str, bool]:
    """BTCUSDT -> ("BTC", True); AAPL -> ("AAPL", False)."""
    s = (symbol or "").upper().strip()
    is_crypto = False
    for suf in _QUOTE_SUFFIXES:
        if s.endswith(suf) and len(s) > len(suf) + 1:
            s = s[: -len(suf)]
            is_crypto = True
            break
    if s in _KNOWN_CRYPTO_BASES:
        is_crypto = True
    return s, is_crypto


def _request(params: dict) -> Optional[list[dict]]:
    """One live Marketaux call. Returns article list, or None on any failure.
    Caller is responsible for budget accounting."""
    token = os.environ.get("MARKETAUX_API_TOKEN", "")
    if not token:
        return None
    q = dict(params)
    q["api_token"] = token
    q.setdefault("language", "en")
    q.setdefault("filter_entities", "true")
    q.setdefault("limit", "3")
    url = f"{_API_URL}?{urllib.parse.urlencode(q)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "tradingview-mcp"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("data") or []
    except Exception:
        return None


def _get_articles(symbol: Optional[str], category: str) -> tuple[list[dict], str]:
    """Cached article fetch. Returns (articles, freshness) where freshness is
    "live" | "cached" | "stale" | "unavailable"."""
    if symbol:
        base, is_crypto = _clean_symbol(symbol)
        key = f"sym:{base}"
    else:
        base, is_crypto = "", category == "crypto"
        key = f"cat:{category}"

    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < _TTL_SECONDS:
            return hit[1], "cached"
        if _budget_left() <= 0:
            return (hit[1], "stale") if hit else ([], "unavailable")
        _budget["used"] += 1  # reserve before the network call

    if base:
        # Crypto tickers aren't reliably in Marketaux's symbols index — a text
        # search on the base finds coin coverage; equities go through symbols=.
        params = {"search": base} if is_crypto else {"symbols": base}
    elif category == "crypto":
        params = {"search": "cryptocurrency OR bitcoin"}
    else:
        params = {}  # general market news

    articles = _request(params)

    # Equity-style lookup that came back empty may still be a crypto ticker
    # we don't know (e.g. a new coin) — one text-search fallback, budget permitting.
    if base and not is_crypto and articles == []:
        with _lock:
            can_retry = _budget_left() > 0
            if can_retry:
                _budget["used"] += 1
        if can_retry:
            articles = _request({"search": base})

    with _lock:
        if articles is None:
            hit = _cache.get(key)
            return (hit[1], "stale") if hit else ([], "unavailable")
        _cache[key] = (now, articles)
        if len(_cache) > _CACHE_MAX_ENTRIES:
            oldest = min(_cache, key=lambda k: _cache[k][0])
            _cache.pop(oldest, None)
        return articles, "live"


def _clean_text(text: str) -> str:
    import re
    text = re.sub(r"<[^>]+>", "", text or "")
    for entity, char in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&nbsp;", " ")):
        text = text.replace(entity, char)
    return text.strip()


# Keyword fallback for articles Marketaux returns WITHOUT entity scores (its
# text-search path — most crypto coverage — attaches no entities). Same scorer
# the old Reddit service used, applied to licensed headline/description text.
_BULLISH_KEYWORDS = [
    "buy", "bull", "moon", "pump", "long", "call", "up", "gain",
    "strong", "breakout", "bullish", "rally", "surge", "upside",
    "accumulate", "undervalued", "support", "bottom", "recovery",
]
_BEARISH_KEYWORDS = [
    "sell", "bear", "dump", "short", "put", "down", "loss", "weak",
    "crash", "drop", "bearish", "tank", "decline", "downside",
    "overvalued", "resistance", "top", "overbought", "bubble",
]


def _keyword_score(text: str) -> float:
    t = (text or "").lower()
    bull = sum(1 for w in _BULLISH_KEYWORDS if w in t)
    bear = sum(1 for w in _BEARISH_KEYWORDS if w in t)
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


# ─── Public API (same names/shapes as the modules this replaces) ─────────────

def fetch_news_summary(
    symbol: Optional[str] = None,
    category: str = "stocks",
    limit: int = 10,
) -> dict:
    """Licensed financial news via Marketaux. Same output shape as the old
    RSS-based fetch_news_summary."""
    if not os.environ.get("MARKETAUX_API_TOKEN"):
        return {
            "symbol": symbol, "category": category, "count": 0, "items": [],
            "provider": "marketaux",
            "error": "MARKETAUX_API_TOKEN not configured",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    articles, freshness = _get_articles(symbol, category)
    items = [{
        "title": a.get("title", ""),
        "url": a.get("url", ""),
        "published": a.get("published_at", ""),
        "summary": _clean_text(a.get("description") or a.get("snippet") or "")[:300],
        "source": a.get("source", "Marketaux"),
    } for a in articles[:limit]]
    out = {
        "symbol": symbol,
        "category": category,
        "count": len(items),
        "items": items,
        "provider": "marketaux",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if freshness in ("stale", "unavailable"):
        out["note"] = f"news {freshness}: daily news budget exhausted or provider unreachable"
    return out


def analyze_sentiment(
    symbol: str,
    category: str = "all",
    limit: int = 20,
) -> dict:
    """News-based sentiment via Marketaux entity sentiment scores. Same output
    shape as the old Reddit-based analyze_sentiment (top_posts now carries
    news articles instead of Reddit posts)."""
    base, _ = _clean_symbol(symbol)
    if not os.environ.get("MARKETAUX_API_TOKEN"):
        return {
            "symbol": (symbol or "").upper(), "sentiment_score": 0.0,
            "sentiment_label": "Unavailable", "posts_analyzed": 0,
            "bullish_count": 0, "bearish_count": 0, "neutral_count": 0,
            "top_posts": [], "sources": ["Marketaux news"],
            "provider": "marketaux",
            "error": "MARKETAUX_API_TOKEN not configured",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    articles, freshness = _get_articles(symbol, category)

    scores: list[float] = []
    top: list[dict] = []
    for a in articles:
        ent_scores = [
            e.get("sentiment_score")
            for e in (a.get("entities") or [])
            if isinstance(e.get("sentiment_score"), (int, float))
            and (e.get("symbol", "").upper().startswith(base) if base else True)
        ]
        if not ent_scores:  # fall back to any scored entity on the article
            ent_scores = [
                e.get("sentiment_score")
                for e in (a.get("entities") or [])
                if isinstance(e.get("sentiment_score"), (int, float))
            ]
        if ent_scores:
            art_score = sum(ent_scores) / len(ent_scores)
        else:
            # No entity scores at all (Marketaux's text-search path) —
            # keyword-score the licensed headline/description text instead.
            art_score = _keyword_score(f"{a.get('title', '')} {a.get('description', '')}")
        scores.append(art_score)
        top.append({
            "title": (a.get("title") or "")[:120],
            "url": a.get("url", ""),
            "sentiment": "bullish" if art_score > 0.05 else "bearish" if art_score < -0.05 else "neutral",
            "source": a.get("source", "Marketaux"),
            "published": a.get("published_at", ""),
        })

    avg = sum(scores) / len(scores) if scores else 0.0
    out = {
        "symbol": (symbol or "").upper(),
        "sentiment_score": round(avg, 3),
        "sentiment_label": _label(avg),
        "posts_analyzed": len(scores),
        "bullish_count": sum(1 for s in scores if s > 0.05),
        "bearish_count": sum(1 for s in scores if s < -0.05),
        "neutral_count": sum(1 for s in scores if -0.05 <= s <= 0.05),
        "top_posts": top[:5],
        "sources": ["Marketaux news"],
        "provider": "marketaux",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if freshness in ("stale", "unavailable"):
        out["note"] = f"sentiment {freshness}: daily news budget exhausted or provider unreachable"
    return out
