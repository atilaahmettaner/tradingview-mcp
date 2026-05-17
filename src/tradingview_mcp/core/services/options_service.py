"""
Options chain + unusual activity service for US stocks.

Why this exists: a paying user (active morning-prep options trader) asked for
a way to spot institutional positioning before catalysts. The pattern they
care about is "strikes where today's volume is multiples of standing open
interest" — a classic V/OI > 1 signal that someone is opening size on a
specific strike in a specific direction.

Manually pulling this for a watchlist is the kind of grunt work AI is
supposed to remove. Two tools:

- get_options_chain(symbol, expiry=None)
    Full chain for one ticker. If `expiry` is not provided, returns the
    nearest expiration. Returns calls and puts with strike, last, bid, ask,
    volume, open_interest, IV.

- get_unusual_options_activity(symbol, top_n=10, min_volume=100)
    Ranks all strikes across all expirations by volume / open_interest
    ratio. Filters out illiquid noise (min_volume default 100). Returns
    top-N with call/put labelling and direction context. This is the
    "what is institutional money doing right now" call.

Data source: Yahoo Finance public options endpoint:
  https://query2.finance.yahoo.com/v7/finance/options/{symbol}
  https://query2.finance.yahoo.com/v7/finance/options/{symbol}?date={ts}

No auth, no key. Same pattern as extended_hours_service: raw urllib, no
third-party deps. Returns error dicts on failure rather than raising.
"""
from __future__ import annotations

import http.cookiejar
import json
import time
import urllib.parse
import urllib.request
import urllib.error
from typing import Optional, List, Dict, Any

_TIMEOUT = 12
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
# Yahoo started gating /v7/finance/options behind a crumb+cookie session
# in 2024 (same as the quoteSummary endpoint). Without auth: HTTP 401.
# We open a session against fc.yahoo.com to drop cookies, then ask
# query2 for a crumb token, then attach `?crumb=...` to every request.
_BASE = "https://query2.finance.yahoo.com/v7/finance/options"

# Session cache: crumb tokens expire — re-handshake every ~25 minutes.
_SESSION_CACHE: dict = {"crumb": None, "opener": None, "ts": 0.0}
_SESSION_TTL = 1500


def _new_session_opener() -> urllib.request.OpenerDirector:
    """Build a cookie-aware urllib opener with a browser-like User-Agent.

    Yahoo's anti-bot blocks plain `python-urllib/x.y` so we present as Chrome.
    """
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    opener.addheaders = [
        ("User-Agent", _UA),
        ("Accept", "application/json, text/plain, */*"),
        ("Accept-Language", "en-US,en;q=0.9"),
    ]
    return opener


def _get_session() -> tuple:
    """Return a (crumb, opener_with_cookies) pair, cached for 25 minutes.

    1. Hit fc.yahoo.com so Yahoo drops session cookies (status irrelevant).
    2. Ask query2/v1/test/getcrumb for the per-session crumb token.
    3. Re-use both for all subsequent options calls.
    """
    now = time.time()
    if _SESSION_CACHE["crumb"] and (now - _SESSION_CACHE["ts"]) < _SESSION_TTL:
        return _SESSION_CACHE["crumb"], _SESSION_CACHE["opener"]

    opener = _new_session_opener()
    # Cookie-drop step. Any HTTP status here is fine — we only need Set-Cookie.
    try:
        opener.open("https://fc.yahoo.com/", timeout=_TIMEOUT)
    except urllib.error.HTTPError:
        pass
    except urllib.error.URLError:
        pass

    req = urllib.request.Request(
        "https://query2.finance.yahoo.com/v1/test/getcrumb",
        headers={"User-Agent": _UA, "Accept": "text/plain"},
    )
    with opener.open(req, timeout=_TIMEOUT) as resp:
        crumb = resp.read().decode("utf-8").strip()
    if not crumb or len(crumb) > 100:
        raise ValueError(f"unexpected crumb response: {crumb[:80]!r}")

    _SESSION_CACHE.update(crumb=crumb, opener=opener, ts=now)
    return crumb, opener


def _fetch(url: str) -> dict:
    """GET JSON from Yahoo using a crumb+cookie session.

    Adds `?crumb=...` (or `&crumb=...`) to the URL automatically. On 401 (crumb
    rotated server-side), invalidates the cache and retries once.
    """

    def _go() -> dict:
        crumb, opener = _get_session()
        sep = "&" if "?" in url else "?"
        full = f"{url}{sep}crumb={urllib.parse.quote(crumb)}"
        with opener.open(full, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))

    try:
        return _go()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            # Session likely expired mid-flight. Invalidate and retry once.
            _SESSION_CACHE.update(crumb=None, opener=None, ts=0.0)
            return _go()
        raise


def _fmt_expiry(ts: Optional[int]) -> Optional[str]:
    if ts is None:
        return None
    return time.strftime("%Y-%m-%d", time.gmtime(ts))


def _safe_round(value, ndigits: int = 4):
    if value is None:
        return None
    try:
        return round(float(value), ndigits)
    except (TypeError, ValueError):
        return None


def _normalize_contract(c: Dict[str, Any], side: str) -> Dict[str, Any]:
    """Flatten a Yahoo option contract into the shape we return."""
    return {
        "contract_symbol": c.get("contractSymbol"),
        "side": side,  # 'call' or 'put'
        "strike": _safe_round(c.get("strike"), 2),
        "last_price": _safe_round(c.get("lastPrice"), 2),
        "bid": _safe_round(c.get("bid"), 2),
        "ask": _safe_round(c.get("ask"), 2),
        "volume": c.get("volume") or 0,
        "open_interest": c.get("openInterest") or 0,
        "implied_volatility": _safe_round(c.get("impliedVolatility"), 4),
        "in_the_money": c.get("inTheMoney"),
        "expiration": _fmt_expiry(c.get("expiration")),
    }


# ── Tool 1: get_options_chain ───────────────────────────────────────────────


def get_options_chain(symbol: str, expiry: Optional[str] = None) -> dict:
    """Fetch options chain (calls + puts) for one symbol and one expiry.

    Args:
        symbol: US stock symbol (AAPL, TSLA, SPY, ...).
        expiry: ISO date string (YYYY-MM-DD). If None, uses nearest expiry.

    Returns:
        Dict with:
            symbol, underlying_price, requested_expiry, available_expiries,
            calls: list of contracts, puts: list of contracts
        Or {symbol, error} on failure.
    """
    sym = symbol.strip().upper()
    url = f"{_BASE}/{sym}"
    try:
        data = _fetch(url)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as e:
        return {"symbol": sym, "error": f"{type(e).__name__}: {e}"}

    try:
        chain = data["optionChain"]["result"][0]
    except (KeyError, IndexError, TypeError):
        err = data.get("optionChain", {}).get("error")
        return {"symbol": sym, "error": err or "no options data for symbol"}

    underlying = chain.get("quote", {}) or {}
    expirations = chain.get("expirationDates", []) or []
    available_iso = [_fmt_expiry(e) for e in expirations]

    # Resolve target expiry: caller-provided, else first option block returned.
    target_expiry_ts: Optional[int] = None
    if expiry:
        for e in expirations:
            if _fmt_expiry(e) == expiry:
                target_expiry_ts = e
                break
        if target_expiry_ts is None:
            return {
                "symbol": sym,
                "error": f"expiry {expiry} not available",
                "available_expiries": available_iso,
            }

    # If a specific expiry was requested, re-fetch scoped to that timestamp.
    if target_expiry_ts is not None:
        try:
            data = _fetch(f"{_BASE}/{sym}?date={target_expiry_ts}")
            chain = data["optionChain"]["result"][0]
        except (urllib.error.URLError, urllib.error.HTTPError,
                json.JSONDecodeError, KeyError, IndexError) as e:
            return {"symbol": sym, "error": f"failed to fetch expiry: {e}"}

    options_blocks = chain.get("options", []) or []
    if not options_blocks:
        return {
            "symbol": sym,
            "underlying_price": _safe_round(underlying.get("regularMarketPrice"), 2),
            "requested_expiry": expiry,
            "available_expiries": available_iso,
            "calls": [],
            "puts": [],
            "note": "no contracts returned for this expiry",
        }

    block = options_blocks[0]
    calls = [_normalize_contract(c, "call") for c in block.get("calls", [])]
    puts = [_normalize_contract(p, "put") for p in block.get("puts", [])]

    return {
        "symbol": sym,
        "underlying_price": _safe_round(underlying.get("regularMarketPrice"), 2),
        "underlying_change_pct": _safe_round(
            underlying.get("regularMarketChangePercent"), 2
        ),
        "requested_expiry": _fmt_expiry(block.get("expirationDate")),
        "available_expiries": available_iso,
        "call_count": len(calls),
        "put_count": len(puts),
        "calls": calls,
        "puts": puts,
        "source": "Yahoo Finance",
    }


# ── Tool 2: get_unusual_options_activity ────────────────────────────────────


def get_unusual_options_activity(
    symbol: str,
    top_n: int = 10,
    min_volume: int = 100,
    expiries: int = 4,
) -> dict:
    """Rank strikes by today's volume / standing open-interest ratio.

    Flags strikes where today's volume is a large multiple of standing OI —
    a classic "someone is opening size here" signal that's useful for
    spotting institutional positioning before catalysts (earnings, FOMC,
    macro prints).

    Args:
        symbol: US stock symbol.
        top_n: Number of strikes to return, ranked by V/OI descending.
            Default 10.
        min_volume: Filter floor for today's volume — drops illiquid
            strikes whose ratios are noise. Default 100.
        expiries: How many of the soonest expirations to scan. Default 4
            (typically covers ~1 month of weeklies/monthlies).

    Returns:
        Dict with:
            symbol, underlying_price, total_call_volume, total_put_volume,
            put_call_volume_ratio,
            unusual: list of top-N contracts sorted by V/OI desc, each with
                strike, side (call/put), expiry, volume, open_interest,
                v_oi_ratio, IV, moneyness
        Or {symbol, error} on failure.
    """
    sym = symbol.strip().upper()

    # First call: get list of expiration timestamps.
    try:
        data = _fetch(f"{_BASE}/{sym}")
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as e:
        return {"symbol": sym, "error": f"{type(e).__name__}: {e}"}

    try:
        chain0 = data["optionChain"]["result"][0]
    except (KeyError, IndexError, TypeError):
        err = data.get("optionChain", {}).get("error")
        return {"symbol": sym, "error": err or "no options data for symbol"}

    underlying = chain0.get("quote", {}) or {}
    underlying_price = _safe_round(underlying.get("regularMarketPrice"), 2)
    expirations = (chain0.get("expirationDates") or [])[:max(1, expiries)]

    all_contracts: List[Dict[str, Any]] = []
    total_call_vol = 0
    total_put_vol = 0
    fetched_expiries: List[str] = []

    # Iterate over the first N expirations.
    for ts in expirations:
        try:
            d = _fetch(f"{_BASE}/{sym}?date={ts}")
            blk = d["optionChain"]["result"][0]["options"][0]
        except (urllib.error.URLError, urllib.error.HTTPError,
                json.JSONDecodeError, KeyError, IndexError):
            # Skip a broken expiry rather than failing the whole call.
            continue

        fetched_expiries.append(_fmt_expiry(ts))
        for c in blk.get("calls", []):
            v = c.get("volume") or 0
            total_call_vol += v
            all_contracts.append(_normalize_contract(c, "call"))
        for p in blk.get("puts", []):
            v = p.get("volume") or 0
            total_put_vol += v
            all_contracts.append(_normalize_contract(p, "put"))

    if not all_contracts:
        return {
            "symbol": sym,
            "error": "no contracts returned across requested expiries",
            "expiries_scanned": fetched_expiries,
        }

    # Compute V/OI and moneyness for each, filter, sort.
    ranked: List[Dict[str, Any]] = []
    for c in all_contracts:
        vol = c["volume"] or 0
        oi = c["open_interest"] or 0
        if vol < min_volume:
            continue
        # Use max(oi, 1) so a 0-OI brand-new strike with real volume still
        # gets a high score rather than div-by-zero.
        ratio = vol / max(oi, 1)
        moneyness = None
        if underlying_price is not None and c["strike"] is not None:
            diff_pct = (c["strike"] - underlying_price) / underlying_price * 100
            moneyness = round(diff_pct, 2)
        ranked.append({
            "contract_symbol": c["contract_symbol"],
            "side": c["side"],
            "strike": c["strike"],
            "expiration": c["expiration"],
            "volume": vol,
            "open_interest": oi,
            "v_oi_ratio": round(ratio, 2),
            "last_price": c["last_price"],
            "implied_volatility": c["implied_volatility"],
            "in_the_money": c["in_the_money"],
            "strike_vs_spot_pct": moneyness,
        })

    ranked.sort(key=lambda r: r["v_oi_ratio"], reverse=True)
    top = ranked[: max(1, top_n)]

    pc_ratio = None
    if total_call_vol > 0:
        pc_ratio = round(total_put_vol / total_call_vol, 2)

    return {
        "symbol": sym,
        "underlying_price": underlying_price,
        "expiries_scanned": fetched_expiries,
        "total_call_volume": total_call_vol,
        "total_put_volume": total_put_vol,
        "put_call_volume_ratio": pc_ratio,
        "filter": {
            "min_volume": min_volume,
            "top_n": top_n,
            "expiries_checked": len(fetched_expiries),
        },
        "unusual": top,
        "source": "Yahoo Finance",
    }
